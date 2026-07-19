from __future__ import annotations

from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_db
from app.schemas.study import (
    StudyRoundtableRequest,
    StudyRoundtableResponse,
    StudySourceCreateRequest,
    StudySourceDetail,
    StudySourceFileImportRequest,
    StudySourceSummary,
    StudySourceUrlImportRequest,
    StudyVideoImportRequest,
    SpeakerCardGenerateRequest,
    SpeakerCardSummary,
)
from app.services.study import SpeakerCardService, StudyRoundtableService, StudySourceService

router = APIRouter()


@router.post('/sources', response_model=StudySourceDetail)
def create_source(request: StudySourceCreateRequest, db: Session = Depends(get_db)) -> StudySourceDetail:
    service = StudySourceService(db)
    return service.create_source(request)


@router.post('/sources/import-file', response_model=StudySourceDetail)
def import_file(request: StudySourceFileImportRequest, db: Session = Depends(get_db)) -> StudySourceDetail:
    service = StudySourceService(db)
    return service.import_file(request)


@router.post('/sources/import-url', response_model=StudySourceDetail)
async def import_url(request: StudySourceUrlImportRequest, db: Session = Depends(get_db)) -> StudySourceDetail:
    service = StudySourceService(db)
    return await service.import_url(request)


@router.post('/sources/import-video', response_model=StudySourceDetail)
async def import_video(request: StudyVideoImportRequest, db: Session = Depends(get_db)) -> StudySourceDetail:
    service = StudySourceService(db)
    return await service.import_video(request)


@router.post('/speaker-cards/generate', response_model=SpeakerCardSummary)
async def generate_speaker_card(
    request: SpeakerCardGenerateRequest,
    db: Session = Depends(get_db),
) -> SpeakerCardSummary:
    return await SpeakerCardService(db).generate(request)


@router.get('/speaker-cards', response_model=list[SpeakerCardSummary])
def list_speaker_cards(
    user_id: str = Query(default='default_user', min_length=1, max_length=120),
    db: Session = Depends(get_db),
) -> list[SpeakerCardSummary]:
    return SpeakerCardService(db).list_cards(user_id)


@router.get('/sources', response_model=list[StudySourceSummary])
def list_sources(
    user_id: str = Query(default='default_user', min_length=1, max_length=120),
    db: Session = Depends(get_db),
) -> list[StudySourceSummary]:
    service = StudySourceService(db)
    return service.list_sources(user_id=user_id)


@router.get('/sources/{source_id}', response_model=StudySourceDetail)
def get_source(
    source_id: str,
    user_id: str = Query(default='default_user', min_length=1, max_length=120),
    db: Session = Depends(get_db),
) -> StudySourceDetail:
    service = StudySourceService(db)
    return service.get_source(source_id, user_id=user_id)


@router.post('/roundtable/respond', response_model=StudyRoundtableResponse)
async def respond(request: StudyRoundtableRequest, db: Session = Depends(get_db)) -> StudyRoundtableResponse:
    service = StudyRoundtableService(db)
    return await service.respond(request)
