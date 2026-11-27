"""Upgrade the illustrative community to v3: longer sessions, half of them roundtables,
plus a top summary (positions + conclusion) and community reactions (likes / comments / shares).

Keeps each user's identity + question from v2 (story_community.json) and rewrites the session.
Run: backend/.venv/bin/python scripts/upgrade_story_community.py   (resumable)
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'backend'))
os.chdir(ROOT / 'backend')
from sqlalchemy import select  # noqa: E402
from app.db.models import Person  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services.llm import MiniMaxService  # noqa: E402

DATA = ROOT / 'backend' / 'data' / 'story_community.json'
CACHE = ROOT / 'backend' / 'data' / 'story_sessions_v3.json'
OUT_JS = ROOT / 'assets' / 'story-community.js'

POOL = ['socrates', 'nietzsche', 'marcus-aurelius', 'carl-jung', 'simone-de-beauvoir', 'confucius', 'laozi', 'viktor-frankl',
        'frida-kahlo', 'warren-buffett', 'albert-camus', 'hayao-miyazaki', 'marie-curie', 'richard-feynman', 'hannah-arendt',
        'zhuangzi', 'vincent-van-gogh', 'naval-ravikant', 'daniel-kahneman', 'leonardo-da-vinci', 'coco-chanel', 'steve-jobs',
        'plato', 'ada-lovelace', 'salvador-dali', 'michael-jackson', 'walter-white']

COMMON = """You are writing an illustrative (fictional) community record for "Ask Socrates", an app where people bring a real dilemma to AI personas of historical/fictional figures, grounded in each figure's real ideas, life events and works.

The user: {name}, {age}, {role}, {city}.
Their question: "{question}"
Background: {context}

Rules for every figure's voice: speak in their recognisable voice, cite concrete things from their actual life or works (a year, a place, a book, a decision they made) when relevant, push back, ask sharp questions, never generic self-help. The user writes like a real person — sometimes short, hesitant, emotional, revealing new concrete details as the talk goes on (numbers, names, what someone said).
"""

SOLO = COMMON + """
This was a long ONE-ON-ONE session with {advisor_name} (speaker slug "{advisor}").
Write "transcript": 14-18 turns alternating user / {advisor}, starting with the user. Advisor turns 50-120 words. The conversation must evolve: first understanding, then a challenge, a moment where the user resists or gets upset, a reframe, and finally a concrete next step the user commits to.
"""

TABLE = COMMON + """
This was a long ROUNDTABLE. Participants: {participant_list}. The host (speaker "host") occasionally steers (2-3 short lines max).
Write "transcript": 20-28 turns. Start with the user's question, then each figure's opening position (they must genuinely DISAGREE — at least two clearly opposed camps), then the user pushes back / adds details, figures respond to EACH OTHER by name, someone changes their mind partially, the host invites one closing line each, and the user says what they will do. Figure turns 40-100 words, user turns short. Speakers: "user", "host", or a participant slug.
"""

TAIL = """
Also write:
- "summary": {{"tldr": 2 sentences on what this session was really about, "positions": [one per figure: {{"speaker": slug, "stance": max 18 words, the core of their argument}}], "conclusion": 2-3 sentences: where the discussion landed / the key insight, "tension": one sentence naming the unresolved disagreement (or null for one-on-one if none)}}
- "outcome": 1-3 sentences written later by {name} about what they actually did (not always a happy ending).
- "comments": 3-6 comments from other (fictional) community members reacting to this story. Each {{"name": realistic first name + last initial, "text": 1-3 sentences, varied (relating own experience, disagreeing with a figure, a question to {name}), "likes": int 0-90}}. Optionally one reply from {name} as a comment with "is_author": true.

Return ONLY JSON: {{"transcript": [{{"speaker": ..., "text": ...}}], "summary": {{...}}, "outcome": ..., "comments": [...]}}"""


async def gen(llm, user, advisor, mode, participants, names, sem):
    async with sem:
        base = dict(name=user['name'], age=user['age'], role=user['role'], city=user['city'], question=user['question'],
                    context=user['context'], advisor=advisor, advisor_name=names[advisor],
                    participant_list=', '.join(f'{names[p]} (slug "{p}")' for p in participants))
        prompt = (SOLO if mode == 'solo' else TABLE).format(**base) + TAIL.format(**base)
        allowed = set(participants) | {'user', 'host'}
        for attempt in range(4):
            try:
                data = await llm.chat_json([{'role': 'user', 'content': prompt}], temperature=0.9, max_tokens=9000)
                tr = [t for t in data['transcript'] if t.get('speaker') in allowed and t.get('text')]
                need = 12 if mode == 'solo' else 16
                assert len(tr) >= need, f'short {len(tr)}'
                assert data['summary']['positions'] and data['summary']['conclusion']
                data['transcript'] = tr
                print('ok', user['id'], mode, len(tr), flush=True)
                return data
            except Exception as exc:  # noqa: BLE001
                print('retry', user['id'], attempt, repr(exc)[:150], flush=True)
        return None


async def main():
    community = json.loads(DATA.read_text())
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    with SessionLocal() as db:
        names = {p.slug: p.english_name for p in db.scalars(select(Person).where(Person.slug.in_(POOL)))}
    rng = random.Random(7)
    llm = MiniMaxService()
    sem = asyncio.Semaphore(10)
    jobs = []
    for adv in community['advisors']:
        for k, u in enumerate(adv['users']):
            mode = 'roundtable' if k % 2 == 1 else 'solo'
            if mode == 'roundtable':
                # reuse the figures that showed up in the v2 roundtable when possible
                prev = [t['speaker'] for t in u.get('roundtable', []) if t.get('speaker') in names and t['speaker'] != adv['slug']]
                others = list(dict.fromkeys(prev))
                extra = [s for s in POOL if s in names and s != adv['slug'] and s not in others]
                rng.shuffle(extra)
                participants = [adv['slug']] + (others + extra)[: rng.choice([2, 3, 3])]
            else:
                participants = [adv['slug']]
            u['mode'], u['participants'] = mode, participants
            if u['id'] not in cache:
                jobs.append((u, adv['slug'], mode, participants))
    print('todo', len(jobs), flush=True)

    async def run(job):
        res = await gen(llm, *job, names, sem)
        if res:
            cache[job[0]['id']] = res
            CACHE.write_text(json.dumps(cache, ensure_ascii=False))

    await asyncio.gather(*(run(j) for j in jobs))

    for adv in community['advisors']:
        for u in adv['users']:
            s = cache.get(u['id'])
            if not s:
                continue
            u.update(transcript=s['transcript'], summary=s['summary'], outcome=s.get('outcome') or u.get('outcome'),
                     comments=s.get('comments', []))
            u['likes'] = u.get('resonance') or rng.randint(20, 400)
            u['shares'] = rng.randint(2, max(3, u['likes'] // 6))
            u.pop('conversation', None)
            u.pop('roundtable', None)
    community['version'] = 3
    community['names'] = names
    DATA.write_text(json.dumps(community, ensure_ascii=False, indent=1))
    OUT_JS.write_text('// Illustrative community: fictional users and their sample sessions (generated; not real people).\n'
                      'window.STORY_COMMUNITY = ' + json.dumps(community, ensure_ascii=False, separators=(',', ':')) + ';\n')
    print('done', len(cache))


if __name__ == '__main__':
    asyncio.run(main())
