from __future__ import annotations

from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends

from app.api.deps import get_db
from app.schemas.roundtable import RoundtableRequest, RoundtableResponse
from app.services.roundtable import RoundtableService

router = APIRouter()


@router.post('/respond', response_model=RoundtableResponse)
async def respond(request: RoundtableRequest, db: Session = Depends(get_db)) -> RoundtableResponse:
    service = RoundtableService(db)
    return await service.respond(request)
