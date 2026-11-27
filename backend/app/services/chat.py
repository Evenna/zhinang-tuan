from __future__ import annotations

from uuid import uuid4
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from fastapi import HTTPException

from app.core.prompts import (
    build_group_synthesis_prompt,
    build_persona_system_prompt,
    build_roundtable_invite_prompt,
    build_roundtable_turn_prompt,
)
from app.db.models import ChatMessage, ConversationSession, Person, PersonaProfile
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ConversationTurn,
    GroupAdvisorAnswer,
    GroupChatRequest,
    GroupChatResponse,
    GroupInvite,
    RetrievedChunk,
)
from app.schemas.recommend import RecommendRequest
from app.services.llm import MiniMaxService
from app.services.longform import pick_long, long_clause, finish_sentences
from app.services.recommend import RecommendService, person_name_aliases, text_mentions_alias
from app.services.retrieval import RetrievalService
from app.utils.text import finalize_complete_sentence

MAX_ROUNDTABLE_SEATS = 6
MAX_INVITES_PER_TURN = 2


class ChatService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.retrieval_service = RetrievalService(db)
        self.recommend_service = RecommendService(db)
        self.llm_service = MiniMaxService()

    async def respond(self, request: ChatRequest) -> ChatResponse:
        person = self._get_person(request.person_slug)
        profile = self._get_profile(person.id)
        if not profile:
            raise HTTPException(status_code=404, detail='Persona profile not found')

        session = self._get_or_create_session(request.conversation_id, mode='single', selected_people=[person.slug])
        retrieved = self.retrieval_service.retrieve_for_person(person, request.question)
        system_prompt = build_persona_system_prompt(
            person_name=person.english_name,
            person_slug=person.slug,
            profile=self._serialize_profile(profile),
            retrieved_chunks=[self._retrieved_to_dict(item) for item in retrieved],
        )
        messages = [{'role': 'system', 'content': system_prompt}]
        for turn in request.history[-6:]:
            messages.append({'role': turn.role, 'content': turn.content})
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
        self.db.commit()

        return ChatResponse(
            conversation_id=session.id,
            person_slug=person.slug,
            person_name=person.english_name,
            answer=answer,
            citations=[self._retrieved_to_schema(item) for item in retrieved],
        )

    async def group_respond(self, request: GroupChatRequest) -> GroupChatResponse:
        person_slugs = list(dict.fromkeys(request.person_slugs))
        if not person_slugs:
            recommended = await self.recommend_service.recommend(
                RecommendRequest(question=request.question, top_k=request.top_k)
            )
            person_slugs = [item.person_slug for item in recommended.recommendations]

        invites = await self._resolve_invites(request, person_slugs)
        invited_slugs = [item.person_slug for item in invites]
        person_slugs = list(dict.fromkeys(person_slugs + invited_slugs))[:MAX_ROUNDTABLE_SEATS]
        invited_slugs = [slug for slug in invited_slugs if slug in person_slugs]
        invites = [item for item in invites if item.person_slug in invited_slugs]

        session = self._get_or_create_session(request.conversation_id, mode='group', selected_people=person_slugs)
        answers: list[GroupAdvisorAnswer] = []
        for slug in person_slugs:
            person = self._get_person(slug)
            profile = self._get_profile(person.id)
            if not profile:
                continue
            retrieved = self.retrieval_service.retrieve_for_person(person, request.question)
            system_prompt = build_persona_system_prompt(
                person_name=person.english_name,
                person_slug=person.slug,
                profile=self._serialize_profile(profile),
                retrieved_chunks=[self._retrieved_to_dict(item) for item in retrieved],
            )
            messages = [{'role': 'system', 'content': system_prompt}]
            for turn in request.history[-4:]:
                messages.append({'role': turn.role, 'content': turn.content})
            messages.append({
                'role': 'user',
                'content': build_roundtable_turn_prompt(
                    request.question,
                    person.chinese_name,
                    newly_invited=slug in invited_slugs,
                ),
            })
            raw_answer = await self.llm_service.chat(messages, temperature=0.7, max_tokens=80)
            normalized_answer = raw_answer.strip().strip('"“”')
            if normalized_answer.startswith(person.chinese_name):
                normalized_answer = normalized_answer[len(person.chinese_name):].lstrip('：:,，、 -')
            if normalized_answer.lower() in {'沉默', '不回答', 'pass', 'skip'}:
                continue
            speech = finalize_complete_sentence(normalized_answer, max_chars=240)
            if not speech:
                continue
            answers.append(
                GroupAdvisorAnswer(
                    person_slug=person.slug,
                    person_name=person.english_name,
                    answer=speech,
                    citations=[self._retrieved_to_schema(item) for item in retrieved],
                )
            )
            self._store_message(session.id, 'assistant', person.slug, speech, [self._retrieved_to_dict(item) for item in retrieved])

        self._store_message(session.id, 'user', None, request.question, None)
        for invite in invites:
            self._store_message(session.id, 'assistant', 'moderator', invite.host_line, None)

        synthesis = await self.llm_service.chat(
            [
                {
                    'role': 'system',
                    'content': 'You are a synthesis layer for multiple advisors. Reply in one complete English sentence, no more than 25 words. No ellipsis, and do not cut the sentence in half.',
                },
                {'role': 'user', 'content': build_group_synthesis_prompt(request.question, [item.model_dump() for item in answers])},
            ],
            temperature=0.5,
            max_tokens=80,
        )
        synthesis = finalize_complete_sentence(synthesis, max_chars=240) or synthesis.strip()
        self._store_message(session.id, 'assistant', 'moderator', synthesis, None)
        self.db.commit()

        return GroupChatResponse(
            conversation_id=session.id,
            selected_people=person_slugs,
            answers=answers,
            synthesis=synthesis,
            invited=invites,
        )

    # ── Sequential roundtable: one speaker per call, each hears the ones before ──
    async def roundtable_prepare(self, request) -> dict:
        seats = list(dict.fromkeys(request.person_slugs))
        history = [ConversationTurn(role='user' if line.speaker == 'user' else 'assistant', content=line.text[:20000]) for line in request.transcript[-6:]]
        invites = await self._resolve_invites(
            GroupChatRequest(question=request.question, person_slugs=seats, history=history, conversation_id=request.conversation_id),
            seats,
        )
        invites = invites[: max(0, MAX_ROUNDTABLE_SEATS - len(seats))]
        session = self._get_or_create_session(request.conversation_id, mode='group', selected_people=seats + [i.person_slug for i in invites])
        self._store_message(session.id, 'user', None, request.question, None)
        for invite in invites:
            self._store_message(session.id, 'assistant', 'moderator', invite.host_line, None)
        self.db.commit()
        return {'conversation_id': session.id, 'invited': [i.model_dump() for i in invites]}

    async def roundtable_turn(self, request) -> dict:
        seats = list(dict.fromkeys(request.person_slugs))
        if request.speaker not in seats:
            raise HTTPException(status_code=400, detail='That advisor is not at the table.')
        person = self._get_person(request.speaker)
        profile = self._get_profile(person.id)
        if not profile:
            raise HTTPException(status_code=404, detail='No profile for this advisor.')
        names = {}
        for slug in seats:
            try:
                names[slug] = self._get_person(slug).english_name
            except HTTPException:
                names[slug] = slug
        retrieved = self.retrieval_service.retrieve_for_person(person, request.question)
        system_prompt = build_persona_system_prompt(
            person_name=person.english_name,
            person_slug=person.slug,
            profile=self._serialize_profile(profile),
            retrieved_chunks=[self._retrieved_to_dict(item) for item in retrieved],
        )
        lines = []
        for line in request.transcript[-14:]:
            who = 'The guest' if line.speaker == 'user' else ('Host' if line.speaker == 'moderator' else (line.name or names.get(line.speaker, line.speaker)))
            lines.append(f'{who}: {line.text}')
        others = ', '.join(names[s] for s in seats if s != request.speaker) or 'nobody else'
        said_this_round = bool(request.transcript) and request.transcript[-1].speaker != 'user'
        guidance = (
            'Others have just spoken. Do not repeat them: respond to the last speaker by name if useful — agree, push back, or add what only you can add.'
            if said_this_round else
            'You speak first. Answer the guest directly from your own life.'
        )
        passing = (
            ' You do NOT have to speak. Only speak if you have something genuinely new, a real disagreement, or it touches your own life; otherwise output only: pass'
            if request.allow_pass else ''
        )
        go_long = pick_long(person.slug, [line.text for line in request.transcript] + [request.question])
        user_msg = (
            f'You are {person.english_name}, {"just invited to join" if request.newly_invited else "seated at"} a small roundtable with {others}. '
            'A guest has brought a personal question. Speak as yourself, warmly but with conviction, in English, '
            'one or two complete sentences, at most 45 words, no ellipses, no lists, no speaker label. Only address or name people who have already spoken in the conversation below.'
            + (' ' + long_clause() if go_long else '') +
            f'{passing}\n\nCONVERSATION SO FAR:\n' + ('\n'.join(lines) or '(nothing yet)')
            + f'\n\nThe guest\'s latest words: "{request.question}"\n{guidance}'
        )
        try:
            raw = await self.llm_service.chat(
                [{'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': user_msg}],
                temperature=0.8, max_tokens=420 if go_long else 160,
            )
        except HTTPException as exc:
            raise HTTPException(status_code=502, detail='The table fell quiet. Try again in a moment.') from exc
        text = ' '.join(str(raw or '').split()).strip().strip('"“”')
        for prefix in (person.english_name, person.chinese_name):
            if prefix and text.startswith(prefix):
                text = text[len(prefix):].lstrip('：:,， -').strip()
        if not text or text.lower().strip('. ') in {'pass', 'skip', 'silence'}:
            if request.allow_pass:
                return {'answer': None, 'speaker': person.slug}
            text = ''
        if text and go_long and len(text.split()) > 50:
            speech = finish_sentences(text, max_chars=1200)
        else:
            speech = finish_sentences(text, max_chars=360) if text else ''
        if not speech:
            if request.allow_pass:
                return {'answer': None, 'speaker': person.slug}
            raise HTTPException(status_code=502, detail='The table fell quiet. Try again in a moment.')
        if request.conversation_id:
            session = self.db.scalar(select(ConversationSession).where(ConversationSession.id == request.conversation_id))
            if session:
                self._store_message(session.id, 'assistant', person.slug, speech, [self._retrieved_to_dict(item) for item in retrieved])
                self.db.commit()
        return {'answer': {'person_slug': person.slug, 'person_name': person.english_name, 'answer': speech}, 'speaker': person.slug}

    async def roundtable_synthesis(self, request) -> dict:
        answers = [{'person_name': line.name or line.speaker, 'answer': line.text} for line in request.transcript if line.speaker not in ('user', 'moderator')][-8:]
        if not answers:
            return {'synthesis': ''}
        raw = await self.llm_service.chat(
            [
                {'role': 'system', 'content': 'You are the quiet host of a roundtable. Reply in one complete English sentence, no more than 30 words. No ellipsis.'},
                {'role': 'user', 'content': build_group_synthesis_prompt(request.question, answers)},
            ],
            temperature=0.5, max_tokens=90,
        )
        synthesis = finalize_complete_sentence(raw, max_chars=260) or str(raw or '').strip()
        return {'synthesis': synthesis}

    async def _resolve_invites(self, request: GroupChatRequest, seated_slugs: list[str]) -> list[GroupInvite]:
        remaining_seats = MAX_ROUNDTABLE_SEATS - len(seated_slugs)
        if remaining_seats <= 0:
            return []

        people = self.db.scalars(select(Person).order_by(Person.chinese_name)).all()
        by_slug = {person.slug: person for person in people}
        seated = set(seated_slugs)
        mention_text = '\n'.join(
            [request.question] + [turn.content for turn in request.history[-6:] if turn.content]
        )
        invites: list[GroupInvite] = []
        seen: set[str] = set()

        for person in people:
            if person.slug in seated or person.slug in seen:
                continue
            if not any(text_mentions_alias(mention_text, alias) for alias in person_name_aliases(person)):
                continue
            if not self._get_profile(person.id):
                continue
            invites.append(
                GroupInvite(
                    person_slug=person.slug,
                    person_name=person.english_name,
                    host_line=f'The discussion mentioned {person.english_name}, so I invited them to join.',
                )
            )
            seen.add(person.slug)
            if len(invites) >= min(MAX_INVITES_PER_TURN, remaining_seats):
                break

        if len(invites) >= min(MAX_INVITES_PER_TURN, remaining_seats):
            return invites[:remaining_seats]

        roster_people = [person for person in people if person.slug not in seated and person.slug not in seen]
        if not roster_people:
            return invites

        seated_names = '、'.join(by_slug[slug].chinese_name for slug in seated_slugs if slug in by_slug)
        roster = '\n'.join(f'{person.slug}\t{person.chinese_name}\t{person.english_name}' for person in roster_people)
        history_text = '\n'.join(f'{turn.role}: {turn.content}' for turn in request.history[-6:])
        try:
            payload = await self.llm_service.chat_json(
                [
                    {'role': 'system', 'content': '你只输出合法 JSON，不输出任何其他文字。'},
                    {
                        'role': 'user',
                        'content': build_roundtable_invite_prompt(
                            request.question,
                            history_text,
                            seated_names,
                            roster,
                        ),
                    },
                ],
                temperature=0.1,
                max_tokens=300,
            )
        except Exception:
            return invites

        raw_invites = payload.get('invites') if isinstance(payload, dict) else None
        if not isinstance(raw_invites, list):
            return invites

        for entry in raw_invites:
            if not isinstance(entry, dict):
                continue
            slug = str(entry.get('person_slug') or '').strip()
            person = by_slug.get(slug)
            if not person or slug in seated or slug in seen:
                continue
            if not self._get_profile(person.id):
                continue
            host_line = finalize_complete_sentence(
                str(entry.get('host_line') or '').strip() or f'I have invited {person.english_name} to join the discussion.',
                max_chars=240,
            ) or f'I have invited {person.english_name}.'
            invites.append(
                GroupInvite(
                    person_slug=person.slug,
                    person_name=person.english_name,
                    host_line=host_line,
                )
            )
            seen.add(slug)
            if len(invites) >= min(MAX_INVITES_PER_TURN, remaining_seats):
                break
        return invites[:remaining_seats]

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
                existing = list(session.selected_people or [])
                for slug in selected_people:
                    if slug not in existing:
                        existing.append(slug)
                session.selected_people = existing
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
            'Answer in English in one or two complete sentences, up to 40 words. '
            'Stay true to the advisor’s voice. Be specific, with no bullet points, lengthy analysis, or polite preamble.'
        )

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
