"""Illustrative community stories: fictional users and the conversations they had with advisors."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter()
DATA = Path(__file__).resolve().parents[3] / 'data' / 'story_community.json'


@lru_cache(maxsize=1)
def _community() -> dict:
    return json.loads(DATA.read_text())


def _summary(user: dict) -> dict:
    return {k: user.get(k) for k in ('id', 'name', 'avatar', 'age', 'role', 'city', 'headline', 'question', 'context', 'topics', 'date', 'resonance', 'saves')}


@router.get('')
def list_stories(advisor: str | None = None) -> dict:
    data = _community()
    advisors = [a for a in data['advisors'] if not advisor or a['slug'] == advisor]
    return {'demo': True, 'advisors': [{'slug': a['slug'], 'name': a['name'], 'users': [_summary(u) for u in a['users']]} for a in advisors]}


@router.get('/{advisor}/{user}')
def get_story(advisor: str, user: str) -> dict:
    for a in _community()['advisors']:
        for u in a['users']:
            if u['id'] == f'{advisor}/{user}':
                return {**u, 'advisor_slug': a['slug'], 'advisor_name': a['name'], 'demo': True}
    raise HTTPException(status_code=404, detail='Story not found')
