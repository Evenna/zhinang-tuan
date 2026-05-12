from __future__ import annotations

from pydantic import BaseModel, Field


class RecommendRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=10)


class RecommendationItem(BaseModel):
    person_slug: str
    person_name: str
    reason: str
    score: float


class RecommendResponse(BaseModel):
    question: str
    recommendations: list[RecommendationItem]
