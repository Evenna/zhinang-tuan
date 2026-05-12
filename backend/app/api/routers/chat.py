from __future__ import annotations

from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends

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
