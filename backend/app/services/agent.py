from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from uuid import uuid4

from fastapi import HTTPException

from app.core.agent_prompt import AGENT_SYSTEM_PROMPT
from app.core.config import get_settings
from app.schemas.agent import AgentAskResponse, AgentSessionResponse, AgentStatusResponse
from app.services.deepseek import DeepSeekService

settings = get_settings()


@dataclass
class AgentSession:
    id: str
    messages: list[dict[str, str]] = field(default_factory=list)
    active: bool = True


class AgentService:
    def __init__(self) -> None:
        self._sessions: dict[str, AgentSession] = {}
        self._lock = Lock()
        self._llm = DeepSeekService()

    def open(self) -> AgentSessionResponse:
        session = AgentSession(
            id=str(uuid4()),
            messages=[{'role': 'system', 'content': AGENT_SYSTEM_PROMPT}],
        )
        with self._lock:
            self._sessions[session.id] = session
        return AgentSessionResponse(
            session_id=session.id,
            active=True,
            greeting=settings.agent_greeting,
        )

    def close(self, session_id: str) -> AgentSessionResponse:
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if not session:
            raise HTTPException(status_code=404, detail='Agent session not found or already closed')
        return AgentSessionResponse(session_id=session_id, active=False)

    def status(self, session_id: str) -> AgentStatusResponse:
        session = self._get_active(session_id)
        turn_count = sum(1 for item in session.messages if item['role'] == 'user')
        return AgentStatusResponse(session_id=session.id, active=True, turn_count=turn_count)

    async def ask(self, session_id: str, question: str) -> AgentAskResponse:
        session = self._get_active(session_id)
        messages = self._messages_for_request(session, question)
        answer = await self._llm.chat(messages)
        self._commit_turn(session.id, question, answer)
        return AgentAskResponse(session_id=session.id, answer=answer)

    async def ask_stream(self, session_id: str, question: str):
        session = self._get_active(session_id)
        messages = self._messages_for_request(session, question)
        chunks: list[str] = []
        async for delta in self._llm.chat_stream(messages):
            chunks.append(delta)
            yield delta
        answer = ''.join(chunks).strip()
        if not answer:
            raise HTTPException(status_code=502, detail='DeepSeek returned an empty reply')
        self._commit_turn(session.id, question, answer)

    def _get_active(self, session_id: str) -> AgentSession:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session or not session.active:
                raise HTTPException(status_code=404, detail='Agent session not found. Click the floating ball to start.')
            return session

    def _messages_for_request(self, session: AgentSession, question: str) -> list[dict[str, str]]:
        history_limit = max(settings.agent_max_history, 2)
        kept = [session.messages[0], *session.messages[1:][-history_limit:]]
        return [*kept, {'role': 'user', 'content': question.strip()}]

    def _commit_turn(self, session_id: str, question: str, answer: str) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session or not session.active:
                return
            session.messages.append({'role': 'user', 'content': question.strip()})
            session.messages.append({'role': 'assistant', 'content': answer})


agent_service = AgentService()
