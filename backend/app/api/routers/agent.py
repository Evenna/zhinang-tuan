from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.schemas.agent import (
    AgentAskRequest,
    AgentAskResponse,
    AgentCloseRequest,
    AgentSessionResponse,
    AgentStatusResponse,
)
from app.services.agent import agent_service

router = APIRouter()


@router.post('/open', response_model=AgentSessionResponse)
def open_agent() -> AgentSessionResponse:
    """MR 悬浮球第一次点击：启动智能体会话。"""
    return agent_service.open()


@router.post('/close', response_model=AgentSessionResponse)
def close_agent(request: AgentCloseRequest) -> AgentSessionResponse:
    """MR 悬浮球再次点击：关闭智能体并清空本轮对话。"""
    return agent_service.close(request.session_id)


@router.get('/status/{session_id}', response_model=AgentStatusResponse)
def agent_status(session_id: str) -> AgentStatusResponse:
    return agent_service.status(session_id)


@router.post('/ask', response_model=AgentAskResponse)
async def ask_agent(request: AgentAskRequest) -> AgentAskResponse:
    """把用户问题发给 DeepSeek，返回完整回答。"""
    return await agent_service.ask(request.session_id, request.question)


@router.post('/ask/stream')
async def ask_agent_stream(request: AgentAskRequest) -> StreamingResponse:
    """SSE 流式回答，适合眼镜里边生成边播报。"""

    async def event_source():
        async for delta in agent_service.ask_stream(request.session_id, request.question):
            yield f'data: {json.dumps({"delta": delta}, ensure_ascii=False)}\n\n'
        yield f'data: {json.dumps({"done": True})}\n\n'

    return StreamingResponse(
        event_source(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        },
    )
