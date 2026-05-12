from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends

from app.api.deps import get_db
from app.core.config import get_settings

router = APIRouter()
settings = get_settings()


@router.get('/health')
def health(db: Session = Depends(get_db)) -> dict[str, object]:
    db.execute(text('SELECT 1'))
    return {
        'status': 'ok',
        'database': 'ok',
        'deepseek_configured': bool(settings.deepseek_api_key),
    }
