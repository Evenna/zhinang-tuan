from __future__ import annotations

import json
from uuid import uuid4
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from fastapi import HTTPException

from app.core.prompts import build_persona_system_prompt
from app.db.models import ChatMessage, ConversationSession, Person, PersonaProfile
from app.schemas.chat import ChatRequest, ChatResponse, GroupAdvisorAnswer, GroupChatRequest, GroupChatResponse, RetrievedChunk
from app.services.llm import DeepSeekService
from app.services.memory import MemoryService
from app.services.recommend import RecommendService
from app.services.retrieval import RetrievalService


class ChatService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.retrieval_service = RetrievalService(db)
        self.recommend_service = RecommendService(db)
        self.llm_service = DeepSeekService()
        self.memory_service = MemoryService(db)

    async def respond(self, request: ChatRequest) -> ChatResponse:
        person = self._get_person(request.person_slug)
        profile = self._get_profile(person.id)
        if not profile:
            raise HTTPException(status_code=404, detail='Persona profile not found')

        session = self._get_or_create_session(request.conversation_id, mode='single', selected_people=[person.slug])
        session.topic_analysis = {**(session.topic_analysis or {}), 'user_id': request.user_id}
        retrieved = self.retrieval_service.retrieve_for_person(person, request.question)
        system_prompt = build_persona_system_prompt(
            person_name=person.chinese_name,
            person_slug=person.slug,
            profile=self._serialize_profile(profile),
            retrieved_chunks=[self._retrieved_to_dict(item) for item in retrieved],
        )
        messages = [{'role': 'system', 'content': system_prompt}]
        memory_context, _ = self.memory_service.context(request.user_id, session.id, request.question)
        if memory_context:
            messages.append({'role': 'system', 'content': memory_context})
        messages.extend(self._conversation_history(session.id, request.history, limit=8))
        messages.append({'role': 'user', 'content': self._build_concise_user_prompt(request.question)})
        answer = await self.llm_service.chat(messages, temperature=0.65, max_tokens=120)

        self._store_message(session.id, 'user', None, request.question, None)
        self._store_message(
            session.id,
            'assistant',
            person.slug,
            answer,
            [self._retrieved_to_dict(item) for item in retrieved],
        )
        await self.memory_service.maybe_maintain(request.user_id, session.id, request.question)
        self.db.commit()

        return ChatResponse(
            conversation_id=session.id,
            person_slug=person.slug,
            person_name=person.chinese_name,
            answer=answer,
            citations=[self._retrieved_to_schema(item) for item in retrieved],
        )

    async def group_respond(self, request: GroupChatRequest) -> GroupChatResponse:
        person_slugs = request.person_slugs
        if not person_slugs:
            recommended = self.recommend_service.recommend(
                type('RecommendReq', (), {'question': request.question, 'top_k': request.top_k})()
            )
            person_slugs = [item.person_slug for item in recommended.recommendations]

        session = self._get_or_create_session(request.conversation_id, mode='group', selected_people=person_slugs)
        topic_state = dict(session.topic_analysis or {})
        round_number = int(topic_state.get('round_count') or 0) + 1
        session.topic_analysis = {**topic_state, 'user_id': request.user_id, 'round_count': round_number}
        group_history = list(topic_state.get('group_history') or [])
        recent_speakers = [
            slug
            for entry in group_history[-3:]
            for slug in (entry.get('speaker_slugs') or [])
        ]
        candidates: list[tuple[Person, PersonaProfile]] = []
        for slug in person_slugs:
            person = self._get_person(slug)
            profile = self._get_profile(person.id)
            if profile:
                candidates.append((person, profile))
        selected_slugs = await self._select_group_responders(request.question, candidates, recent_speakers)
        answers: list[GroupAdvisorAnswer] = []
        for person, profile in candidates:
            if person.slug not in selected_slugs:
                continue
            retrieved = self.retrieval_service.retrieve_for_person(person, request.question)
            system_prompt = build_persona_system_prompt(
                person_name=person.chinese_name,
                person_slug=person.slug,
                profile=self._serialize_profile(profile),
                retrieved_chunks=[self._retrieved_to_dict(item) for item in retrieved],
            )
            messages = [{'role': 'system', 'content': system_prompt}]
            memory_context, _ = self.memory_service.context(request.user_id, session.id, request.question)
            if memory_context:
                messages.append({'role': 'system', 'content': memory_context})
            messages.extend(self._conversation_history(session.id, request.history, limit=6))
            messages.append({
                'role': 'user',
                'content': f'{request.question}\n你已判断自己有必要回应。请只提供新增观点，控制在200个字符以内。',
            })
            answer = await self.llm_service.chat(messages, temperature=0.85)
            normalized_answer = answer.strip().strip('"“”')
            if normalized_answer.startswith(person.chinese_name):
                normalized_answer = normalized_answer[len(person.chinese_name):].lstrip('：:,，、 -')
            if normalized_answer.lower() in {'沉默', '不回答', 'pass', 'skip'}:
                continue
            answer = self._limit_reply(answer)
            answers.append(
                GroupAdvisorAnswer(
                    person_slug=person.slug,
                    person_name=person.chinese_name,
                    answer=answer,
                    citations=[self._retrieved_to_schema(item) for item in retrieved],
                )
            )
            self._store_message(session.id, 'assistant', person.slug, answer, [self._retrieved_to_dict(item) for item in retrieved])

        self._store_message(session.id, 'user', None, request.question, None)

        group_history.append({
            'round': round_number,
            'question': request.question,
            'viewpoints': [f'{item.person_name}：{item.answer}' for item in answers],
            'speaker_slugs': [item.person_slug for item in answers],
        })
        group_history = group_history[-5:]
        synthesis = ''
        available_viewpoints = [item for entry in group_history for item in (entry.get('viewpoints') or [])]
        if round_number % 5 == 0 and available_viewpoints:
            synthesis = await self.llm_service.chat(
                [
                    {
                        'role': 'system',
                        'content': '你是圆桌主持人。第五轮后才总结，只依据最近五轮已出现的观点，提炼共识、分歧和下一步，控制在200个字符以内。',
                    },
                    {'role': 'user', 'content': json.dumps(group_history, ensure_ascii=False)},
                ],
                temperature=0.4,
                max_tokens=500,
            )
            synthesis = self._limit_reply(synthesis)
            self._store_message(session.id, 'assistant', 'moderator', synthesis, None)
        session.topic_analysis = {**session.topic_analysis, 'group_history': group_history}
        await self.memory_service.maybe_maintain(request.user_id, session.id, request.question)
        self.db.commit()

        return GroupChatResponse(
            conversation_id=session.id,
            selected_people=person_slugs,
            answers=answers,
            synthesis=synthesis,
        )

    def _get_person(self, slug: str) -> Person:
        person = self.db.scalar(select(Person).where(Person.slug == slug))
        if not person:
            raise HTTPException(status_code=404, detail=f'Person not found: {slug}')
        return person

    def _get_profile(self, person_id: str) -> Optional[PersonaProfile]:
        return self.db.scalar(
            select(PersonaProfile)
            .where(PersonaProfile.person_id == person_id)
            .order_by(desc(PersonaProfile.version))
        )

    def _get_or_create_session(self, conversation_id: Optional[str], *, mode: str, selected_people: list[str]) -> ConversationSession:
        if conversation_id:
            session = self.db.scalar(select(ConversationSession).where(ConversationSession.id == conversation_id))
            if session:
                return session
        session = ConversationSession(
            id=str(uuid4()),
            mode=mode,
            selected_people=selected_people,
            topic_analysis={},
        )
        self.db.add(session)
        self.db.flush()
        return session

    def _store_message(
        self,
        session_id: str,
        role: str,
        person_slug: Optional[str],
        content: str,
        retrieved_chunks: Optional[list[dict]],
    ) -> None:
        self.db.add(
            ChatMessage(
                id=str(uuid4()),
                session_id=session_id,
                role=role,
                person_slug=person_slug,
                content=content,
                retrieved_chunks=retrieved_chunks,
                metadata_json={},
            )
        )

    def _conversation_history(self, session_id: str, supplied_history: list, *, limit: int) -> list[dict[str, str]]:
        if supplied_history:
            return [{'role': turn.role, 'content': turn.content} for turn in supplied_history[-limit:]]
        rows = list(
            self.db.scalars(
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(desc(ChatMessage.created_at))
                .limit(limit)
            ).all()
        )
        rows.reverse()
        return [
            {'role': row.role if row.role in {'user', 'assistant'} else 'assistant', 'content': row.content}
            for row in rows
        ]

    def _serialize_profile(self, profile: PersonaProfile) -> dict:
        return {
            'identity': profile.identity,
            'core_traits': profile.core_traits,
            'thinking_style': profile.thinking_style,
            'speaking_style': profile.speaking_style,
            'values': profile.values,
            'blind_spots': profile.blind_spots,
            'taboos': profile.taboos,
            'preferred_topics': profile.preferred_topics,
            'disallowed_claims': profile.disallowed_claims,
            'response_strategy': profile.response_strategy,
            'prompt_contract': profile.prompt_contract,
        }

    def _build_concise_user_prompt(self, question: str) -> str:
        return (
            f'{question}\n\n'
            '请直接回答这个问题，使用中文，只写 1 到 2 句，尽量控制在 50 字内。'
            '语气要像这位人物本人，内容具体，不要分点，不要长篇分析，不要客套开场。'
        )

    async def _select_group_responders(
        self,
        question: str,
        candidates: list[tuple[Person, PersonaProfile]],
        recent_speakers: list[str],
    ) -> list[str]:
        recent_counts = {slug: recent_speakers.count(slug) for slug in set(recent_speakers)}
        roster = [
            {
                'slug': person.slug,
                'name': person.chinese_name,
                'domain': person.domain_category,
                'archetype': person.ai_archetype,
                'topics': profile.preferred_topics,
                'recent_appearances': recent_counts.get(person.slug, 0),
            }
            for person, profile in candidates
        ]
        prompt = (
            '你是圆桌发言调度器。让名单中每个人判断是否需要回答用户问题。'
            '先判断问题是否符合人物的领域、经历、思维方式和表达角色；人设不匹配必须沉默。'
            '只有能提供新增观点、专业判断或必要反驳的人才回答。相关度相近时，优先最近较少发言的人；'
            '但不能为了轮换让不相关的人硬说。只要有两人都符合人设且能提供不同的有效观点，就选择2人；'
            '只有确实仅一人匹配时才选择1人。最多选择2人。必须为每名候选人输出决定。仅输出JSON：'
            '{"decisions":[{"slug":"...","respond":true,"relevance":0.9,"persona_fit":0.9,"reason":"..."}]}。'
            f'\n问题：{question}\n候选：{json.dumps(roster, ensure_ascii=False)}'
        )
        try:
            raw = await self.llm_service.chat(
                [{'role': 'system', 'content': prompt}], temperature=0.1, max_tokens=500
            )
            start, end = raw.find('{'), raw.rfind('}')
            data = json.loads(raw[start:end + 1]) if start >= 0 and end > start else {}
            allowed = {person.slug for person, _ in candidates}
            decisions = data.get('decisions') if isinstance(data, dict) else None
            if not isinstance(decisions, list):
                raise ValueError('Missing routing decisions')
            ranked = sorted(
                (
                    (
                        str(item.get('slug')),
                        0.7 * float(item.get('relevance') or 0)
                        + 0.3 * float(item.get('persona_fit') or item.get('relevance') or 0)
                        - 0.22 * min(recent_counts.get(str(item.get('slug')), 0), 2),
                    )
                    for item in decisions
                    if item.get('respond') is True and str(item.get('slug')) in allowed
                    and float(item.get('persona_fit') or item.get('relevance') or 0) >= 0.55
                ),
                key=lambda item: item[1],
                reverse=True,
            )
            selected = list(dict.fromkeys(slug for slug, _ in ranked))[:2]
            return selected
        except (ValueError, TypeError, json.JSONDecodeError, HTTPException):
            pass
        if not candidates:
            return []
        return [min(candidates, key=lambda item: recent_counts.get(item[0].slug, 0))[0].slug]

    def _limit_reply(self, content: str, limit: int = 200) -> str:
        cleaned = content.strip()
        return cleaned if len(cleaned) <= limit else f'{cleaned[:limit - 1].rstrip()}…'

    def _retrieved_to_dict(self, item) -> dict:
        return {
            'chunk_type': item.chunk_type,
            'title': item.title,
            'source_name': item.source_name,
            'score': item.score,
            'excerpt': item.excerpt,
            'content': item.content,
        }

    def _retrieved_to_schema(self, item) -> RetrievedChunk:
        return RetrievedChunk(
            chunk_type=item.chunk_type,
            title=item.title,
            source_name=item.source_name,
            score=item.score,
            excerpt=item.excerpt,
        )
