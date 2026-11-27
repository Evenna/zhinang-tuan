"""Export the UI and a public-only advisor catalog to the existing GitHub Pages /docs tree.

Run with backend/.venv/bin/python scripts/build_public_preview.py.
The export contains no conversations, API keys, databases, or server environment files.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / 'docs' / 'app'
sys.path.insert(0, str(ROOT / 'backend'))
from sqlalchemy import desc, select
from app.db.models import Person, PersonaProfile
from app.db.session import SessionLocal
from app.schemas.people import PersonDetailResponse, PersonSummaryResponse


def export_image(path: Path) -> tuple[str, str]:
    relative = path.relative_to(ROOT)
    target = DEST / relative.with_suffix('.webp')
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(path) as image:
        image.thumbnail((900, 900), Image.Resampling.LANCZOS)
        image.save(target, 'WEBP', quality=86, method=5)
    return relative.as_posix(), relative.with_suffix('.webp').as_posix()


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    source = (ROOT / 'index.html').read_text()
    images = list((ROOT / 'assets' / 'character_cutouts').glob('*.png'))
    images += list((ROOT / 'assets' / 'home_figures').glob('*.png'))
    images += [ROOT / path for path in set(re.findall(r"assets/portraits-v3-cut/[^'\"]+\.png", source))]
    with ThreadPoolExecutor(max_workers=4) as pool:
        replacements = dict(pool.map(export_image, images))
    for before, after in replacements.items():
        source = source.replace(before, after)
    source = source.replace('assets/character_cutouts/${slug}.png', 'assets/character_cutouts/${slug}.webp')

    for name in ['story-community.js', 'story-community-ui.js', 'story-detail.js', 'story-community.css', 'advisor-life.js', 'advisor-life.css', 'person-timelines.js', 'agora.css', 'agora.js', 'agora-floor.js', 'agora-index-lines.webp', 'agora-debate-lines.webp']:
        shutil.copy2(ROOT / 'assets' / name, DEST / 'assets' / name)
    # Offline snapshot of the Agora (halls, residents, debates on record) for when the backend is unreachable.
    from app.api.routers import agora as agora_api
    with SessionLocal() as db:
        halls = agora_api.list_halls(db)['halls']
        details = {h['id']: agora_api.get_hall(h['id'], db) for h in halls}
    debates = {d['id']: d for d in agora_api._published() + agora_api._seeded()}
    (DEST / 'assets' / 'agora-static.json').write_text(json.dumps({'halls': halls, 'details': details, 'debates': debates}, ensure_ascii=False))
    shutil.copytree(ROOT / 'assets' / 'story-users', DEST / 'assets' / 'story-users', dirs_exist_ok=True)
    catalog = []
    with SessionLocal() as db:
        for person in db.scalars(select(Person).order_by(Person.english_name)):
            summary = PersonSummaryResponse.model_validate(person).model_dump()
            profile = db.scalar(select(PersonaProfile).where(PersonaProfile.person_id == person.id).order_by(desc(PersonaProfile.version)))
            item = PersonDetailResponse(**summary,
                persona_profile=profile.identity if profile else None,
                persona_traits=profile.core_traits if profile else None,
                preferred_topics=profile.preferred_topics if profile else None).model_dump()
            if item.get('portrait_asset') in replacements:
                item['portrait_asset'] = replacements[item['portrait_asset']]
            catalog.append(item)
    data = json.dumps(catalog, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
    adapter = '''// Static UI preview: catalog only; live AI remains on the backend.
window.ASK_SOCRATES_PREVIEW = {
  people: CATALOG,
  async request(path, options = {}) {
    const url = new URL(path, 'https://preview.invalid');
    if ((!options.method || options.method === 'GET') && url.pathname === '/people') {
      const offset = Number(url.searchParams.get('offset') || 0);
      const limit = Number(url.searchParams.get('limit') || 100);
      return this.people.slice(offset, offset + limit);
    }
    if ((!options.method || options.method === 'GET') && url.pathname.startsWith('/people/')) {
      const person = this.people.find(item => item.slug === decodeURIComponent(url.pathname.slice(8)));
      if (person) return person;
      throw new Error('Advisor not found.');
    }
    throw new Error('Live AI replies are not connected in this public preview. Browse the advisors, explore sample stories, or try the sample card deck from Home.');
  }
};
'''.replace('CATALOG', data)
    adapter += '''
window.ASK_SOCRATES_CATALOG = window.ASK_SOCRATES_PREVIEW.people;
// Live mode: when the backend in api-config.js answers, drop the static adapter so every call goes to the real API.
(function () {
  const base = window.ASK_SOCRATES_API;
  if (!base) return;
  const ctrl = new AbortController();
  setTimeout(() => ctrl.abort(), 6000);
  fetch(base + '/health', {signal: ctrl.signal}).then(r => r.ok ? r.json() : null).then(h => {
    if (!h || h.status !== 'ok') return;
    delete window.ASK_SOCRATES_PREVIEW;
    document.documentElement.dataset.live = 'true';
    document.querySelectorAll('.tagline').forEach(el => { if (el.textContent === 'INTERACTIVE PREVIEW') el.textContent = 'LIVE'; });
  }).catch(() => {});
})();
'''
    (DEST / 'public-preview.js').write_text(adapter)
    api_config = DEST / 'api-config.js'
    if not api_config.exists():
        api_config.write_text("window.ASK_SOCRATES_API = '';\n")
    source = source.replace('<script src="assets/story-community.js">', '<script src="api-config.js"></script>\n<script src="public-preview.js"></script>\n<script src="assets/story-community.js">', 1)
    source = source.replace('<span class="tagline">SOCRATES</span>', '<span class="tagline">INTERACTIVE PREVIEW</span>')
    (DEST / 'index.html').write_text(source)
    (DEST / '.nojekyll').write_text('')
    print(f'Exported {len(catalog)} public advisor profiles and {len(replacements)} optimized illustrations to {DEST}')


if __name__ == '__main__':
    main()
