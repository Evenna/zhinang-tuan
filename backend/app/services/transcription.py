from __future__ import annotations

import base64
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx
from fastapi import HTTPException

from app.core.config import get_settings


class StepFunTranscriptionService:
    AUDIO_SUFFIXES = {'.mp3', '.wav', '.ogg', '.pcm'}

    def __init__(self) -> None:
        self.settings = get_settings()

    async def transcribe_media(self, raw: bytes, filename: str) -> tuple[str, list[dict]]:
        if not self.settings.stepfun_api_key:
            raise HTTPException(status_code=503, detail='STEPFUN_API_KEY 尚未配置。')
        suffix = Path(filename).suffix.lower()
        audio = raw if suffix in self.AUDIO_SUFFIXES else self._extract_audio(raw, suffix or '.mp4')
        audio_format = suffix.lstrip('.') if suffix in self.AUDIO_SUFFIXES else 'mp3'
        return await self._transcribe_audio(audio, audio_format)

    async def download_media(self, url: str) -> tuple[bytes, str]:
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.stepfun_timeout_seconds,
                follow_redirects=True,
                trust_env=False,
            ) as client:
                response = await client.get(url, headers={'User-Agent': 'ZhinangStudy/1.0'})
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f'视频或音频下载失败：{exc}') from exc
        raw = response.content
        if not raw or len(raw) > 60 * 1024 * 1024:
            raise HTTPException(status_code=413, detail='远程媒体为空或超过 60 MB。')
        filename = Path(httpx.URL(str(response.url)).path).name or 'remote-video.mp4'
        return raw, filename

    def download_video_page(self, url: str) -> tuple[bytes, str]:
        with tempfile.TemporaryDirectory(prefix='zhinang-video-link-') as temp_dir:
            output_template = str(Path(temp_dir) / 'source.%(ext)s')
            command = [
                sys.executable, '-m', 'yt_dlp', '--no-playlist', '--no-progress', '--no-warnings',
                '--max-filesize', '60M', '-f', 'bestaudio/best', '-x', '--audio-format', 'mp3',
                '--audio-quality', '5', '-o', output_template, url,
            ]
            try:
                completed = subprocess.run(command, capture_output=True, timeout=300, check=False)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise HTTPException(status_code=502, detail='视频链接音轨提取超时或工具不可用。') from exc
            output = Path(temp_dir) / 'source.mp3'
            if completed.returncode != 0 or not output.exists():
                raise HTTPException(status_code=400, detail='无法读取该视频页面。请确认链接公开可访问，且平台受支持。')
            raw = output.read_bytes()
            if not raw or len(raw) > 60 * 1024 * 1024:
                raise HTTPException(status_code=413, detail='提取出的音轨为空或超过 60 MB。')
            return raw, output.name

    async def _transcribe_audio(self, audio: bytes, audio_format: str) -> tuple[str, list[dict]]:
        payload = {
            'audio': {
                'data': base64.b64encode(audio).decode('ascii'),
                'input': {
                    'transcription': {
                        'language': 'zh',
                        'hotwords': ['TED', '圆桌', '演讲'],
                        'prompt': '请准确转写演讲、课程或访谈内容，保留中英文专有名词。',
                        'model': self.settings.stepfun_asr_model,
                        'enable_itn': True,
                    },
                    'format': {'type': audio_format},
                },
            }
        }
        headers = {
            'Authorization': f'Bearer {self.settings.stepfun_api_key}',
            'Content-Type': 'application/json',
            'Accept': 'text/event-stream',
        }
        endpoint = f'{self.settings.stepfun_base_url.rstrip("/")}/audio/asr/sse'
        deltas: list[str] = []
        final_text = ''
        try:
            async with httpx.AsyncClient(timeout=self.settings.stepfun_timeout_seconds, trust_env=False) as client:
                async with client.stream('POST', endpoint, json=payload, headers=headers) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        value = line.strip()
                        if not value.startswith('data:'):
                            continue
                        data_text = value[5:].strip()
                        if not data_text or data_text == '[DONE]':
                            continue
                        try:
                            event = json.loads(data_text)
                        except json.JSONDecodeError:
                            continue
                        if event.get('type') == 'transcript.text.delta':
                            deltas.append(str(event.get('delta') or ''))
                        elif event.get('type') == 'transcript.text.done':
                            final_text = str(event.get('text') or '')
                        elif event.get('type') == 'error':
                            raise HTTPException(status_code=502, detail=f'StepFun 转写失败：{event.get("message") or "未知错误"}')
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=502, detail=f'StepFun ASR 请求失败（HTTP {exc.response.status_code}）。') from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f'StepFun ASR 网络错误：{exc}') from exc
        transcript = (final_text or ''.join(deltas)).strip()
        if len(transcript) < 2:
            raise HTTPException(status_code=502, detail='StepFun ASR 未返回有效转写文本。')
        return transcript, []

    def _extract_audio(self, raw: bytes, suffix: str) -> bytes:
        with tempfile.TemporaryDirectory(prefix='zhinang-asr-') as temp_dir:
            source = Path(temp_dir) / f'input{suffix}'
            output = Path(temp_dir) / 'audio.mp3'
            source.write_bytes(raw)
            command = [
                self.settings.ffmpeg_path, '-hide_banner', '-loglevel', 'error', '-y',
                '-i', str(source), '-vn', '-ac', '1', '-ar', '16000', '-b:a', '64k', str(output),
            ]
            try:
                completed = subprocess.run(command, capture_output=True, timeout=180, check=False)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise HTTPException(status_code=500, detail='FFmpeg 音轨提取失败，请检查本机 FFmpeg。') from exc
            if completed.returncode != 0 or not output.exists():
                raise HTTPException(status_code=400, detail='无法从该文件提取音轨，请确认它是有效的音频或视频。')
            return output.read_bytes()
