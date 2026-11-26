from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import HTTPException

from app.core.config import get_settings

settings = get_settings()


class DeepSeekService:
    def __init__(self) -> None:
        self.base_url = settings.deepseek_base_url.rstrip('/')
        self.api_key = settings.deepseek_api_key
        self.model = settings.deepseek_model

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise HTTPException(status_code=503, detail='DEEPSEEK_API_KEY is not configured')
        return {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }

    def _payload(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
        stream: bool,
    ) -> dict[str, Any]:
        return {
            'model': self.model,
            'messages': messages,
            'temperature': min(max(temperature, 0), 2),
            'max_tokens': max_tokens,
            'stream': stream,
        }

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 600,
    ) -> str:
        url = f'{self.base_url}/chat/completions'
        payload = self._payload(messages, temperature=temperature, max_tokens=max_tokens, stream=False)
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                response = await client.post(url, json=payload, headers=self._headers())
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=502, detail=_public_error(exc.response.text)) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f'DeepSeek network error: {exc}') from exc

        try:
            data = response.json()
            content = data['choices'][0]['message']['content']
            text = str(content or '').strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise HTTPException(status_code=502, detail='Unexpected DeepSeek response format') from exc
        if not text:
            raise HTTPException(status_code=502, detail='DeepSeek returned an empty reply')
        return text

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 600,
    ) -> AsyncIterator[str]:
        url = f'{self.base_url}/chat/completions'
        payload = self._payload(messages, temperature=temperature, max_tokens=max_tokens, stream=True)
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                async with client.stream('POST', url, json=payload, headers=self._headers()) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith('data:'):
                            continue
                        data = line[5:].strip()
                        if not data or data == '[DONE]':
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk['choices'][0].get('delta', {}).get('content') or ''
                        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                            continue
                        if delta:
                            yield str(delta)
        except httpx.HTTPStatusError as exc:
            body = await exc.response.aread()
            raise HTTPException(status_code=502, detail=_public_error(body.decode('utf-8', errors='ignore'))) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f'DeepSeek network error: {exc}') from exc


def _public_error(body: str) -> str:
    snippet = (body or '').strip()
    if len(snippet) > 500:
        snippet = snippet[:500] + '…'
    return f'DeepSeek API error: {snippet or "unknown error"}'
