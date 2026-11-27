"""Generate a life timeline + key works for every advisor in the DB.

Run: backend/.venv/bin/python scripts/generate_person_timelines.py
Writes backend/data/person_timelines.json (served by /api/people/{slug}/timeline) and assets/person-timelines.js.
Resumable: already-generated slugs are skipped.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'backend'))
os.chdir(ROOT / 'backend')
from sqlalchemy import select  # noqa: E402
from app.db.models import Person  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services.llm import MiniMaxService  # noqa: E402

OUT_JSON = ROOT / 'backend' / 'data' / 'person_timelines.json'
OUT_JS = ROOT / 'assets' / 'person-timelines.js'

PROMPT = """Write accurate biographical timelines for these figures (historical, living or fictional). Facts must be correct; for fictional characters use events from their canonical story and in-world dates/ages.

{people}

For EACH figure return:
- "tagline": one line (max 12 words) capturing who they are.
- "events": 8-11 chronological life events. Each: "year" (string like "1889", "c. 470 BC", "Season 2" for fiction), "title" (max 7 words), "detail" (1-2 sentences, concrete), "kind" one of "life" | "work" | "turning" (turning = a crisis/decisive moment), "keywords": 3-6 lowercase English words or short phrases a person might mention in conversation that relate to this event (places, people, objects, concepts).
- "works": 3-6 major works / achievements / creations. Each: "title", "year", "note" (max 16 words).
- "quote": one short real (or canonical) quote.

Return ONLY JSON: {{"items": [{{"slug": ..., "tagline": ..., "events": [...], "works": [...], "quote": ...}}]}}"""


async def gen(llm, batch, sem, out):
    async with sem:
        plist = '\n'.join(f'- slug={p["slug"]} | {p["name"]} | {p["era"]} | {p["intro"]}' for p in batch)
        for attempt in range(4):
            try:
                data = await llm.chat_json([{'role': 'user', 'content': PROMPT.format(people=plist)}], temperature=0.3, max_tokens=8000)
                items = data['items'] if isinstance(data, dict) else data
                got = {i['slug']: i for i in items if isinstance(i, dict) and i.get('events')}
                for p in batch:
                    if p['slug'] in got and len(got[p['slug']]['events']) >= 5:
                        out[p['slug']] = got[p['slug']]
                missing = [p for p in batch if p['slug'] not in out]
                if not missing:
                    print('ok', [p['slug'] for p in batch], flush=True)
                    return
                batch = missing
                plist = '\n'.join(f'- slug={p["slug"]} | {p["name"]} | {p["era"]} | {p["intro"]}' for p in batch)
            except Exception as exc:  # noqa: BLE001
                print('retry', attempt, repr(exc)[:160], flush=True)
        print('FAILED', [p['slug'] for p in batch], flush=True)


async def main():
    out = json.loads(OUT_JSON.read_text()) if OUT_JSON.exists() else {}
    with SessionLocal() as db:
        people = [{'slug': p.slug, 'name': p.english_name, 'era': p.era_context or '', 'intro': (p.brief_intro or '')[:160]}
                  for p in db.scalars(select(Person).order_by(Person.english_name))]
    todo = [p for p in people if p['slug'] not in out]
    print('todo', len(todo), flush=True)
    llm = MiniMaxService()
    sem = asyncio.Semaphore(8)
    batches = [todo[i:i + 3] for i in range(0, len(todo), 3)]

    async def runner(b):
        await gen(llm, b, sem, out)
        OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=1))

    await asyncio.gather(*(runner(b) for b in batches))
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    OUT_JS.write_text('// Advisor life timelines (generated).\nwindow.PERSON_TIMELINES = '
                      + json.dumps(out, ensure_ascii=False, separators=(',', ':')) + ';\n')
    print('done', len(out), 'of', len(people))


if __name__ == '__main__':
    asyncio.run(main())
