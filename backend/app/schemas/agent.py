from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class AgentSessionResponse(BaseModel):
    session_id: str
    active: bool
    greeting: Optional[str] = None


class AgentCloseRequest(BaseModel):
    session_id: str = Field(min_length=1)


class AgentAskRequest(BaseModel):
    session_id: str = Field(min_length=1)
    question: str = Field(min_length=1, max_length=20000)


class AgentAskResponse(BaseModel):
    session_id: str
    answer: str


class AgentStatusResponse(BaseModel):
    session_id: str
    active: bool
    turn_count: int
