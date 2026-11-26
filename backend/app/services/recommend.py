from __future__ import annotations

import re
from collections import defaultdict
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.prompts import build_recommend_prompt
from app.db.models import KnowledgeChunk, Person, PersonaProfile
from app.schemas.recommend import RecommendationItem, RecommendRequest, RecommendResponse
from app.services.llm import MiniMaxService
from app.utils.text import keyword_overlap_score, tokenize

settings = get_settings()
LIFE_CHUNK_TYPES = {'summary', 'story_seed', 'biography_extract'}
LIFE_HINTS = (
    'relationship', 'married', 'marriage', 'wife', 'husband', 'lover', 'affair',
    'partner', 'open relationship', 'divorce', 'love', 'romance',
    '婚姻', '妻子', '丈夫', '恋人', '情人', '出轨', '开放', '伴侣', '同居', '离婚', '爱情',
)
EXTRA_ALIASES = {
    'simone-de-beauvoir': ['波伏娃', '波弗娃', '波伏瓦', 'Beauvoir'],
    'jean-paul-sartre': ['萨特', 'Sartre'],
}

CATEGORY_HINTS = {
    'career': ['work', 'career', 'job', 'business', 'management', '工作', '职业', '跳槽', '升职', '创业', '公司', '老板', '管理', '方向'],
    'relationship': ['relationship', 'love', 'marriage', 'partner', 'affair', 'forgive', '关系', '爱情', '婚姻', '伴侣', '朋友', '家人', '分手', '沟通', '出轨', '原谅', '开放', '接受'],
    'growth': ['anxiety', 'meaning', 'growth', 'choice', 'life', '焦虑', '人生', '意义', '成长', '选择', '迷茫', '内耗', '自我'],
    'creative': ['creative', 'writing', 'art', 'inspiration', '创作', '灵感', '写作', '艺术', '表达', '作品', '风格'],
    'study': ['study', 'research', 'learning', 'knowledge', '学习', '研究', '方法', '思考', '知识', '论文'],
}

CATEGORY_TO_DOMAIN = {
    'career': ['商业', '历史', '科学'],
    'relationship': ['文学', '哲学'],
    'growth': ['哲学', '文学', '历史'],
    'creative': ['艺术', '文学'],
    'study': ['科学', '哲学'],
}


class RecommendService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.llm_service = MiniMaxService()

    async def recommend(self, request: RecommendRequest) -> RecommendResponse:
        people = self._load_people()
        life_notes = self._load_life_notes(people)
        top_k = request.top_k or settings.recommendation_top_k
        keyword_items = self._keyword_rank(request.question, people, life_notes)
        llm_items = await self._llm_rank(request.question, people, life_notes, top_k)
        merged = self._merge_picks(llm_items, keyword_items, people, life_notes, request.question, top_k)
        return RecommendResponse(question=request.question, recommendations=merged)

    def _load_people(self) -> list[tuple[Person, Optional[PersonaProfile]]]:
        people = self.db.scalars(select(Person).order_by(Person.chinese_name)).all()
        loaded: list[tuple[Person, Optional[PersonaProfile]]] = []
        for person in people:
            profile = self.db.scalar(
                select(PersonaProfile)
                .where(PersonaProfile.person_id == person.id)
                .order_by(desc(PersonaProfile.version))
            )
            loaded.append((person, profile))
        return loaded

    def _load_life_notes(self, people: list[tuple[Person, Optional[PersonaProfile]]]) -> dict[str, dict[str, str]]:
        person_ids = [person.id for person, _ in people]
        chunks = self.db.scalars(
            select(KnowledgeChunk).where(
                KnowledgeChunk.person_id.in_(person_ids),
                KnowledgeChunk.chunk_type.in_(LIFE_CHUNK_TYPES),
            )
        ).all()
        grouped: dict[str, list[str]] = defaultdict(list)
        for chunk in chunks:
            grouped[chunk.person_id].append(chunk.content or '')

        name_to_label: dict[str, str] = {}
        for person, _ in people:
            for alias in person_name_aliases(person):
                name_to_label[alias] = person.chinese_name

        notes: dict[str, dict[str, str]] = {}
        for person, profile in people:
            blob = ' '.join(grouped.get(person.id, []))
            related: list[str] = []
            for alias, label in name_to_label.items():
                if label == person.chinese_name:
                    continue
                if alias and alias in blob and label not in related:
                    related.append(label)
            notes[person.slug] = {
                'life': _compact_life_note(blob, profile),
                'related': ' / '.join(related[:3]),
            }

        name_to_slug = {person.chinese_name: person.slug for person, _ in people}
        related_map = {
            slug: [name for name in (info.get('related') or '').split(' / ') if name]
            for slug, info in notes.items()
        }
        for slug, names in list(related_map.items()):
            source_name = next((person.chinese_name for person, _ in people if person.slug == slug), '')
            for name in names:
                other_slug = name_to_slug.get(name)
                if not other_slug or not source_name:
                    continue
                other_related = related_map.setdefault(other_slug, [])
                if source_name not in other_related:
                    other_related.append(source_name)
        for slug, names in related_map.items():
            if slug in notes:
                notes[slug]['related'] = ' / '.join(names[:3])
        return notes

    def _keyword_rank(
        self,
        question: str,
        people: list[tuple[Person, Optional[PersonaProfile]]],
        life_notes: dict[str, dict[str, str]],
    ) -> list[RecommendationItem]:
        question_tokens = tokenize(question)
        inferred_categories = self._infer_categories(question)
        scored: list[tuple[float, Person, Optional[PersonaProfile]]] = []
        for person, profile in people:
            life = life_notes.get(person.slug, {})
            haystack = ' '.join(
                [
                    person.chinese_name,
                    person.english_name,
                    person.domain_category,
                    person.ai_archetype,
                    person.brief_intro,
                    life.get('life', ''),
                    life.get('related', ''),
                    ' '.join(profile.preferred_topics if profile else []),
                    ' '.join(profile.core_traits if profile else []),
                ]
            )
            score = keyword_overlap_score(question_tokens, tokenize(haystack))
            life_text = f"{life.get('life', '')} {life.get('related', '')}".lower()
            if any(hint in question for hint in CATEGORY_HINTS['relationship']) and any(
                hint in life_text for hint in LIFE_HINTS
            ):
                score += 0.45
            for category in inferred_categories:
                if any(domain in person.domain_category for domain in CATEGORY_TO_DOMAIN.get(category, [])):
                    score += 0.08
            if person.is_fictional and 'career' in inferred_categories:
                score -= 0.08
            scored.append((score, person, profile))

        scored.sort(key=lambda item: item[0], reverse=True)
        items = []
        for score, person, profile in scored:
            items.append(self._to_item(person, profile, round(max(score, 0.01), 4), life_notes.get(person.slug, {})))
        return items

    async def _llm_rank(
        self,
        question: str,
        people: list[tuple[Person, Optional[PersonaProfile]]],
        life_notes: dict[str, dict[str, str]],
        top_k: int,
    ) -> list[RecommendationItem]:
        by_slug = {person.slug: (person, profile) for person, profile in people}
        catalog = '\n'.join(self._catalog_line(person, life_notes.get(person.slug, {})) for person, _profile in people)
        payload = await self.llm_service.chat_json(
            [
                {'role': 'system', 'content': '你只输出合法 JSON，不输出任何其他文字。'},
                {'role': 'user', 'content': build_recommend_prompt(question, catalog, top_k)},
            ],
            temperature=0.2,
            max_tokens=800,
        )
        raw_items = payload.get('recommendations') if isinstance(payload, dict) else None
        if not isinstance(raw_items, list):
            return []

        picked: list[RecommendationItem] = []
        seen: set[str] = set()
        for entry in raw_items:
            if not isinstance(entry, dict):
                continue
            slug = str(entry.get('person_slug') or '').strip()
            if slug not in by_slug or slug in seen:
                continue
            person, profile = by_slug[slug]
            reason = str(entry.get('reason') or '').strip() or self._fallback_reason(person, profile, life_notes.get(slug, {}))
            try:
                score = float(entry.get('score') or 0.8)
            except (TypeError, ValueError):
                score = 0.8
            picked.append(
                RecommendationItem(
                    person_slug=person.slug,
                    person_name=person.english_name,
                    reason=reason,
                    score=round(min(max(score, 0.01), 1.0), 4),
                )
            )
            seen.add(slug)
            if len(picked) >= top_k:
                break
        return picked

    def _merge_picks(
        self,
        llm_items: list[RecommendationItem],
        keyword_items: list[RecommendationItem],
        people: list[tuple[Person, Optional[PersonaProfile]]],
        life_notes: dict[str, dict[str, str]],
        question: str,
        top_k: int,
    ) -> list[RecommendationItem]:
        merged = self._expand_related_pairs(llm_items, people, life_notes, question, top_k)
        seen = {item.person_slug for item in merged}
        for item in keyword_items:
            if item.person_slug in seen:
                continue
            merged.append(item)
            seen.add(item.person_slug)
            if len(merged) >= top_k:
                break
        return self._expand_related_pairs(merged[:top_k], people, life_notes, question, top_k)[:top_k]

    def _expand_related_pairs(
        self,
        items: list[RecommendationItem],
        people: list[tuple[Person, Optional[PersonaProfile]]],
        life_notes: dict[str, dict[str, str]],
        question: str,
        top_k: int,
    ) -> list[RecommendationItem]:
        if not items or not any(hint in question for hint in CATEGORY_HINTS['relationship']):
            return items[:top_k]

        by_name = {person.chinese_name: person for person, _profile in people}
        expanded: list[RecommendationItem] = []
        seen: set[str] = set()
        for item in items:
            if item.person_slug not in seen:
                expanded.append(item)
                seen.add(item.person_slug)
            related = life_notes.get(item.person_slug, {}).get('related', '')
            for name in [part.strip() for part in related.split(' / ') if part.strip()]:
                if len(expanded) >= top_k:
                    return expanded[:top_k]
                person = by_name.get(name)
                if not person or person.slug in seen:
                    continue
                expanded.append(
                    RecommendationItem(
                        person_slug=person.slug,
                        person_name=person.english_name,
                        reason=f'Shares directly relevant experiences with {item.person_name}.',
                        score=round(max(item.score - 0.02, 0.5), 4),
                    )
                )
                seen.add(person.slug)
        return expanded[:top_k]

    def _catalog_line(self, person: Person, life: dict[str, str]) -> str:
        return '\t'.join(
            [
                person.slug,
                person.chinese_name,
                person.english_name,
                person.domain_category or '',
                life.get('life') or (person.brief_intro or '')[:80],
                life.get('related') or '',
            ]
        )

    def _to_item(
        self,
        person: Person,
        profile: Optional[PersonaProfile],
        score: float,
        life: dict[str, str],
    ) -> RecommendationItem:
        return RecommendationItem(
            person_slug=person.slug,
            person_name=person.english_name,
            reason=self._fallback_reason(person, profile, life),
            score=score,
        )

    def _fallback_reason(self, person: Person, profile: Optional[PersonaProfile], life: dict[str, str]) -> str:
        return f"{person.english_name} offers a perspective grounded in their own work and life experience."

    def _infer_categories(self, question: str) -> list[str]:
        inferred = []
        for category, keywords in CATEGORY_HINTS.items():
            if any(keyword in question for keyword in keywords):
                inferred.append(category)
        return inferred or ['growth']


def person_name_aliases(person: Person) -> list[str]:
    names = {
        person.chinese_name,
        person.english_name,
        person.chinese_name.replace('·', ''),
        person.english_name.replace('-', ' '),
    }
    for part in person.chinese_name.split('·'):
        if len(part) >= 2:
            names.add(part)
    english_parts = person.english_name.replace('-', ' ').split()
    if english_parts:
        names.add(english_parts[-1])
    names.update(EXTRA_ALIASES.get(person.slug, []))
    return [name for name in names if name and len(name) >= 2]


def text_mentions_alias(text: str, alias: str) -> bool:
    if not alias or not text:
        return False
    if re.search(r'[\u4e00-\u9fff]', alias):
        return alias in text
    if len(alias) < 4:
        return False
    return re.search(rf'\b{re.escape(alias)}\b', text, re.I) is not None


def _compact_life_note(blob: str, profile: Optional[PersonaProfile]) -> str:
    text = re.sub(r'\s+', ' ', blob or '').strip()
    if not text:
        notes = (profile.generation_notes or {}).get('notes') if profile else None
        text = ' '.join(notes or [])
    sentences = [part.strip() for part in re.split(r'(?<=[.。!?])\s+', text) if part.strip()]
    preferred = [sentence for sentence in sentences if any(hint in sentence.lower() for hint in LIFE_HINTS)]
    chosen = ' '.join((preferred or sentences)[:2]) or text
    return chosen[:180]
