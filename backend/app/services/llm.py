from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx
from fastapi import HTTPException

from app.core.config import get_settings

settings = get_settings()
THINK_BLOCK_RE = re.compile(r'<think>.*?</think>|<thinking>.*?</thinking>', re.IGNORECASE | re.DOTALL)
JSON_FENCE_RE = re.compile(r'```(?:json)?\s*(.*?)\s*```', re.IGNORECASE | re.DOTALL)


class MiniMaxService:
    def __init__(self) -> None:
        # Fall back to DeepSeek (OpenAI-compatible) when no MiniMax key is configured.
        self.use_deepseek = not settings.minimax_api_key and bool(settings.deepseek_api_key)
        if self.use_deepseek:
            self.base_url = settings.deepseek_base_url.rstrip('/')
            self.api_key = settings.deepseek_api_key
            self.model = settings.deepseek_model
        else:
            self.base_url = settings.minimax_base_url.rstrip('/')
            self.api_key = settings.minimax_api_key
            self.model = settings.minimax_model

    async def chat(self, messages: list[dict[str, str]], *, temperature: float = 0.8, max_tokens: int = 900) -> str:
        if not self.api_key:
            raise HTTPException(status_code=503, detail='MINIMAX_API_KEY is not configured')

        payload = {
            'model': self.model,
            'messages': messages,
            'temperature': min(max(temperature, 0), 2),
            'max_tokens': max_tokens,
            'max_completion_tokens': max_tokens,
            'thinking': {'type': 'disabled'},
        }
        if self.use_deepseek:
            payload.pop('thinking', None)
            payload.pop('max_completion_tokens', None)
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }
        url = f'{self.base_url}/chat/completions'
        try:
            async with httpx.AsyncClient(timeout=float(os.environ.get("LLM_TIMEOUT", "90"))) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=502, detail=_public_llm_error(exc.response.text)) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f'MiniMax network error: {exc}') from exc

        try:
            data = response.json()
            return _extract_text(data)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail='Unexpected MiniMax response format') from exc

    async def chat_json(self, messages: list[dict[str, str]], *, temperature: float = 0.4, max_tokens: int = 700) -> Any:
        raw = await self.chat(messages, temperature=temperature, max_tokens=max_tokens)
        parsed = _extract_json(raw)
        if parsed is None:
            raise HTTPException(status_code=502, detail='MiniMax did not return valid JSON')
        return parsed


def _extract_text(data: dict[str, Any]) -> str:
    message = data['choices'][0]['message']
    content = message.get('content') or ''
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                parts.append(str(part.get('text') or ''))
            else:
                parts.append(str(part))
        content = ''.join(parts)
    content = THINK_BLOCK_RE.sub('', str(content)).strip()
    if not content:
        raise HTTPException(status_code=502, detail='MiniMax returned an empty reply')
    return content


def _extract_json(raw: str) -> Any:
    text = raw.strip()
    fenced = JSON_FENCE_RE.search(text)
    if fenced:
        text = fenced.group(1).strip()
    start = text.find('{')
    end = text.rfind('}')
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


def _public_llm_error(body: str) -> str:
    snippet = (body or '').strip()
    if len(snippet) > 500:
        snippet = snippet[:500] + '…'
    return f'MiniMax API error: {snippet or "unknown error"}'
