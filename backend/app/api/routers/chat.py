from __future__ import annotations

from sqlalchemy.orm import Session

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_db
from app.schemas.chat import ChatRequest, ChatResponse, GroupChatRequest, GroupChatResponse
from app.services.chat import ChatService

router = APIRouter()


@router.post('/respond', response_model=ChatResponse)
async def respond(request: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    service = ChatService(db)
    return await service.respond(request)


@router.post('/group', response_model=GroupChatResponse)
async def group_chat(request: GroupChatRequest, db: Session = Depends(get_db)) -> GroupChatResponse:
    service = ChatService(db)
    return await service.group_respond(request)


class RoundLine(BaseModel):
    speaker: str
    name: str = ''
    text: str = Field(min_length=1, max_length=2000)


class RoundPrepareRequest(BaseModel):
    question: str = Field(min_length=2, max_length=4000)
    person_slugs: list[str] = Field(default_factory=list)
    transcript: list[RoundLine] = Field(default_factory=list)
    conversation_id: Optional[str] = None


class RoundTurnRequest(BaseModel):
    question: str = Field(min_length=2, max_length=4000)
    person_slugs: list[str]
    speaker: str
    transcript: list[RoundLine] = Field(default_factory=list)
    allow_pass: bool = False
    newly_invited: bool = False
    conversation_id: Optional[str] = None


class RoundSynthesisRequest(BaseModel):
    question: str = Field(min_length=2, max_length=4000)
    transcript: list[RoundLine] = Field(default_factory=list)
    conversation_id: Optional[str] = None


@router.post('/group/prepare')
async def group_prepare(request: RoundPrepareRequest, db: Session = Depends(get_db)) -> dict:
    """Open a round: log the question and decide whether anyone should be invited in."""
    return await ChatService(db).roundtable_prepare(request)


@router.post('/group/turn')
async def group_turn(request: RoundTurnRequest, db: Session = Depends(get_db)) -> dict:
    """One voice at a time — each speaker hears everyone who spoke before them, and may pass."""
    return await ChatService(db).roundtable_turn(request)


@router.post('/group/synthesis')
async def group_synthesis(request: RoundSynthesisRequest, db: Session = Depends(get_db)) -> dict:
    return await ChatService(db).roundtable_synthesis(request)
