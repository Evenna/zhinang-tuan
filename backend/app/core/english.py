"""English presentation of the existing catalog; original research data stays intact."""
from __future__ import annotations

import json
from pathlib import Path
from pydantic import BaseModel, field_validator

_TRANSLATIONS = json.loads((Path(__file__).parent.parent / 'data' / 'english.json').read_text())


def english_value(value):
    if isinstance(value, str):
        return _TRANSLATIONS.get(value, value)
    if isinstance(value, list):
        return [english_value(item) for item in value]
    if isinstance(value, dict):
        return {key: english_value(item) for key, item in value.items()}
    return value


class EnglishResponse(BaseModel):
    @field_validator('*', mode='after')
    @classmethod
    def localize_field(cls, value):
        return english_value(value)
