from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_db
from app.db.models import Person, PersonaProfile
from app.schemas.people import PersonDetailResponse, PersonSummaryResponse

router = APIRouter()


@router.get('', response_model=list[PersonSummaryResponse])
def list_people(
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[PersonSummaryResponse]:
    people = db.scalars(select(Person).order_by(Person.chinese_name).offset(offset).limit(limit)).all()
    return [PersonSummaryResponse.model_validate(person) for person in people]


@router.get('/{slug}', response_model=PersonDetailResponse)
def get_person(slug: str, db: Session = Depends(get_db)) -> PersonDetailResponse:
    person = db.scalar(select(Person).where(Person.slug == slug))
    if not person:
        raise HTTPException(status_code=404, detail='Person not found')
    profile = db.scalar(
        select(PersonaProfile)
        .where(PersonaProfile.person_id == person.id)
        .order_by(desc(PersonaProfile.version))
    )
    return PersonDetailResponse(
        id=person.id,
        slug=person.slug,
        english_name=person.english_name,
        chinese_name=person.chinese_name,
        domain_category=person.domain_category,
        ai_archetype=person.ai_archetype,
        brief_intro=person.brief_intro,
        portrait_asset=person.portrait_asset,
        is_fictional=person.is_fictional,
        era_context=person.era_context,
        status=person.status,
        persona_profile=profile.identity if profile else None,
        persona_traits=profile.core_traits if profile else None,
        preferred_topics=profile.preferred_topics if profile else None,
    )
