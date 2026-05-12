from __future__ import annotations

import re


def unique_clean(values: list[str]) -> list[str]:
    seen = set()
    results: list[str] = []
    for value in values:
        text = str(value or '').strip()
        if not text or text in seen:
            continue
        seen.add(text)
        results.append(text)
    return results


def tokenize(text: str) -> list[str]:
    if not text:
        return []
    lowered = text.lower()
    english_tokens = re.findall(r'[a-z0-9]+', lowered)
    chinese_tokens = [char for char in lowered if '一' <= char <= '鿿']
    return english_tokens + chinese_tokens


def keyword_overlap_score(question_tokens: list[str], candidate_tokens: list[str]) -> float:
    if not question_tokens or not candidate_tokens:
        return 0.0
    qset = set(question_tokens)
    cset = set(candidate_tokens)
    overlap = len(qset & cset)
    return overlap / max(len(qset), 1)


def truncate_text(text: str, limit: int) -> str:
    text = (text or '').strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + '...'


def split_text_semantic(text: str, *, chunk_size: int = 700, overlap: int = 80) -> list[str]:
    text = (text or '').strip()
    if not text:
        return []

    paragraphs = [part.strip() for part in re.split(r'\\n+', text) if part.strip()]
    chunks: list[str] = []
    current = ''
    for paragraph in paragraphs:
        candidate = f'{current}\\n\\n{paragraph}'.strip() if current else paragraph
        if len(candidate) <= chunk_size:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(paragraph) <= chunk_size:
            current = paragraph
            continue
        start = 0
        while start < len(paragraph):
            end = min(start + chunk_size, len(paragraph))
            piece = paragraph[start:end].strip()
            if piece:
                chunks.append(piece)
            if end >= len(paragraph):
                break
            start = max(0, end - overlap)
        current = ''
    if current:
        chunks.append(current)
    return chunks
