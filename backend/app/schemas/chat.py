from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ConversationTurn(BaseModel):
    role: str = Field(pattern='^(user|assistant)$')
    content: str = Field(min_length=1, max_length=4000)


class RetrievedChunk(BaseModel):
    chunk_type: str
    title: str
    source_name: str
    score: float
    excerpt: str


class ChatRequest(BaseModel):
    person_slug: str
    question: str = Field(min_length=2, max_length=4000)
    history: list[ConversationTurn] = Field(default_factory=list)
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    conversation_id: str
    person_slug: str
    person_name: str
    answer: str
    citations: list[RetrievedChunk]


class GroupAdvisorAnswer(BaseModel):
    person_slug: str
    person_name: str
    answer: str
    citations: list[RetrievedChunk]


class GroupChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=4000)
    person_slugs: list[str] = Field(default_factory=list)
    top_k: int = Field(default=3, ge=1, le=5)
    history: list[ConversationTurn] = Field(default_factory=list)
    conversation_id: Optional[str] = None


class GroupChatResponse(BaseModel):
    conversation_id: str
    selected_people: list[str]
    answers: list[GroupAdvisorAnswer]
    synthesis: str
