from __future__ import annotations

import json
from typing import Optional
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.prompts import build_persona_system_prompt
from app.db.models import ChatMessage, ConversationSession, Person, PersonaProfile, RoundtableTurn, SpeakerCard
from app.schemas.recommend import RecommendRequest
from app.schemas.roundtable import (
    RoundtableMemoryState,
    RoundtableParticipant,
    RoundtablePlan,
    RoundtableRequest,
    RoundtableResponse,
    RoundtableTurnResponse,
)
from app.services.llm import DeepSeekService
from app.services.memory import MemoryService
from app.services.recommend import RecommendService
from app.services.retrieval import RetrievalService


ROLE_LABELS = {
    'primary_responder': '主答者',
    'challenger': '质疑者',
    'complement': '补充者',
    'clarifier': '澄清者',
    'critic': '批评者',
}


class RoundtableService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.llm = DeepSeekService()
        self.recommend = RecommendService(db)
        self.retrieval = RetrievalService(db)
        self.memory = MemoryService(db)

    async def respond(self, request: RoundtableRequest) -> RoundtableResponse:
        user_memory_text = request.memory_text if request.memory_text is not None else request.question
        session = self._session(request)
        summary = self.memory.latest_summary(session.id)
        recalled = self.memory.recall(request.user_id, request.question)
        actors = self._select_actors(request)
        if not actors:
            raise HTTPException(status_code=404, detail='没有可用的智囊人物。')

        participants = self._participants(actors)
        plan = RoundtablePlan(
            mode='single_expert' if len(participants) == 1 else 'mini_roundtable',
            reasoning='根据问题、资料主题、人物专长和用户指定人物选择参与者。',
            participants=participants,
        )
        session.selected_people = [item.participant_id or item.person_slug or '' for item in participants]
        topic_state = dict(session.topic_analysis or {})
        round_number = int(topic_state.get('round_count') or 0) + 1
        session.topic_analysis = {
            **topic_state, 'user_id': request.user_id, 'plan': plan.model_dump(), 'round_count': round_number,
        }

        memory_context = '\n'.join(f'- {item.content}' for item in recalled)
        previous: list[str] = []
        turns: list[RoundtableTurnResponse] = []
        round_history = list(topic_state.get('round_history') or [])
        recent_speaker_ids = [
            speaker_id
            for entry in round_history[-3:]
            for speaker_id in (entry.get('speaker_ids') or [])
        ]
        responder_indexes = await self._select_responder_indexes(
            request.question, actors, participants, recent_speaker_ids
        )
        for turn_index, actor_index in enumerate(responder_indexes, start=1):
            participant = participants[actor_index]
            actor = actors[actor_index]
            if actor['type'] == 'builtin_person':
                person = actor['value']
                profile = self._profile(person.id)
                chunks = self.retrieval.retrieve_for_person(person, request.question)
                system = build_persona_system_prompt(
                    person_name=person.chinese_name,
                    person_slug=person.slug,
                    profile=self._serialize_profile(profile),
                    retrieved_chunks=[self._chunk_dict(item) for item in chunks],
                )
                speaker_slug, speaker_name = person.slug, person.chinese_name
                citations = [self._chunk_schema(item) for item in chunks]
            elif actor['type'] == 'speaker_card':
                card = actor['value']
                system = self._speaker_card_prompt(card)
                speaker_slug, speaker_name = card.id, card.display_name
                citations = []
            else:
                coach = actor['value']
                system = self._coach_prompt(coach['id'])
                speaker_slug, speaker_name = coach['id'], coach['name']
                citations = []
            prompt = (
                f'用户问题：{request.question}\n'
                f'你在圆桌中的角色：{ROLE_LABELS.get(participant.role, participant.role)}。\n'
                f'本轮任务：{participant.task}\n'
                f'已有会话摘要：{summary.summary if summary else "无"}\n'
                f'相关用户长期记忆：{memory_context or "无"}\n'
                f'前面发言：{chr(10).join(previous) if previous else "无"}\n'
                '请直接给出有根据、可行动的中文回答；如需反驳，请明确指出分歧。'
                '本轮发言必须控制在200个汉字或字符以内。'
            )
            answer = await self.llm.chat(
                [{'role': 'system', 'content': system}, {'role': 'user', 'content': prompt}],
                temperature=0.65,
                max_tokens=700,
            )
            answer = self._limit_reply(answer)
            turn = RoundtableTurnResponse(
                turn_index=turn_index,
                speaker_slug=speaker_slug,
                speaker_name=speaker_name,
                speaker_role=participant.role,
                task=participant.task,
                content=answer,
                citations=citations,
            )
            turns.append(turn)
            previous.append(f'{speaker_name}：{answer}')
            self._store_turn(session.id, turn)

        round_history.append({
            'round': round_number,
            'question': request.question,
            'viewpoints': previous,
            'speaker_ids': [turn.speaker_slug for turn in turns if turn.speaker_slug],
        })
        round_history = round_history[-5:]
        final_answer = ''
        available_viewpoints = [item for entry in round_history for item in (entry.get('viewpoints') or [])]
        if round_number % 5 == 0 and available_viewpoints:
            synthesis_prompt = (
                '你是智囊圆桌主持人。现在是第五轮复盘。只能基于最近五轮已经出现的观点，'
                '提炼共识、关键分歧与下一步；没有出现的观点不得补写。总结控制在200个字符以内。\n'
                f'最近五轮：{json.dumps(round_history, ensure_ascii=False)}'
            )
            final_answer = await self.llm.chat(
                [{'role': 'system', 'content': synthesis_prompt}], temperature=0.35, max_tokens=500
            )
            final_answer = self._limit_reply(final_answer)
            moderator = RoundtableTurnResponse(
                turn_index=len(turns) + 1, speaker_slug='moderator', speaker_name='主持人',
                speaker_role='moderator', task='五轮观点总结', content=final_answer, citations=[],
            )
            turns.append(moderator)
            self._store_turn(session.id, moderator)
        session.topic_analysis = {**session.topic_analysis, 'round_history': round_history}
        self._store_message(session.id, 'user', None, user_memory_text)
        if final_answer:
            self._store_message(session.id, 'assistant', 'moderator', final_answer)

        maintained = await self.memory.maybe_maintain(request.user_id, session.id, user_memory_text)
        self.db.commit()
        return RoundtableResponse(
            conversation_id=session.id,
            plan=plan,
            turns=turns,
            final_answer=final_answer,
            memory=RoundtableMemoryState(
                summary=maintained.summary if maintained else '',
                open_questions=maintained.open_questions if maintained else [],
                decisions=maintained.decisions if maintained else [],
                memory_highlights=maintained.memory_highlights if maintained else [],
                user_memories=[item.content for item in recalled],
            ),
        )

    def _session(self, request: RoundtableRequest) -> ConversationSession:
        if request.conversation_id:
            existing = self.db.scalar(select(ConversationSession).where(ConversationSession.id == request.conversation_id))
            if existing:
                existing.mode = 'roundtable'
                return existing
        row = ConversationSession(id=str(uuid4()), mode='roundtable', selected_people=[], topic_analysis={})
        self.db.add(row)
        self.db.flush()
        return row

    def _select_people(self, request: RoundtableRequest) -> list[Person]:
        slugs = list(dict.fromkeys(request.preferred_people))
        recommended = self.recommend.recommend(
            RecommendRequest(question=request.question[:1800], top_k=max(request.max_participants, 4))
        ).recommendations
        slugs.extend(item.person_slug for item in recommended if item.person_slug not in slugs)
        result: list[Person] = []
        for slug in slugs:
            person = self.db.scalar(select(Person).where(Person.slug == slug, Person.status == 'active'))
            if person:
                result.append(person)
            if len(result) >= request.max_participants:
                break
        return result

    def _select_actors(self, request: RoundtableRequest) -> list[dict]:
        actors: list[dict] = []
        seen: set[tuple[str, str]] = set()
        coaches = self._coach_roles()
        for ref in request.participant_refs:
            key = (ref.type, ref.id)
            if key in seen:
                continue
            if ref.type == 'builtin_person':
                value = self.db.scalar(select(Person).where(Person.slug == ref.id, Person.status == 'active'))
            elif ref.type == 'speaker_card':
                value = self.db.scalar(select(SpeakerCard).where(
                    SpeakerCard.id == ref.id,
                    SpeakerCard.user_id == request.user_id,
                ))
            else:
                value = coaches.get(ref.id)
            if value:
                actors.append({'type': ref.type, 'value': value})
                seen.add(key)
            if len(actors) >= request.max_participants:
                return actors
        for person in self._select_people(request):
            key = ('builtin_person', person.slug)
            if key not in seen:
                actors.append({'type': 'builtin_person', 'value': person})
                seen.add(key)
            if len(actors) >= request.max_participants:
                break
        return actors

    def _participants(self, actors: list[dict]) -> list[RoundtableParticipant]:
        roles = ['primary_responder', 'challenger', 'complement', 'critic']
        tasks = [
            '从你的核心专长出发提出主判断和可执行建议。',
            '检查主判断的假设、证据和潜在风险，提出必要反驳。',
            '补充被忽略的视角，并把观点连接到现实行动。',
            '指出论证盲点、适用边界和可能失败的条件。',
        ]
        result: list[RoundtableParticipant] = []
        for index, actor in enumerate(actors[:4]):
            value = actor['value']
            if actor['type'] == 'builtin_person':
                participant_id, name = value.slug, value.chinese_name
                reason = f'{value.domain_category} · {value.ai_archetype}'
            elif actor['type'] == 'speaker_card':
                participant_id, name = value.id, value.display_name
                reason = f'学习型表达角色卡 · {value.role_title}'
            else:
                participant_id, name = value['id'], value['name']
                reason = f'教练角色 · {value["focus"]}'
            result.append(RoundtableParticipant(
                participant_type=actor['type'], participant_id=participant_id,
                person_slug=participant_id, person_name=name, role=roles[index],
                task=tasks[index], selection_reason=reason,
            ))
        return result

    async def _select_responder_indexes(
        self,
        question: str,
        actors: list[dict],
        participants: list[RoundtableParticipant],
        recent_speaker_ids: list[str],
    ) -> list[int]:
        participant_ids = [
            participant.participant_id or participant.person_slug or str(index)
            for index, participant in enumerate(participants)
        ]
        recent_counts = {
            participant_id: recent_speaker_ids.count(participant_id)
            for participant_id in set(recent_speaker_ids)
        }
        candidates = [
            {
                'index': index,
                'name': participant.person_name,
                'type': participant.participant_type,
                'expertise': participant.selection_reason,
                'role': ROLE_LABELS.get(participant.role, participant.role),
                'recent_appearances': recent_counts.get(participant_ids[index], 0),
            }
            for index, participant in enumerate(participants)
        ]
        prompt = (
            '你是圆桌发言调度器。让每位候选人独立判断：这个问题是否真的需要自己回应。'
            '先判断问题与其人物设定、材料观点、专业领域或教练职责是否匹配；不匹配必须沉默。'
            '只有能提供新增观点、必要质疑或专业补充时才回应。相关度相近时优先最近较少发言的人，'
            '但不能为了轮换牺牲人设匹配。只要有两人都符合人设且能提供不同的有效观点，就选择2人；'
            '只有确实仅一人匹配时才选择1人。最多选择2人。必须为每名候选人输出决定。仅输出JSON：'
            '{"decisions":[{"index":0,"respond":true,"relevance":0.9,"persona_fit":0.9,"reason":"..."}]}。'
            f'\n问题：{question}\n候选人：{json.dumps(candidates, ensure_ascii=False)}'
        )
        try:
            raw = await self.llm.chat([{'role': 'system', 'content': prompt}], temperature=0.1, max_tokens=500)
            start, end = raw.find('{'), raw.rfind('}')
            data = json.loads(raw[start:end + 1]) if start >= 0 and end > start else {}
            decisions = data.get('decisions') if isinstance(data, dict) else None
            if not isinstance(decisions, list):
                raise ValueError('Missing routing decisions')
            ranked = sorted(
                (
                    (
                        int(item.get('index')),
                        0.7 * float(item.get('relevance') or 0)
                        + 0.3 * float(item.get('persona_fit') or item.get('relevance') or 0)
                        - 0.22 * min(
                            recent_counts.get(participant_ids[int(item.get('index'))], 0), 2
                        ),
                    )
                    for item in decisions
                    if item.get('respond') is True and str(item.get('index', '')).isdigit()
                    and 0 <= int(item.get('index')) < len(actors)
                    and float(item.get('persona_fit') or item.get('relevance') or 0) >= 0.55
                ),
                key=lambda item: item[1],
                reverse=True,
            )
            selected = list(dict.fromkeys(index for index, _ in ranked))[:2]
            return selected
        except (ValueError, TypeError, json.JSONDecodeError, HTTPException):
            pass
        if not actors:
            return []
        return [min(range(len(actors)), key=lambda index: recent_counts.get(participant_ids[index], 0))]

    def _speaker_card_prompt(self, card: SpeakerCard) -> str:
        profile = {
            'role_title': card.role_title,
            'core_claims': card.core_claims,
            'speaking_style': card.speaking_style,
            'thinking_style': card.thinking_style,
            'rhetorical_patterns': card.rhetorical_patterns,
            'useful_quotes': card.useful_quotes,
            'discussion_topics': card.discussion_topics,
            'limitations': card.limitations,
        }
        return (
            f'你是“{card.display_name}”学习型表达角色卡，不是真人，也不得声称代表或复刻视频中的人物。\n'
            f'你只能依据这张卡片概括出的内容与表达方法参与学习讨论。\n角色卡：{profile}\n'
            '若问题超出材料范围，明确说明限制；不要虚构经历、立场、身份或原话。'
        )

    def _coach_roles(self) -> dict[str, dict[str, str]]:
        return {
            'english_expression_coach': {'id': 'english_expression_coach', 'name': '英语表达教练', 'focus': '英语表达的清晰度、结构与语感'},
            'critical_thinking_coach': {'id': 'critical_thinking_coach', 'name': '批判性思维教练', 'focus': '论证、证据、假设与反例'},
            'peer_audience': {'id': 'peer_audience', 'name': '同龄人听众', 'focus': '可理解性、共鸣与真实听众反馈'},
        }

    def _coach_prompt(self, coach_id: str) -> str:
        coach = self._coach_roles()[coach_id]
        return (
            f'你是{coach["name"]}，关注{coach["focus"]}。'
            '你是功能性学习教练角色，不冒充任何真人。给出具体、友善、可操作的反馈。'
        )

    def _limit_reply(self, content: str, limit: int = 200) -> str:
        cleaned = content.strip()
        return cleaned if len(cleaned) <= limit else f'{cleaned[:limit - 1].rstrip()}…'

    def _profile(self, person_id: str) -> PersonaProfile:
        row = self.db.scalar(
            select(PersonaProfile).where(PersonaProfile.person_id == person_id).order_by(desc(PersonaProfile.version))
        )
        if not row:
            raise HTTPException(status_code=404, detail='人物画像不存在。')
        return row

    def _serialize_profile(self, profile: PersonaProfile) -> dict:
        return {
            'identity': profile.identity, 'core_traits': profile.core_traits,
            'thinking_style': profile.thinking_style, 'speaking_style': profile.speaking_style,
            'values': profile.values, 'blind_spots': profile.blind_spots,
            'taboos': profile.taboos, 'preferred_topics': profile.preferred_topics,
            'disallowed_claims': profile.disallowed_claims,
            'response_strategy': profile.response_strategy, 'prompt_contract': profile.prompt_contract,
        }

    def _store_turn(self, session_id: str, turn: RoundtableTurnResponse) -> None:
        self.db.add(RoundtableTurn(
            id=str(uuid4()), session_id=session_id, turn_index=turn.turn_index,
            speaker_slug=turn.speaker_slug, speaker_role=turn.speaker_role,
            task=turn.task, content=turn.content,
            citations=[item.model_dump() for item in turn.citations], metadata_json={'speaker_name': turn.speaker_name},
        ))

    def _store_message(self, session_id: str, role: str, person_slug: Optional[str], content: str) -> None:
        self.db.add(ChatMessage(
            id=str(uuid4()), session_id=session_id, role=role, person_slug=person_slug,
            content=content, retrieved_chunks=None, metadata_json={},
        ))

    def _chunk_dict(self, item) -> dict:
        return {'chunk_type': item.chunk_type, 'title': item.title, 'source_name': item.source_name,
                'score': item.score, 'excerpt': item.excerpt, 'content': item.content}

    def _chunk_schema(self, item):
        from app.schemas.chat import RetrievedChunk
        return RetrievedChunk(chunk_type=item.chunk_type, title=item.title, source_name=item.source_name,
                              score=item.score, excerpt=item.excerpt)
