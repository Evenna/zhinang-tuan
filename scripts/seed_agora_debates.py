"""Seed the Agora with illustrative debates by fictional visitors (runs against the local backend)."""
import json, random, sys, time, re
from pathlib import Path
import requests

API = 'http://127.0.0.1:8000/api/agora'
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'backend' / 'data' / 'agora_debates.json'
AVATARS = sorted(p.name for p in (ROOT / 'assets' / 'story-users').glob('*.jpg'))
PER_HALL = int(sys.argv[1]) if len(sys.argv) > 1 else 4
random.seed(42)

import yaml
cfg = yaml.safe_load(open('/root/.hermes/profiles/yiwen/config.yaml'))['model']


def llm_json(prompt):
    for _ in range(3):
        r = requests.post(cfg['base_url'].rstrip('/') + '/chat/completions', headers={'Authorization': 'Bearer ' + cfg['api_key']},
                          json={'model': 'deepseek-v4-flash', 'max_tokens': 1500, 'temperature': 0.9, 'messages': [{'role': 'user', 'content': prompt}]}, timeout=120)
        try:
            t = r.json()['choices'][0]['message']['content']
            return json.loads(re.search(r'\{.*\}', t, re.S).group(0))
        except Exception as e:
            print('retry json', e, file=sys.stderr)
    raise RuntimeError('llm json failed')


def post(path, body):
    for _ in range(3):
        r = requests.post(API + path, json=body, timeout=200)
        if r.ok:
            return r.json()
        print('retry', path, r.status_code, r.text[:200], file=sys.stderr)
        time.sleep(3)
    raise RuntimeError(path)


existing = json.loads(OUT.read_text())['debates'] if OUT.exists() else []
done = {d['id'] for d in existing}
halls = requests.get(API + '/halls').json()['halls']
used_avatars = {d['avatar'].split('/')[-1] for d in existing}
for hall in halls:
    detail = requests.get(f"{API}/halls/{hall['id']}").json()
    residents = [r['slug'] for r in detail['residents']]
    for i in range(PER_HALL):
        did = f"agora/{hall['id']}-{i:02d}"
        if did in done:
            continue
        motion = hall['motions'][i % len(hall['motions'])]
        seats = random.sample(residents[:14], random.choice([3, 4, 4, 5]))
        avatar = random.choice([a for a in AVATARS if a not in used_avatars] or AVATARS)
        used_avatars.add(avatar)
        gender = 'woman' if avatar.startswith('women') else 'man'
        age = int(re.search(r'(\d+)', avatar).group(1)) % 40 + 20
        persona = llm_json(
            f'Invent a believable fictional {gender}, about {age}, from anywhere in the world, who came to an online "Agora" to watch historical minds debate: "{motion}". '
            'The motion matters to their real life right now. Return JSON: {"name": "First Last", "role": "job", "city": "City, Country", '
            '"why": "2 sentences, first person, the personal situation that made them convene this debate", '
            '"questions": ["a sharp follow-up question they ask the floor mid-debate", "a second, more personal question"], '
            '"outcome": "3 sentences, first person, written weeks later: what they actually did after the debate, honest and specific, not a fairy tale"}')
        transcript, stances = [], {}
        transcript.append({'speaker': 'user', 'text': persona['why'], 'round': 0})
        for rnd in range(1, 4):
            q = persona['questions'][rnd - 2] if rnd >= 2 and len(persona['questions']) >= rnd - 1 else None
            target = random.choice(seats) if rnd == 3 and random.random() < 0.5 else None
            if q:
                transcript.append({'speaker': 'user', 'text': (f'@{target} ' if target else '') + q, 'round': rnd})
            res = post('/round', {'motion': motion, 'seats': seats, 'transcript': transcript, 'stances': stances,
                                  'question': q, 'target': target, 'round': rnd})
            for t in res['turns']:
                transcript.append({'speaker': t['speaker'], 'text': t['text'], 'stance': t['stance'], 'move': t['move'], 'round': rnd})
            stances = res['stances']
        verdict = post('/verdict', {'motion': motion, 'seats': seats, 'transcript': transcript, 'stances': stances})
        social = llm_json(
            f'Debate motion: "{motion}". Verdict: {verdict["summary"]}. Write 3-5 short comments other visitors left under this published debate. '
            'Varied voices, specific, some disagree, one may be from the author replying. Return JSON: {"comments": [{"name": "First L.", "text": "...", "is_author": false}]}')
        date = f"2026-{random.choice([9, 10, 11]):02d}-{random.randint(1, 26):02d}"
        likes = random.randint(40, 620)
        debate = {
            'id': did, 'hall': hall['id'], 'motion': motion, 'mode': 'agora', 'published': True,
            'name': persona['name'], 'avatar': f'assets/story-users/{avatar}', 'age': age, 'role': persona['role'], 'city': persona['city'],
            'date': date, 'headline': verdict['headline'], 'question': motion, 'context': persona['why'], 'outcome': persona['outcome'],
            'topics': [hall['title']], 'participants': seats, 'stances': stances, 'tally': verdict['tally'],
            'transcript': transcript, 'verdict': {k: verdict[k] for k in ('for', 'against', 'open')},
            'summary': {'tldr': verdict['summary'], 'positions': verdict['positions'], 'conclusion': verdict['summary'], 'tension': verdict['tension']},
            'comments': [{**c, 'likes': random.randint(0, 60)} for c in social.get('comments', [])],
            'likes': likes, 'shares': likes // random.randint(5, 12), 'saves': likes // random.randint(3, 6),
        }
        existing.append(debate)
        OUT.write_text(json.dumps({'version': 1, 'demo': True, 'debates': existing}, ensure_ascii=False, indent=1))
        print('ok', did, persona['name'], len(transcript), flush=True)
print('DONE', len(existing))
