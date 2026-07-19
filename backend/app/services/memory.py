from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.db.models import ChatMessage, SessionSummary, UserMemory
from app.services.llm import DeepSeekService


SUMMARY_MESSAGE_INTERVAL = 8
SUMMARY_CHARACTER_THRESHOLD = 3500
MAX_ACTIVE_MEMORIES = 60


class MemoryService:
    """Threshold-based session summaries and durable user memory.

    The service deliberately avoids summarizing every turn. Explicit memory cues
    are handled cheaply on each user message; LLM extraction and summarization
    only run after enough new conversation has accumulated.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.llm = DeepSeekService()

    def latest_summary(self, session_id: str) -> SessionSummary | None:
        return self.db.scalar(
            select(SessionSummary)
            .where(SessionSummary.session_id == session_id)
            .order_by(desc(SessionSummary.message_count), desc(SessionSummary.updated_at))
        )

    def recall(self, user_id: str, query: str, limit: int = 8) -> list[UserMemory]:
        rows = list(
            self.db.scalars(
                select(UserMemory)
                .where(UserMemory.user_id == user_id, UserMemory.status == 'active')
                .order_by(desc(UserMemory.importance), desc(UserMemory.updated_at))
                .limit(80)
            ).all()
        )
        tokens = self._tokens(query)
        now = datetime.now(timezone.utc)

        def score(row: UserMemory) -> float:
            overlap = len(tokens & self._tokens(row.content)) / max(1, len(tokens))
            age_days = max(0.0, (now - self._aware(row.updated_at)).total_seconds() / 86400)
            recency = 1.0 / (1.0 + age_days / 45.0)
            return row.importance * 0.5 + row.confidence * 0.2 + overlap * 0.22 + recency * 0.08

        selected = sorted(rows, key=score, reverse=True)[:limit]
        for row in selected:
            row.last_accessed_at = now
        return selected

    def context(self, user_id: str, session_id: str, query: str) -> tuple[str, list[UserMemory]]:
        summary = self.latest_summary(session_id)
        memories = self.recall(user_id, query)
        blocks: list[str] = []
        if summary and summary.summary:
            blocks.append(f'会话摘要（按阈值更新，不是逐轮摘要）：\n{summary.summary}')
        if memories:
            blocks.append('与当前问题相关的长期用户记忆：\n' + '\n'.join(f'- {row.content}' for row in memories))
        return '\n\n'.join(blocks), memories

    def capture_explicit(self, user_id: str, session_id: str, text: str) -> list[UserMemory]:
        candidates: list[dict[str, Any]] = []
        normalized = ' '.join(text.strip().split())
        rules = [
            ('preference', r'(?:我喜欢|我偏好|我更喜欢|我不喜欢|我习惯|我希望你)([^。！？\n]{2,120})', 0.78),
            ('goal', r'(?:我的目标是|我打算|我正在努力|我想要)([^。！？\n]{2,140})', 0.82),
            ('confirmed_fact', r'(?:我是|我在|我有|我的职业是|我目前)([^。！？\n]{2,140})', 0.68),
            ('instruction', r'(?:请记住|以后记得|记住)([^。！？\n]{2,160})', 0.92),
        ]
        for memory_type, pattern, importance in rules:
            for match in re.finditer(pattern, normalized):
                content = match.group(0).strip(' ，,。')
                if len(content) >= 4:
                    candidates.append({'memory_type': memory_type, 'content': content, 'importance': importance, 'confidence': 0.84})
        return [self._upsert(user_id, session_id, item) for item in candidates[:4]]

    async def maybe_maintain(self, user_id: str, session_id: str, trigger_text: str = '') -> SessionSummary | None:
        self.db.flush()
        messages = list(
            self.db.scalars(
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at)
            ).all()
        )
        if trigger_text:
            self.capture_explicit(user_id, session_id, trigger_text)
        latest = self.latest_summary(session_id)
        previous_count = latest.message_count if latest else 0
        unsummarized = messages[previous_count:]
        new_count = len(messages) - previous_count
        new_chars = sum(len(item.content or '') for item in unsummarized)
        if new_count < SUMMARY_MESSAGE_INTERVAL and new_chars < SUMMARY_CHARACTER_THRESHOLD:
            return latest

        trigger_reason = 'message_interval' if new_count >= SUMMARY_MESSAGE_INTERVAL else 'context_length'
        payload = await self._summarize_and_extract(latest, unsummarized)
        summary_text = str(payload.get('summary') or self._fallback_summary(latest, unsummarized)).strip()
        row = SessionSummary(
            id=str(uuid4()),
            session_id=session_id,
            summary=summary_text[:4000],
            open_questions=self._string_list(payload.get('open_questions'), 8),
            decisions=self._string_list(payload.get('decisions'), 8),
            memory_highlights=self._string_list(payload.get('memory_highlights'), 10),
            message_count=len(messages),
            source_character_count=new_chars,
            trigger_reason=trigger_reason,
        )
        self.db.add(row)
        for item in payload.get('memories', [])[:8] if isinstance(payload.get('memories'), list) else []:
            if isinstance(item, dict):
                self._upsert(user_id, session_id, item)
        self._compress(user_id)
        return row

    async def _summarize_and_extract(self, latest: SessionSummary | None, messages: list[ChatMessage]) -> dict[str, Any]:
        transcript = '\n'.join(f'{item.role}: {item.content[:1200]}' for item in messages[-24:])
        prompt = (
            '你是会话记忆维护器。只输出 JSON，不要 Markdown。\n'
            '目标：压缩会话，并只提取对未来对话稳定、有用的用户偏好、事实、目标和长期指令。'
            '不要保存临时情绪、一次性问题、敏感推断或助手自己的观点。\n'
            'JSON 格式：{"summary":"...","open_questions":[],"decisions":[],"memory_highlights":[],'
            '"memories":[{"memory_type":"preference|confirmed_fact|goal|instruction",'
            '"content":"...","confidence":0.0,"importance":0.0}]}\n'
            f'上一版摘要：{latest.summary if latest else "无"}\n新增对话：\n{transcript}'
        )
        try:
            raw = await self.llm.chat([{'role': 'system', 'content': prompt}], temperature=0.1, max_tokens=1000)
            parsed = self._parse_json(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    def _upsert(self, user_id: str, session_id: str, item: dict[str, Any]) -> UserMemory:
        content = ' '.join(str(item.get('content') or '').strip().split())[:1000]
        memory_type = str(item.get('memory_type') or 'confirmed_fact')[:80]
        key = self._memory_key(content)
        existing = next(
            (
                row for row in self.db.new
                if isinstance(row, UserMemory)
                and row.user_id == user_id
                and row.memory_type == memory_type
                and row.memory_key == key
            ),
            None,
        )
        if existing is None:
            existing = self.db.scalar(
                select(UserMemory).where(
                    UserMemory.user_id == user_id,
                    UserMemory.memory_type == memory_type,
                    UserMemory.memory_key == key,
                )
            )
        confidence = self._clamp(item.get('confidence'), 0.5)
        importance = self._clamp(item.get('importance'), 0.5)
        if existing:
            existing.content = content or existing.content
            existing.confidence = max(existing.confidence, confidence)
            existing.importance = min(1.0, max(existing.importance, importance) + 0.03)
            existing.evidence_count += 1
            existing.status = 'active'
            existing.source_session_id = session_id
            return existing
        row = UserMemory(
            id=str(uuid4()), user_id=user_id, memory_type=memory_type, memory_key=key,
            content=content, confidence=confidence, importance=importance,
            evidence_count=1, status='active', source_session_id=session_id,
            metadata_json={'source': 'threshold_memory_service'},
        )
        self.db.add(row)
        return row

    def _compress(self, user_id: str) -> None:
        rows = list(
            self.db.scalars(
                select(UserMemory)
                .where(UserMemory.user_id == user_id, UserMemory.status == 'active')
                .order_by(desc(UserMemory.importance), desc(UserMemory.confidence), desc(UserMemory.updated_at))
            ).all()
        )
        for row in rows[MAX_ACTIVE_MEMORIES:]:
            if row.importance < 0.82 or row.confidence < 0.8:
                row.status = 'archived'

    def _fallback_summary(self, latest: SessionSummary | None, messages: list[ChatMessage]) -> str:
        snippets = [f'{item.role}: {item.content[:240]}' for item in messages[-8:]]
        previous = latest.summary[:1200] if latest else ''
        return '\n'.join(part for part in [previous, *snippets] if part)

    def _memory_key(self, content: str) -> str:
        normalized = re.sub(r'[^\w\u4e00-\u9fff]+', '', content.lower())[:180]
        return hashlib.sha1(normalized.encode('utf-8')).hexdigest()[:24]

    def _tokens(self, text: str) -> set[str]:
        latin = re.findall(r'[a-z0-9_]{2,}', text.lower())
        cjk = re.findall(r'[\u4e00-\u9fff]', text)
        bigrams = [''.join(cjk[i:i + 2]) for i in range(max(0, len(cjk) - 1))]
        return set(latin + bigrams)

    def _parse_json(self, text: str) -> Any:
        cleaned = text.strip().replace('```json', '').replace('```', '').strip()
        match = re.search(r'\{.*\}', cleaned, re.S)
        try:
            return json.loads(match.group(0) if match else cleaned)
        except Exception:
            return {}

    def _string_list(self, value: Any, limit: int) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip()[:500] for item in value if str(item).strip()][:limit]

    def _clamp(self, value: Any, default: float) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return default

    def _aware(self, value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
