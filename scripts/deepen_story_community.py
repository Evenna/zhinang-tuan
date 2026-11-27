"""v4 community: deeper, longer sessions. One-on-one or roundtable; in a roundtable the story's owner
(the advisor it is filed under) speaks the most. Comments come from a recurring pool of members with real photos.

Run: backend/.venv/bin/python scripts/deepen_story_community.py   (resumable; cache in backend/data/story_sessions_v4.json)
"""
from __future__ import annotations

import asyncio
import collections
import json
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'backend'))
os.chdir(ROOT / 'backend')
from app.services.llm import MiniMaxService  # noqa: E402

DATA = ROOT / 'backend' / 'data' / 'story_community.json'
CACHE = ROOT / 'backend' / 'data' / 'story_sessions_v4.json'
OUT_JS = ROOT / 'assets' / 'story-community.js'
PHOTOS = ROOT / 'assets' / 'story-users'

COMMON = """You are writing an illustrative (fictional) community record for "Dear Socrates", an app where people bring a real dilemma to AI personas of historical/fictional figures, grounded in each figure's real ideas, life events and works.

The user: {name}, {age}, {role}, {city}.
Their question: "{question}"
Background: {context}

Voice rules: every figure speaks in their recognisable voice and cites concrete things from their actual life or works (a year, a place, a book, a decision they made, something they said). They push back, ask sharp questions, tell short stories from their own life, and never give generic self-help. The user writes like a real person typing at night: hesitant, sometimes defensive or emotional, and keeps revealing NEW concrete details (numbers, names, what someone said, a memory) as the talk deepens. The conversation must feel like it truly went somewhere deep.
"""

SOLO = COMMON + """
This was a long ONE-ON-ONE session with {advisor_name} (speaker slug "{advisor}").
Write "transcript": 22-28 turns alternating "user" / "{advisor}", starting with the user.
- Advisor turns: 120-230 words (count them; short replies are a failure), at least three of them tell a specific episode from {advisor_name}'s own life.
- User turns: 25-90 words.
Arc: understanding → a hard question the user avoids → the user resists or gets upset → a real story from the advisor's life → a reframe → the user admits the thing underneath → a concrete next step with a date or a number.
"""

TABLE = COMMON + """
This was a long ROUNDTABLE. Participants: {participant_list}. {advisor_name} ("{advisor}") is the one the user mainly came for and leads the table.
Write "transcript" with EXACTLY these {n_turns} turns, in EXACTLY this speaker order (do not add, drop, merge or reorder turns):
{order}
- Turns 2-{open_end} are each figure's opening position — they must genuinely DISAGREE (at least two opposed camps).
- After that, figures answer EACH OTHER by name, quote each other, and argue; someone partially changes their mind.
- {advisor_name} speaks most because the others keep provoking them and the user keeps turning back to them — make that feel natural, never repetitive: each of their turns must add a new episode, a new objection or a sharper question.
- In "user" turns the user pushes back and adds new concrete details; at least once the user asks one figure directly.
- "host" turns are a single short steering line; the last host line invites one closing line from each figure.
- The final user turn says what they will do.
- Figure turns 90-190 words (count them; short replies are a failure); user turns 25-90 words.
"""

TAIL = """
Also write:
- "summary": {{"tldr": 2 sentences on what this session was really about, "positions": [one per figure: {{"speaker": slug, "stance": max 22 words, the core of their argument}}], "conclusion": 2-3 sentences: where it landed / the key insight, "tension": one sentence naming what stayed unresolved (or null)}}
- "outcome": 2-3 sentences written weeks later by {name} about what they actually did (not always a happy ending).
- "comments": 5-8 comments from other community members. Each {{"gender": "m" or "f", "text": 1-3 sentences, varied (relating their own experience with specifics, disagreeing with one figure by name, a question to {first}), "likes": int 0-120}}. Include exactly one reply from {first} with "is_author": true (put it after the comment it answers).

Return ONLY JSON: {{"transcript": [{{"speaker": ..., "text": ...}}], "summary": {{...}}, "outcome": ..., "comments": [...]}}"""

FIRST = {
    'm': ['Daniel', 'Kenji', 'Mateo', 'Omar', 'Lukas', 'Arjun', 'Theo', 'Samuel', 'Wei', 'Jonas', 'Rafael', 'Ethan', 'Malik', 'Hugo', 'Tomás',
          'Ivan', 'Noah', 'Felix', 'Kwame', 'Leo', 'Marco', 'Yusuf', 'Ben', 'Hiro', 'Adrian', 'Elias', 'Pavel', 'Sanjay', 'Jun', 'Oscar',
          'Diego', 'Nikolai', 'Amir', 'Callum', 'Rohan', 'Sebastian', 'Tariq', 'Finn', 'Minh', 'Gabriel'],
    'f': ['Maya', 'Ines', 'Priya', 'Hannah', 'Yuki', 'Sofia', 'Amara', 'Clara', 'Lena', 'Nadia', 'Zoe', 'Mei', 'Fatima', 'Elena', 'Ruth',
          'Aisha', 'Julia', 'Chloe', 'Ingrid', 'Leila', 'Rosa', 'Anya', 'Grace', 'Noor', 'Camille', 'Hana', 'Tess', 'Lucia', 'Imani', 'Freya',
          'Mira', 'Sana', 'Olivia', 'Beatriz', 'Keiko', 'Nora', 'Talia', 'Esther', 'Linh', 'Vera'],
}


def member_pool(taken: set[str]) -> dict[str, list[dict]]:
    rng = random.Random(11)
    pool = {}
    for g, folder in (('m', 'men'), ('f', 'women')):
        photos = [f'{folder}-{i:02d}.jpg' for i in range(100) if (PHOTOS / f'{folder}-{i:02d}.jpg').exists() and f'{folder}-{i:02d}.jpg' not in taken]
        names = FIRST[g][:]
        rng.shuffle(names)
        pool[g] = [{'name': f'{names[i % len(names)]} {chr(65 + rng.randrange(26))}.', 'avatar': f'assets/story-users/{p}'} for i, p in enumerate(photos)]
    return pool


def plan_order(uid: str, owner: str, participants: list[str]) -> tuple[list[str], int]:
    """A fixed speaking order in which the story's owner clearly speaks the most."""
    rng = random.Random('order-' + uid)
    others = [p for p in participants if p != owner]
    rng.shuffle(others)
    opening = [owner] + others
    if rng.random() < 0.5:           # the owner does not always open
        opening = [others[0], owner] + others[1:]
    order = ['user'] + opening
    per_other = 3 if len(others) >= 3 else 4      # further turns for each other figure
    queue = [o for _ in range(per_other) for o in others]
    rng.shuffle(queue)
    hosts = {2, len(queue) // 2}                   # where the host steers
    users = set(range(1, len(queue), 2))           # where the user cuts in
    for i, other in enumerate(queue):
        if i in hosts:
            order.append('host')
        if i in users:
            order.append('user')
        # every third exchange the figures answer each other directly, without the owner in between
        last_figure = next(x for x in reversed(order) if x not in ('user', 'host'))
        if order[-1] != owner and (i % 3 != 2 or last_figure == other):
            order.append(owner)
        order.append(other)
    order += [owner, 'user', 'host'] + others + [owner, 'user']
    return order, len(opening) + 1


def owner_ok(tr, owner, participants):
    c = collections.Counter(t['speaker'] for t in tr if t['speaker'] in participants)
    return c[owner] >= max(v for k, v in c.items() if k != owner) + int(os.environ.get('OWNER_MARGIN', '2')) if len(c) > 1 else True


async def gen(llm, user, owner, mode, participants, names, sem):
    async with sem:
        base = dict(name=user['name'], first=user['name'].split()[0], age=user['age'], role=user['role'], city=user['city'],
                    question=user['question'], context=user['context'], advisor=owner, advisor_name=names[owner],
                    participant_list=', '.join(f'{names[p]} (slug "{p}")' for p in participants))
        if mode != 'solo':
            order, open_end = plan_order(user['id'], owner, participants)
            base.update(order='\n'.join(f'{i}. {sp}' for i, sp in enumerate(order, 1)), n_turns=len(order), open_end=open_end)
        prompt = (SOLO if mode == 'solo' else TABLE).format(**base) + TAIL.format(**base)
        allowed = set(participants) | {'user', 'host'}
        for attempt in range(6):
            try:
                data = await llm.chat_json([{'role': 'user', 'content': prompt}], temperature=0.9, max_tokens=16000)
                tr = [t for t in data['transcript'] if t.get('speaker') in allowed and t.get('text')]
                need = 18 if mode == 'solo' else 24
                assert len(tr) >= need, f'short {len(tr)}'
                if mode != 'solo':
                    assert owner_ok(tr, owner, participants), 'owner not leading'
                assert data['summary']['positions'] and data['summary']['conclusion']
                data['transcript'] = tr
                print('ok', user['id'], mode, len(tr), flush=True)
                return data
            except Exception as exc:  # noqa: BLE001
                print('retry', user['id'], attempt, repr(exc)[:150], flush=True)
        return None


def assemble(community, cache):
    taken = {Path(u['avatar']).name for a in community['advisors'] for u in a['users'] if u.get('avatar')}
    pool = member_pool(taken)
    for adv in community['advisors']:
        for u in adv['users']:
            s = cache.get(u['id'])
            if not s:
                continue
            rng = random.Random(u['id'])
            used = set()
            comments = []
            for c in s.get('comments', []):
                if not c.get('text'):
                    continue
                if c.get('is_author'):
                    comments.append({'name': u['name'], 'avatar': u.get('avatar'), 'text': c['text'], 'likes': int(c.get('likes') or 0), 'is_author': True})
                    continue
                g = c.get('gender') if c.get('gender') in ('m', 'f') else rng.choice('mf')
                choices = [m for m in pool[g] if m['name'] not in used]
                m = rng.choice(choices)
                used.add(m['name'])
                comments.append({**m, 'text': c['text'], 'likes': int(c.get('likes') or 0)})
            u.update(transcript=s['transcript'], summary=s['summary'], outcome=s.get('outcome') or u.get('outcome'), comments=comments)
    community['version'] = 4


async def main():
    community = json.loads(DATA.read_text())
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    names = community['names']
    llm = MiniMaxService()
    sem = asyncio.Semaphore(12)
    jobs = []
    only = set(sys.argv[1:])
    for adv in community['advisors']:
        names.setdefault(adv['slug'], adv['name'])
        for u in adv['users']:
            parts = u.get('participants') or [adv['slug']]
            if parts[0] != adv['slug']:
                parts = [adv['slug']] + [p for p in parts if p != adv['slug']]
                u['participants'] = parts
            if u['id'] not in cache and (not only or u['id'] in only):
                jobs.append((u, adv['slug'], u['mode'], parts))
    print('todo', len(jobs), flush=True)

    async def run(job):
        res = await gen(llm, *job, names, sem)
        if res:
            cache[job[0]['id']] = res
            CACHE.write_text(json.dumps(cache, ensure_ascii=False))

    await asyncio.gather(*(run(j) for j in jobs))
    assemble(community, cache)
    DATA.write_text(json.dumps(community, ensure_ascii=False, indent=1))
    OUT_JS.write_text('// Illustrative community: fictional users and their sample sessions (generated; not real people).\n'
                      'window.STORY_COMMUNITY = ' + json.dumps(community, ensure_ascii=False, separators=(',', ':')) + ';\n')
    print('done', len(cache), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
