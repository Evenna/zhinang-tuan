from __future__ import annotations

from uuid import uuid4
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from fastapi import HTTPException

from app.core.prompts import build_group_synthesis_prompt, build_persona_system_prompt
from app.db.models import ChatMessage, ConversationSession, Person, PersonaProfile
from app.schemas.chat import ChatRequest, ChatResponse, GroupAdvisorAnswer, GroupChatRequest, GroupChatResponse, RetrievedChunk
from app.services.llm import DeepSeekService
from app.services.recommend import RecommendService
from app.services.retrieval import RetrievalService


class ChatService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.retrieval_service = RetrievalService(db)
        self.recommend_service = RecommendService(db)
        self.llm_service = DeepSeekService()

    async def respond(self, request: ChatRequest) -> ChatResponse:
        person = self._get_person(request.person_slug)
        profile = self._get_profile(person.id)
        if not profile:
            raise HTTPException(status_code=404, detail='Persona profile not found')

        session = self._get_or_create_session(request.conversation_id, mode='single', selected_people=[person.slug])
        retrieved = self.retrieval_service.retrieve_for_person(person, request.question)
        system_prompt = build_persona_system_prompt(
            person_name=person.chinese_name,
            person_slug=person.slug,
            profile=self._serialize_profile(profile),
            retrieved_chunks=[self._retrieved_to_dict(item) for item in retrieved],
        )
        messages = [{'role': 'system', 'content': system_prompt}]
        for turn in request.history[-6:]:
            messages.append({'role': turn.role, 'content': turn.content})
        messages.append({'role': 'user', 'content': request.question})
        answer = await self.llm_service.chat(messages)

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
        answers: list[GroupAdvisorAnswer] = []
        for slug in person_slugs:
            person = self._get_person(slug)
            profile = self._get_profile(person.id)
            if not profile:
                continue
            retrieved = self.retrieval_service.retrieve_for_person(person, request.question)
            system_prompt = build_persona_system_prompt(
                person_name=person.chinese_name,
                person_slug=person.slug,
                profile=self._serialize_profile(profile),
                retrieved_chunks=[self._retrieved_to_dict(item) for item in retrieved],
            )
            messages = [{'role': 'system', 'content': system_prompt}]
            for turn in request.history[-4:]:
                messages.append({'role': turn.role, 'content': turn.content})
            messages.append({'role': 'user', 'content': request.question})
            answer = await self.llm_service.chat(messages, temperature=0.85)
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

        synthesis = await self.llm_service.chat(
            [
                {
                    'role': 'system',
                    'content': 'You are a synthesis layer for multiple advisors. Summarize consensus, disagreement, and next action in Chinese.',
                },
                {'role': 'user', 'content': build_group_synthesis_prompt(request.question, [item.model_dump() for item in answers])},
            ],
            temperature=0.5,
            max_tokens=700,
        )
        self._store_message(session.id, 'assistant', 'moderator', synthesis, None)
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
