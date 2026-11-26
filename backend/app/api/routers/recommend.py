from __future__ import annotations

from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends

from app.api.deps import get_db
from app.schemas.recommend import RecommendRequest, RecommendResponse
from app.services.recommend import RecommendService

router = APIRouter()


@router.post('', response_model=RecommendResponse)
async def recommend(request: RecommendRequest, db: Session = Depends(get_db)) -> RecommendResponse:
    service = RecommendService(db)
    return await service.recommend(request)
