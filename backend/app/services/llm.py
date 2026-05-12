from __future__ import annotations

import httpx
from fastapi import HTTPException

from app.core.config import get_settings

settings = get_settings()


class DeepSeekService:
    def __init__(self) -> None:
        self.base_url = settings.deepseek_base_url.rstrip('/')
        self.api_key = settings.deepseek_api_key
        self.model = settings.deepseek_model

    async def chat(self, messages: list[dict[str, str]], *, temperature: float = 0.8, max_tokens: int = 900) -> str:
        if not self.api_key:
            raise HTTPException(status_code=503, detail='DEEPSEEK_API_KEY is not configured')

        payload = {
            'model': self.model,
            'messages': messages,
            'temperature': temperature,
            'max_tokens': max_tokens,
        }
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }
        url = f'{self.base_url}/chat/completions'
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=502, detail=f'DeepSeek API error: {exc.response.text}') from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f'DeepSeek network error: {exc}') from exc

        data = response.json()
        try:
            return data['choices'][0]['message']['content'].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise HTTPException(status_code=502, detail='Unexpected DeepSeek response format') from exc
