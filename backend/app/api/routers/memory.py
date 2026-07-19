from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.models import SessionSummary, UserMemory


router = APIRouter()


@router.get('')
def list_memories(
    user_id: str = Query(default='default_user', min_length=1, max_length=120),
    include_archived: bool = False,
    db: Session = Depends(get_db),
) -> list[dict]:
    query = select(UserMemory).where(UserMemory.user_id == user_id)
    if not include_archived:
        query = query.where(UserMemory.status == 'active')
    rows = db.scalars(query.order_by(desc(UserMemory.importance), desc(UserMemory.updated_at))).all()
    return [
        {
            'id': row.id, 'memory_type': row.memory_type, 'content': row.content,
            'confidence': row.confidence, 'importance': row.importance,
            'evidence_count': row.evidence_count, 'status': row.status,
            'updated_at': row.updated_at,
        }
        for row in rows
    ]


@router.get('/summaries/{conversation_id}')
def list_summaries(conversation_id: str, db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(
        select(SessionSummary).where(SessionSummary.session_id == conversation_id).order_by(desc(SessionSummary.message_count))
    ).all()
    return [
        {
            'id': row.id, 'summary': row.summary, 'open_questions': row.open_questions,
            'decisions': row.decisions, 'memory_highlights': row.memory_highlights,
            'message_count': row.message_count, 'trigger_reason': row.trigger_reason,
            'updated_at': row.updated_at,
        }
        for row in rows
    ]


@router.delete('/{memory_id}')
def forget_memory(
    memory_id: str,
    user_id: str = Query(default='default_user', min_length=1, max_length=120),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    row = db.scalar(select(UserMemory).where(UserMemory.id == memory_id, UserMemory.user_id == user_id))
    if not row:
        raise HTTPException(status_code=404, detail='记忆不存在。')
    row.status = 'deleted'
    db.commit()
    return {'status': 'forgotten'}
