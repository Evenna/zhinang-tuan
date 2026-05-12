from __future__ import annotations

from pydantic import BaseModel


class ImportRequest(BaseModel):
    force_rebuild: bool = False


class ImportResponse(BaseModel):
    dataset_version: str
    people_count: int
    profiles_count: int
    chunks_count: int
    force_rebuild: bool
