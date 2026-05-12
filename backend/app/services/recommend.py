from __future__ import annotations

from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Person, PersonaProfile
from app.schemas.recommend import RecommendationItem, RecommendRequest, RecommendResponse
from app.utils.text import keyword_overlap_score, tokenize

settings = get_settings()

CATEGORY_HINTS = {
    'career': ['工作', '职业', '跳槽', '升职', '创业', '公司', '老板', '管理', '方向'],
    'relationship': ['关系', '爱情', '婚姻', '伴侣', '朋友', '家人', '分手', '沟通'],
    'growth': ['焦虑', '人生', '意义', '成长', '选择', '迷茫', '内耗', '自我'],
    'creative': ['创作', '灵感', '写作', '艺术', '表达', '作品', '风格'],
    'study': ['学习', '研究', '方法', '思考', '知识', '论文'],
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

    def recommend(self, request: RecommendRequest) -> RecommendResponse:
        people = self.db.scalars(select(Person).order_by(Person.chinese_name)).all()
        question_tokens = tokenize(request.question)
        inferred_categories = self._infer_categories(request.question)

        scored: list[tuple[float, Person, Optional[PersonaProfile]]] = []
        for person in people:
            profile = self.db.scalar(
                select(PersonaProfile)
                .where(PersonaProfile.person_id == person.id)
                .order_by(desc(PersonaProfile.version))
            )
            haystack = ' '.join(
                [
                    person.chinese_name,
                    person.english_name,
                    person.domain_category,
                    person.ai_archetype,
                    person.brief_intro,
                    ' '.join(profile.preferred_topics if profile else []),
                    ' '.join(profile.core_traits if profile else []),
                ]
            )
            score = keyword_overlap_score(question_tokens, tokenize(haystack))
            for category in inferred_categories:
                if any(domain in person.domain_category for domain in CATEGORY_TO_DOMAIN.get(category, [])):
                    score += 0.18
            if person.is_fictional and 'career' in inferred_categories:
                score -= 0.08
            scored.append((score, person, profile))

        scored.sort(key=lambda item: item[0], reverse=True)
        items = []
        for score, person, profile in scored[: request.top_k or settings.recommendation_top_k]:
            reason_bits = [person.domain_category, person.ai_archetype]
            if profile and profile.preferred_topics:
                reason_bits.append('擅长话题: ' + ' / '.join(profile.preferred_topics[:2]))
            items.append(
                RecommendationItem(
                    person_slug=person.slug,
                    person_name=person.chinese_name,
                    reason='；'.join(reason_bits),
                    score=round(max(score, 0.01), 4),
                )
            )
        return RecommendResponse(question=request.question, recommendations=items)

    def _infer_categories(self, question: str) -> list[str]:
        inferred = []
        for category, keywords in CATEGORY_HINTS.items():
            if any(keyword in question for keyword in keywords):
                inferred.append(category)
        return inferred or ['growth']
