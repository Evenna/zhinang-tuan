from __future__ import annotations

from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends

from app.api.deps import get_db
from app.schemas.admin import ImportRequest, ImportResponse
from app.services.importer import ImportService

router = APIRouter()


@router.post('/import', response_model=ImportResponse)
def import_people(request: ImportRequest, db: Session = Depends(get_db)) -> ImportResponse:
    service = ImportService(db)
    summary = service.import_dataset(force_rebuild=request.force_rebuild)
    return ImportResponse(**summary)
