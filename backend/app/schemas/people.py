from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class PersonSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    slug: str
    english_name: str
    chinese_name: str
    domain_category: str
    ai_archetype: str
    brief_intro: str
    portrait_asset: Optional[str]
    is_fictional: bool
    era_context: Optional[str]
    status: str


class PersonDetailResponse(PersonSummaryResponse):
    persona_profile: Optional[dict[str, Any]] = None
    persona_traits: Optional[list[str]] = None
    preferred_topics: Optional[list[str]] = None
