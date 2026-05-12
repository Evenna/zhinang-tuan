from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import KnowledgeChunk, Person
from app.utils.text import keyword_overlap_score, tokenize, truncate_text

settings = get_settings()


@dataclass
class RetrievedChunkResult:
    chunk_type: str
    title: str
    source_name: str
    score: float
    excerpt: str
    content: str


class RetrievalService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def retrieve_for_person(self, person: Person, question: str, limit: Optional[int] = None) -> list[RetrievedChunkResult]:
        limit = limit or settings.max_context_chunks
        chunks = self.db.scalars(select(KnowledgeChunk).where(KnowledgeChunk.person_id == person.id)).all()
        if not chunks:
            return []

        question_tokens = tokenize(question)
        ranked: list[tuple[float, KnowledgeChunk]] = []
        for chunk in chunks:
            score = self._score_chunk(chunk, question_tokens)
            ranked.append((score, chunk))
        ranked.sort(key=lambda item: item[0], reverse=True)

        results = []
        for score, chunk in ranked[:limit]:
            results.append(
                RetrievedChunkResult(
                    chunk_type=chunk.chunk_type,
                    title=chunk.title,
                    source_name=chunk.source_name,
                    score=round(score, 4),
                    excerpt=truncate_text(chunk.content, 280),
                    content=chunk.content,
                )
            )
        return results

    def _score_chunk(self, chunk: KnowledgeChunk, question_tokens: list[str]) -> float:
        text = ' '.join([chunk.title, chunk.content, ' '.join(chunk.theme_tags or [])])
        lexical = keyword_overlap_score(question_tokens, tokenize(text))
        source_boost = chunk.source_priority / 100.0
        return (chunk.importance_score * 0.5) + (lexical * 0.35) + (source_boost * 0.15)
