from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.chat import ConversationTurn, RetrievedChunk


class RoundtableParticipant(BaseModel):
    participant_type: str = Field(default='builtin_person', pattern='^(builtin_person|speaker_card|coach_role)$')
    participant_id: Optional[str] = None
    person_slug: Optional[str] = None
    person_name: Optional[str] = None
    role: str = Field(pattern='^(primary_responder|challenger|complement|clarifier|critic)$')
    task: str = Field(min_length=1, max_length=500)
    selection_reason: str = Field(default='', max_length=500)


class RoundtableParticipantRef(BaseModel):
    type: str = Field(default='builtin_person', pattern='^(builtin_person|speaker_card|coach_role)$')
    id: str = Field(min_length=1, max_length=160)


class RoundtablePlan(BaseModel):
    mode: str = Field(pattern='^(clarify_first|single_expert|primary_with_challenge|mini_roundtable)$')
    reasoning: str = Field(default='', max_length=1000)
    needs_clarification: bool = False
    clarifying_question: Optional[str] = Field(default=None, max_length=500)
    participants: list[RoundtableParticipant] = Field(default_factory=list)


class RoundtableRequest(BaseModel):
    question: str = Field(min_length=2, max_length=4000)
    memory_text: Optional[str] = Field(default=None, max_length=4000)
    conversation_id: Optional[str] = None
    user_id: str = Field(default='default_user', min_length=1, max_length=120)
    preferred_people: list[str] = Field(default_factory=list, max_length=5)
    participant_refs: list[RoundtableParticipantRef] = Field(default_factory=list, max_length=6)
    max_participants: int = Field(default=3, ge=1, le=4)
    history: list[ConversationTurn] = Field(default_factory=list)


class RoundtableTurnResponse(BaseModel):
    turn_index: int
    speaker_slug: Optional[str]
    speaker_name: Optional[str]
    speaker_role: str
    task: str
    content: str
    citations: list[RetrievedChunk] = Field(default_factory=list)


class RoundtableMemoryState(BaseModel):
    summary: str = ''
    open_questions: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    memory_highlights: list[str] = Field(default_factory=list)
    user_memories: list[str] = Field(default_factory=list)


class RoundtableResponse(BaseModel):
    conversation_id: str
    plan: RoundtablePlan
    turns: list[RoundtableTurnResponse]
    final_answer: str
    memory: RoundtableMemoryState
