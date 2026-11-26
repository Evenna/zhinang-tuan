"""Generate the illustrative community: unique virtual users + their full past conversations.

Run: backend/.venv/bin/python scripts/generate_story_community.py
Writes backend/data/story_community.json (served by /api/stories) and assets/story-community.js.
"""
from __future__ import annotations

import asyncio
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'backend'))
import os
os.chdir(ROOT / 'backend')
from sqlalchemy import select  # noqa: E402
from app.db.models import Person  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services.llm import MiniMaxService  # noqa: E402

ADVISORS = ['coco-chanel', 'steve-jobs', 'plato', 'ada-lovelace', 'salvador-dali', 'michael-jackson', 'walter-white']
PER_ADVISOR = 16
OUT_JSON = ROOT / 'backend' / 'data' / 'story_community.json'
OUT_JS = ROOT / 'assets' / 'story-community.js'

FIRST = {
    'women': ['Maya', 'Olivia', 'Nina', 'Lena', 'Julia', 'Sara', 'Sofia', 'Clara', 'Alice', 'Eva', 'Anna', 'Emma', 'Amelia', 'Zoe',
              'Grace', 'Isabel', 'Hana', 'Priya', 'Mei', 'Leila', 'Ines', 'Freya', 'Yuki', 'Camila', 'Ava', 'Rosa', 'Elif', 'Noor',
              'Jade', 'Iris', 'Tara', 'Lucia', 'Wen', 'Aisha', 'Mila', 'Signe', 'Chloe', 'Daria', 'Ana', 'Ruth', 'Sana', 'Lin',
              'Esme', 'Vera', 'Nadia', 'Kaia', 'Hazel', 'Rin', 'Joy', 'Pia', 'Bea', 'Sun', 'Adele', 'Marta', 'Ida', 'Lou', 'Xin'],
    'men': ['Daniel', 'Noah', 'Ethan', 'David', 'Ryan', 'Alex', 'Leo', 'Oliver', 'Lucas', 'Max', 'Nathan', 'James', 'Sam', 'Ben',
            'Adam', 'Theo', 'Kenji', 'Omar', 'Mateo', 'Arjun', 'Jonas', 'Felix', 'Wei', 'Tomas', 'Hugo', 'Ravi', 'Emil', 'Kai',
            'Marco', 'Idris', 'Jun', 'Elias', 'Andre', 'Yusuf', 'Finn', 'Paolo', 'Hao', 'Diego', 'Luca', 'Malik', 'Ivan', 'Owen',
            'Tariq', 'Rafael', 'Henrik', 'Minh', 'Caleb', 'Aaron', 'Sebastian', 'Jin', 'Isaac', 'Nico', 'Bruno', 'Victor', 'Ken'],
}
LAST = ['Morgan', 'Ellis', 'Chen', 'Wong', 'Park', 'Bennett', 'Taylor', 'Patel', 'Reed', 'Miller', 'Rivera', 'Brooks', 'Lin', 'Lewis',
        'Singh', 'Shaw', 'Wright', 'Kim', 'Costa', 'Martin', 'Okafor', 'Nakamura', 'Haddad', 'Novak', 'Larsen', 'Moreau', 'Silva',
        'Ibrahim', 'Zhang', 'Liu', 'Tanaka', 'Rossi', 'Kowalski', 'Ahmed', 'Fischer', 'Duarte', 'Sato', 'Nguyen', 'Herrera', 'Kaur',
        'Volkov', 'Berg', 'Mensah', 'Yilmaz', 'Torres', 'Dubois', 'Huang', 'Fern', 'Quinn', 'Walsh', 'Hart', 'Lund']

PROMPT = """You are writing realistic, illustrative community records for "Ask Socrates", an app where people bring a real-life question to a council of historical and fictional figures (AI personas grounded in each figure's documented ideas), draw advisor cards, chat 1:1 and then hold a roundtable.

Write {n} DIFFERENT people who chose {name} as their main advisor. {bio}

Requirements:
- Every person has a distinct, specific, emotionally honest dilemma that fits why someone would pick {name}. No two share a theme. Vary ages (19-67), jobs, countries, life stages. Avoid clichés; include concrete details (numbers, places, objects, a sentence someone said to them).
- "conversation": 6-8 turns alternating user/advisor, starting with the user. The user writes like a real person (sometimes short, hesitant, typos ok rarely). {name} speaks in their own recognizable voice, values and references from their real life/work (or story, if fictional), challenges the user, asks sharp questions, and does NOT give generic self-help. Each advisor turn 40-110 words.
- "roundtable": after the 1:1, two OTHER figures from this list joined: {others}. Give 3 short turns (speaker slug + text, 30-70 words) where they genuinely disagree or add a new angle, including one reply from {name}.
- "outcome": 1-2 sentences, written later by the user, about what they actually did afterwards (not always a happy ending).
- headline: max 7 words, a question in first person. question: the full question as typed (1 sentence). context: 2 sentences, third person, using the person's first name.
- topics: 2 short tags (Title Case).

The people (keep these names/genders/ids exactly):
{people}

Return ONLY JSON: {{"users":[{{"id":..., "age":int, "role":"job or life situation", "city":"City, Country", "headline":..., "question":..., "context":..., "topics":[..], "conversation":[{{"role":"user"|"advisor","text":...}}], "roundtable":[{{"speaker":"slug","text":...}}], "outcome":..., "resonance":int 3-480, "saves":int 0-120}}]}}"""


async def gen_batch(llm, adv, people, others, sem):
    async with sem:
        plist = '\n'.join(f'- id={p["id"]} name={p["name"]} gender={p["gender"]}' for p in people)
        prompt = PROMPT.format(n=len(people), name=adv['name'], bio=adv['bio'], others=', '.join(others), people=plist)
        for attempt in range(4):
            try:
                data = await llm.chat_json([{'role': 'user', 'content': prompt}], temperature=0.95, max_tokens=7000)
                users = data['users'] if isinstance(data, dict) else data
                byid = {u['id']: u for u in users}
                assert all(p['id'] in byid for p in people), 'missing ids'
                out = []
                for p in people:
                    u = byid[p['id']]
                    assert len(u['conversation']) >= 4
                    out.append({**u, 'id': p['id'], 'name': p['name'], 'avatar': p['avatar']})
                print('ok', adv['slug'], len(out), flush=True)
                return out
            except Exception as exc:  # noqa: BLE001
                print('retry', adv['slug'], attempt, repr(exc)[:200], flush=True)
        raise RuntimeError(f'failed {adv["slug"]}')


async def main():
    with SessionLocal() as db:
        meta = {}
        for slug in ADVISORS:
            p = db.scalar(select(Person).where(Person.slug == slug))
            meta[slug] = {'slug': slug, 'name': p.english_name, 'bio': (p.brief_intro or '')[:400]}
    avatars = sorted(f.name for f in (ROOT / 'assets' / 'story-users').glob('*.jpg'))
    rng = random.Random(2026)
    rng.shuffle(avatars)
    used_names = set()
    llm = MiniMaxService()
    sem = asyncio.Semaphore(6)
    tasks, plan = [], []
    pool = ['socrates', 'nietzsche', 'marcus-aurelius', 'carl-jung', 'simone-de-beauvoir', 'confucius', 'laozi', 'viktor-frankl',
            'frida-kahlo', 'warren-buffett', 'albert-camus', 'hayao-miyazaki', 'marie-curie', 'richard-feynman', 'hannah-arendt',
            'zhuangzi', 'vincent-van-gogh', 'naval-ravikant', 'daniel-kahneman', 'leonardo-da-vinci']
    for ai, slug in enumerate(ADVISORS):
        people = []
        for k in range(PER_ADVISOR):
            av = avatars[(ai * PER_ADVISOR + k) % len(avatars)]
            gender = 'women' if av.startswith('women') else 'men'
            while True:
                name = f'{rng.choice(FIRST[gender])} {rng.choice(LAST)}'
                if name not in used_names:
                    used_names.add(name)
                    break
            people.append({'id': f'{slug}/{av[:-4]}', 'name': name, 'gender': 'woman' if gender == 'women' else 'man',
                           'avatar': f'assets/story-users/{av}'})
        others = [s for s in pool if s != slug]
        rng.shuffle(others)
        for half in [people[i:i + 4] for i in range(0, len(people), 4)]:
            tasks.append(gen_batch(llm, meta[slug], half, others[:8], sem))
            plan.append(slug)
    results = await asyncio.gather(*tasks)
    by_adv = {s: [] for s in ADVISORS}
    for slug, users in zip(plan, results):
        by_adv[slug].extend(users)
    # dates spread over the last ~10 months
    import datetime as dt
    base = dt.date(2026, 11, 20)
    for slug in ADVISORS:
        for u in by_adv[slug]:
            u['date'] = (base - dt.timedelta(days=rng.randint(0, 300))).isoformat()
        by_adv[slug].sort(key=lambda u: u['date'], reverse=True)
    community = {'version': 2, 'demo': True, 'photoSource': 'https://randomuser.me/photos',
                 'advisors': [{'slug': s, 'name': meta[s]['name'], 'users': by_adv[s]} for s in ADVISORS]}
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(community, ensure_ascii=False, indent=1))
    OUT_JS.write_text('// Illustrative community: fictional users and their sample conversations (generated; not real people).\n'
                      'window.STORY_COMMUNITY = ' + json.dumps(community, ensure_ascii=False, separators=(',', ':')) + ';\n')
    print('users', sum(len(v) for v in by_adv.values()))


if __name__ == '__main__':
    asyncio.run(main())
