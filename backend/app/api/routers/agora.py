"""The Agora: themed debate halls. Residents, weekly motions, live debate rounds with stances, verdicts, publishing."""
from __future__ import annotations

import asyncio
import json
import random
import re
import time
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.prompts import build_persona_system_prompt
from app.db.models import Person
from app.services.chat import ChatService

router = APIRouter()
DATA_DIR = Path(__file__).resolve().parents[3] / 'data'
HALLS = DATA_DIR / 'agora_halls.json'
SEEDED = DATA_DIR / 'agora_debates.json'
PUBLISHED = DATA_DIR / 'agora_published.json'
STANCES = ('for', 'against', 'undecided')
MAX_SEATS = 5


@lru_cache(maxsize=1)
def _halls() -> list[dict]:
    return json.loads(HALLS.read_text())['halls']


def _seeded() -> list[dict]:
    return json.loads(SEEDED.read_text()).get('debates', []) if SEEDED.exists() else []


def _published() -> list[dict]:
    return json.loads(PUBLISHED.read_text()).get('debates', []) if PUBLISHED.exists() else []


def _hall(hall_id: str) -> dict:
    for hall in _halls():
        if hall['id'] == hall_id:
            return hall
    raise HTTPException(status_code=404, detail=f'Hall not found: {hall_id}')


def _motion_of_week(hall: dict) -> str:
    week = date.today().isocalendar()[1]
    return hall['motions'][week % len(hall['motions'])]


def _residents(db: Session, hall: dict) -> list[dict]:
    people = db.scalars(select(Person)).all()
    by_slug = {p.slug: p for p in people}
    slugs = [s for s in hall['featured'] if s in by_slug]
    slugs += sorted(p.slug for p in people if p.domain_category in hall['domains'] and p.slug not in slugs)
    return [{'slug': s, 'name': by_slug[s].english_name, 'era': by_slug[s].era_context, 'intro': by_slug[s].brief_intro} for s in slugs]


def _debate_summary(d: dict) -> dict:
    keys = ('id', 'hall', 'motion', 'name', 'avatar', 'role', 'city', 'date', 'participants', 'tally', 'likes', 'published')
    out = {k: d.get(k) for k in keys}
    out['replies'] = len(d.get('transcript') or [])
    out['comments'] = len(d.get('comments') or [])
    return out


def _debates_for(hall_id: str) -> list[dict]:
    items = [d for d in _published() + _seeded() if d.get('hall') == hall_id]
    return sorted(items, key=lambda d: d.get('date') or '', reverse=True)


@router.get('/halls')
def list_halls(db: Session = Depends(get_db)) -> dict:
    out = []
    for hall in _halls():
        residents = _residents(db, hall)
        debates = _debates_for(hall['id'])
        out.append({
            'id': hall['id'], 'title': hall['title'], 'zh': hall['zh'], 'copy': hall['copy'],
            'motion': _motion_of_week(hall), 'motions': hall['motions'],
            'resident_count': len(residents), 'featured': [r['slug'] for r in residents[:3]],
            'debate_count': len(debates), 'live_count': 2 + (len(debates) * 7 + date.today().day) % 9,
        })
    return {'halls': out}


@router.get('/halls/{hall_id}')
def get_hall(hall_id: str, db: Session = Depends(get_db)) -> dict:
    hall = _hall(hall_id)
    debates = _debates_for(hall_id)
    return {
        'id': hall['id'], 'title': hall['title'], 'zh': hall['zh'], 'copy': hall['copy'],
        'motion': _motion_of_week(hall), 'motions': hall['motions'],
        'residents': _residents(db, hall),
        'debates': [_debate_summary(d) for d in debates],
    }


@router.get('/debates')
def list_debates(hall: Optional[str] = None) -> dict:
    items = _published() + _seeded()
    if hall:
        items = [d for d in items if d.get('hall') == hall]
    return {'demo': True, 'debates': [_debate_summary(d) for d in items]}


@router.get('/debates/{debate_id:path}')
def get_debate(debate_id: str) -> dict:
    for d in _published() + _seeded():
        if d['id'] == debate_id:
            return d
    raise HTTPException(status_code=404, detail='Debate not found')


class Turn(BaseModel):
    speaker: str
    text: str
    stance: Optional[str] = None
    round: int = 0


class RoundRequest(BaseModel):
    motion: str = Field(min_length=3, max_length=300)
    seats: list[str] = Field(min_length=1, max_length=MAX_SEATS)
    transcript: list[Turn] = []
    stances: dict[str, str] = {}
    question: Optional[str] = Field(default=None, max_length=400)
    target: Optional[str] = None
    round: int = 1


TURN_INSTRUCTIONS = (
    'You are taking part in a public debate in the Agora, the Athenian square. '
    'Stay fully in character: your real convictions, your life, your voice. '
    'Address the other debaters by name when you disagree or agree with a specific point. '
    'Reply ONLY with JSON: {"stance": "for" | "against" | "undecided", "move": "argues" | "rebuts" | "concedes" | "reframes", "text": "..."}. '
    '"stance" is your honest current answer to the motion: "for" means you answer YES to the motion as worded, "against" means NO, '
    '"undecided" means you reject the framing or are genuinely torn (you may change it if persuaded, but do not flip lightly). '
    '"text" is what you say aloud: 2 to 3 vivid sentences, max 60 words, in English, no speaker label, no ellipses.'
)


def _render_transcript(turns: list[Turn], names: dict[str, str]) -> str:
    lines = []
    for t in turns[-14:]:
        who = 'Audience member (the user)' if t.speaker == 'user' else names.get(t.speaker, t.speaker)
        tag = f' [{t.stance}]' if t.stance else ''
        lines.append(f'{who}{tag}: {t.text}')
    return '\n'.join(lines) or '(Nobody has spoken yet. You open the debate.)'


@router.post('/round')
async def debate_round(req: RoundRequest, db: Session = Depends(get_db)) -> dict:
    svc = ChatService(db)
    seats = list(dict.fromkeys(req.seats))[:MAX_SEATS]
    speakers = [req.target] if req.target and req.target in seats else seats
    names, prompts = {}, []
    for slug in dict.fromkeys(seats + [t.speaker for t in req.transcript if t.speaker not in ('user', 'host', 'system')]):
        try:
            names[slug] = svc._get_person(slug).english_name
        except HTTPException:
            names[slug] = slug
    history = _render_transcript(req.transcript, names)
    for slug in speakers:
        person = svc._get_person(slug)
        profile = svc._get_profile(person.id)
        if not profile:
            continue
        query = f'{req.motion} {req.question or ""}'
        retrieved = svc.retrieval_service.retrieve_for_person(person, query, limit=3)
        system = build_persona_system_prompt(
            person_name=person.english_name, person_slug=person.slug,
            profile=svc._serialize_profile(profile),
            retrieved_chunks=[svc._retrieved_to_dict(r) for r in retrieved],
        )
        others = ', '.join(names[s] for s in seats if s != slug) or 'nobody else'
        ask = ''
        if req.question:
            ask = (f'\nThe audience member just asked {"you directly" if req.target else "the floor"}: "{req.question}". '
                   'Answer that question first, through the lens of the motion.')
        user_msg = (
            f'{TURN_INSTRUCTIONS}\n\nMOTION: "{req.motion}"\nRound {req.round}. Also on the floor: {others}.\n'
            f'Your previous stance: {req.stances.get(slug, "none yet")}.\n\nDEBATE SO FAR:\n{history}{ask}'
        )
        prompts.append((slug, [{'role': 'system', 'content': system}, {'role': 'user', 'content': user_msg}]))

    async def one(slug: str, messages: list[dict]) -> Optional[dict]:
        try:
            raw = await svc.llm_service.chat(messages, temperature=0.85, max_tokens=260)
        except HTTPException:
            return None
        data = _parse_turn(raw)
        if not data:
            return None
        return {'speaker': slug, 'name': names[slug], 'round': req.round, **data}

    results = await asyncio.gather(*(one(s, m) for s, m in prompts))
    turns = [r for r in results if r]
    if not turns:
        raise HTTPException(status_code=502, detail='The floor fell silent. Try again in a moment.')
    random.shuffle(turns) if req.round > 1 and not req.target else None
    stances = {**{k: v for k, v in req.stances.items() if k in seats}, **{t['speaker']: t['stance'] for t in turns}}
    return {'round': req.round, 'turns': turns, 'stances': stances, 'tally': _tally(stances, seats)}


def _parse_turn(raw: str) -> Optional[dict]:
    text = raw.strip()
    match = re.search(r'\{.*\}', text, re.S)
    data = None
    if match:
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            data = None
    if not isinstance(data, dict):
        if len(text) < 8 or text.lower().strip('.') in {'pass', 'skip'}:
            return None
        data = {'stance': 'undecided', 'move': 'argues', 'text': text}
    stance = str(data.get('stance', 'undecided')).lower()
    stance = stance if stance in STANCES else 'undecided'
    move = str(data.get('move', 'argues')).lower()
    move = move if move in {'argues', 'rebuts', 'concedes', 'reframes'} else 'argues'
    speech = re.sub(r'\s+', ' ', str(data.get('text', ''))).strip().strip('"“”')
    if len(speech) < 8 or speech.lower().strip('.') in {'pass', 'skip'}:
        return None
    return {'stance': stance, 'move': move, 'text': speech[:600]}


def _tally(stances: dict[str, str], seats: list[str]) -> dict:
    t = {s: 0 for s in STANCES}
    for slug in seats:
        t[stances.get(slug, 'undecided')] += 1
    return t


class VerdictRequest(BaseModel):
    motion: str
    seats: list[str]
    transcript: list[Turn]
    stances: dict[str, str] = {}


@router.post('/verdict')
async def verdict(req: VerdictRequest, db: Session = Depends(get_db)) -> dict:
    svc = ChatService(db)
    names = {s: svc._get_person(s).english_name for s in req.seats}
    prompt = (
        'You are the scribe of the Agora. Write the verdict of this debate as JSON only:\n'
        '{"headline": "short evocative title, max 9 words", "summary": "2-3 sentences: where the Agora landed and why", '
        '"for": ["2 crisp points made for the motion"], "against": ["2 crisp points made against"], '
        '"open": ["1-2 questions still unresolved"], "tension": "one sentence: the real crux", '
        '"positions": [{"speaker": "slug", "stance": "one sentence: where this person landed"}]}\n'
        'Each bullet max 14 words. English. Use the slugs given.\n\n'
        f'MOTION: "{req.motion}"\nDEBATERS (slug = name): ' + ', '.join(f'{s} = {n}' for s, n in names.items()) +
        f'\nFINAL STANCES: {json.dumps(req.stances)}\n\nTRANSCRIPT:\n{_render_transcript(req.transcript, names)}'
    )
    try:
        data = await svc.llm_service.chat_json([{'role': 'user', 'content': prompt}], temperature=0.4, max_tokens=900)
    except HTTPException:
        data = {}
    data = data if isinstance(data, dict) else {}
    tally = _tally(req.stances, req.seats)
    return {
        'headline': data.get('headline') or req.motion,
        'summary': data.get('summary') or 'The Agora debated without reaching a single answer.',
        'for': [str(x) for x in data.get('for') or []][:3],
        'against': [str(x) for x in data.get('against') or []][:3],
        'open': [str(x) for x in data.get('open') or []][:3],
        'tension': data.get('tension') or '',
        'positions': [p for p in data.get('positions') or [] if isinstance(p, dict) and p.get('speaker') in names],
        'tally': tally,
    }


class PublishRequest(BaseModel):
    hall: str
    motion: str
    seats: list[str]
    transcript: list[Turn]
    stances: dict[str, str] = {}
    verdict: dict
    author: str = Field(default='Anonymous visitor', max_length=40)


@router.post('/publish')
def publish(req: PublishRequest) -> dict:
    _hall(req.hall)
    data = {'debates': _published()}
    did = f'agora/{req.hall}-{int(time.time() * 1000):x}'
    v = req.verdict
    debate = {
        'id': did, 'hall': req.hall, 'motion': req.motion, 'mode': 'agora', 'published': True,
        'name': req.author, 'avatar': '', 'role': 'Visitor', 'city': '', 'date': date.today().isoformat(),
        'headline': v.get('headline') or req.motion, 'question': req.motion, 'context': v.get('summary', ''),
        'topics': [_hall(req.hall)['title']], 'participants': req.seats,
        'stances': req.stances, 'tally': _tally(req.stances, req.seats),
        'transcript': [t.model_dump() for t in req.transcript],
        'verdict': {k: v.get(k) for k in ('for', 'against', 'open')},
        'summary': {'tldr': v.get('summary', ''), 'positions': v.get('positions', []),
                    'conclusion': v.get('summary', ''), 'tension': v.get('tension', '')},
        'comments': [], 'likes': 0, 'shares': 0, 'saves': 0,
    }
    data['debates'].insert(0, debate)
    data['debates'] = data['debates'][:300]
    PUBLISHED.write_text(json.dumps(data, ensure_ascii=False))
    return {'id': did, 'debate': debate}
