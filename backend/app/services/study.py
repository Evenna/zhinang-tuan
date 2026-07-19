from __future__ import annotations

import asyncio
import base64
import html
import ipaddress
import json
import re
import zipfile
from collections import Counter
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4
from xml.etree import ElementTree

import httpx
from fastapi import HTTPException
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import KnowledgePack, SourceDocument, SourceKnowledgeChunk, SourceSection, SpeakerCard, VideoSourceAsset
from app.schemas.chat import RetrievedChunk
from app.schemas.roundtable import RoundtableRequest
from app.schemas.study import (
    StudyKnowledgePack,
    StudyRoundtableRequest,
    StudyRoundtableResponse,
    StudySourceCreateRequest,
    StudySourceDetail,
    StudySourceFileImportRequest,
    StudySourceSection,
    StudySourceSummary,
    StudySourceUrlImportRequest,
    StudyVideoImportRequest,
    SpeakerCardGenerateRequest,
    SpeakerCardSummary,
)
from app.services.llm import DeepSeekService
from app.services.roundtable import RoundtableService
from app.services.transcription import StepFunTranscriptionService


VIDEO_UPLOAD_DIR = Path(__file__).resolve().parents[2] / 'data' / 'uploads' / 'videos'


class _HTMLExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.title = ''
        self._in_title = False
        self._skip = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {'script', 'style', 'noscript', 'svg'}:
            self._skip += 1
        elif tag == 'title':
            self._in_title = True
        elif tag in {'p', 'div', 'section', 'article', 'h1', 'h2', 'h3', 'li', 'br'}:
            self.parts.append('\n')

    def handle_endtag(self, tag: str) -> None:
        if tag in {'script', 'style', 'noscript', 'svg'} and self._skip:
            self._skip -= 1
        elif tag == 'title':
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        text = html.unescape(data).strip()
        if not text:
            return
        if self._in_title:
            self.title = f'{self.title} {text}'.strip()
        self.parts.append(text)

    def result(self) -> tuple[str, str]:
        text = '\n'.join(part.strip() for part in ''.join(self.parts).splitlines() if part.strip())
        return self.title[:255], text


class StudySourceService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_source(self, request: StudySourceCreateRequest) -> StudySourceDetail:
        return self._create(
            title=request.title,
            content=request.content,
            source_type=request.source_type,
            user_id=request.user_id,
            original_filename=request.original_filename,
            metadata=request.metadata,
        )

    def import_file(self, request: StudySourceFileImportRequest) -> StudySourceDetail:
        try:
            raw = base64.b64decode(request.content_base64, validate=True) if request.content_base64 else b''
        except Exception as exc:
            raise HTTPException(status_code=400, detail='文件 Base64 内容无效。') from exc
        suffix = Path(request.filename).suffix.lower()
        if raw:
            content = self._extract_bytes(raw, suffix, request.content_type)
        else:
            content = request.content or ''
        if len(content.strip()) < 20:
            raise HTTPException(status_code=400, detail='未能从文件中提取到足够的文本。扫描版 PDF 请先进行 OCR。')
        source_type = {
            '.pdf': 'paper', '.docx': 'document', '.pptx': 'presentation',
            '.md': 'markdown', '.html': 'html', '.htm': 'html', '.txt': 'text',
        }.get(suffix, 'document')
        return self._create(
            title=request.title or Path(request.filename).stem,
            content=content,
            source_type=source_type,
            user_id=request.user_id,
            original_filename=request.filename,
            metadata={**request.metadata, 'content_type': request.content_type, 'size_bytes': len(raw)},
        )

    async def import_url(self, request: StudySourceUrlImportRequest) -> StudySourceDetail:
        self._validate_url(request.url)
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, trust_env=False) as client:
                response = await client.get(request.url, headers={'User-Agent': 'ZhinangStudy/1.0'})
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f'网页读取失败：{exc}') from exc
        content_type = response.headers.get('content-type', '')
        if 'text' not in content_type and 'html' not in content_type and 'json' not in content_type:
            raise HTTPException(status_code=400, detail='该网址不是可读取的文本网页。')
        extractor = _HTMLExtractor()
        extractor.feed(response.text)
        page_title, content = extractor.result()
        if len(content) < 40:
            raise HTTPException(status_code=400, detail='网页正文过短或由脚本动态加载，未能提取。')
        return self._create(
            title=request.title or page_title or urlparse(request.url).netloc,
            content=content[:300000],
            source_type='webpage',
            user_id=request.user_id,
            original_filename=None,
            metadata={**request.metadata, 'url': str(response.url), 'content_type': content_type},
            source_url=str(response.url),
        )

    async def import_video(self, request: StudyVideoImportRequest) -> StudySourceDetail:
        raw = b''
        if request.content_base64:
            try:
                raw = base64.b64decode(request.content_base64, validate=True)
            except Exception as exc:
                raise HTTPException(status_code=400, detail='视频 Base64 内容无效。') from exc
            if len(raw) > 60 * 1024 * 1024:
                raise HTTPException(status_code=413, detail='本地视频文件请控制在 60 MB 内；更大视频请使用对象存储 URL。')
        storage_path: str | None = None
        filename = request.filename or 'video.mp4'
        suffix = Path(filename).suffix.lower() or '.mp4'
        if suffix not in {'.mp4', '.mov', '.m4v', '.webm', '.mkv', '.avi', '.mp3', '.wav', '.ogg', '.pcm'}:
            raise HTTPException(status_code=400, detail='暂不支持该视频格式。')
        transcript = self._normalize(request.transcript)
        segments = request.segments
        if len(transcript) < 20:
            transcriber = StepFunTranscriptionService()
            media = raw
            media_filename = filename
            if not media and request.video_url:
                self._validate_url(request.video_url)
                if request.extract_from_page:
                    self._validate_video_page_url(request.video_url)
                    media, media_filename = await asyncio.to_thread(transcriber.download_video_page, request.video_url)
                else:
                    media, media_filename = await transcriber.download_media(request.video_url)
            transcript, generated_segments = await transcriber.transcribe_media(media, media_filename)
            segments = segments or generated_segments
        if raw:
            VIDEO_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            stored_name = f'{uuid4()}{suffix}'
            target = VIDEO_UPLOAD_DIR / stored_name
            target.write_bytes(raw)
            storage_path = str(target)
        title = request.title or Path(filename).stem or '视频资料'
        detail = self._create(
            title=title,
            content=transcript,
            source_type='video',
            user_id=request.user_id,
            original_filename=request.filename,
            metadata={**request.metadata, 'video_url': request.video_url, 'duration_seconds': request.duration_seconds},
            source_url=request.video_url,
        )
        document = self._document(detail.id, request.user_id)
        transcript = self._normalize(transcript)
        sentences = [item.strip() for item in re.split(r'(?<=[。！？.!?])\s*|\n+', transcript) if len(item.strip()) >= 8]
        segments = segments or [
            {'index': index, 'start': None, 'end': None, 'text': text}
            for index, text in enumerate(self._chunks(transcript, size=700, overlap=0))
        ]
        topics = self._keywords(transcript, 12)
        viewpoints = [item for item in sentences if 18 <= len(item) <= 220][:10]
        quotes = [item for item in sentences if 12 <= len(item) <= 100][:12]
        asset = VideoSourceAsset(
            id=str(uuid4()), document_id=document.id, storage_path=storage_path,
            object_url=request.video_url, transcript=transcript, segments=segments,
            summary=transcript[:900], topics=topics, viewpoints=viewpoints,
            useful_quotes=quotes, duration_seconds=request.duration_seconds,
            metadata_json={'original_filename': request.filename, 'size_bytes': len(raw)},
        )
        self.db.add(asset)
        self.db.commit()
        self.db.refresh(document)
        return self._detail(document)

    def list_sources(self, user_id: str = 'default_user') -> list[StudySourceSummary]:
        rows = self.db.scalars(
            select(SourceDocument).where(SourceDocument.user_id == user_id).order_by(SourceDocument.updated_at.desc())
        ).all()
        return [self._summary(row) for row in rows]

    def get_source(self, source_id: str, user_id: str = 'default_user') -> StudySourceDetail:
        return self._detail(self._document(source_id, user_id))

    def retrieve(self, source_ids: list[str], user_id: str, query: str, limit: int = 8) -> list[SourceKnowledgeChunk]:
        documents = [self._document(source_id, user_id) for source_id in source_ids]
        ids = [item.id for item in documents]
        rows = list(self.db.scalars(select(SourceKnowledgeChunk).where(SourceKnowledgeChunk.document_id.in_(ids))).all())
        query_tokens = self._tokens(query)
        def score(row: SourceKnowledgeChunk) -> float:
            tokens = self._tokens(f'{row.title} {row.summary or ""} {row.content}')
            overlap = len(query_tokens & tokens) / max(1, len(query_tokens))
            return overlap * 0.7 + row.importance_score * 0.3
        return sorted(rows, key=score, reverse=True)[:limit]

    def _create(self, *, title: str, content: str, source_type: str, user_id: str,
                original_filename: str | None, metadata: dict, source_url: str | None = None) -> StudySourceDetail:
        clean = self._normalize(content)
        if len(clean) < 20:
            raise HTTPException(status_code=400, detail='资料内容过短。')
        document = SourceDocument(
            id=str(uuid4()), user_id=user_id, title=title.strip()[:255], source_type=source_type,
            status='compiled', original_filename=original_filename, metadata_json=metadata,
        )
        self.db.add(document)
        self.db.flush()
        sections = self._split_sections(clean, title)
        all_chunks: list[SourceKnowledgeChunk] = []
        for section_index, item in enumerate(sections):
            section = SourceSection(
                id=str(uuid4()), document_id=document.id, title=item['title'][:255],
                section_type='section', order_index=section_index, content=item['content'],
                summary=item['content'][:320], metadata_json={},
            )
            self.db.add(section)
            self.db.flush()
            for chunk_index, chunk_text in enumerate(self._chunks(item['content'])):
                chunk = SourceKnowledgeChunk(
                    id=str(uuid4()), document_id=document.id, section_id=section.id,
                    chunk_type='source_excerpt', title=f'{item["title"]} · {chunk_index + 1}',
                    content=chunk_text, summary=chunk_text[:260], source_name=title[:255],
                    source_url=source_url, source_priority=80,
                    theme_tags=self._keywords(chunk_text, 8),
                    importance_score=max(0.45, 0.88 - section_index * 0.025 - chunk_index * 0.01),
                    embedding=None,
                )
                self.db.add(chunk)
                all_chunks.append(chunk)
        keywords = self._keywords(clean, 18)
        pack = KnowledgePack(
            id=str(uuid4()), document_id=document.id, name=f'{title} · 研读包',
            summary=clean[:900], core_frameworks=keywords[:6],
            topic_index=[{'topic': word} for word in keywords[:12]], glossary=[],
            patterns=keywords[6:12], cheatsheet=[section['content'][:180] for section in sections[:6]],
            compiler_version='study-pack-v2', metadata_json={'section_count': len(sections), 'chunk_count': len(all_chunks)},
        )
        self.db.add(pack)
        self.db.commit()
        self.db.refresh(document)
        return self._detail(document)

    def _extract_bytes(self, raw: bytes, suffix: str, content_type: str) -> str:
        if suffix == '.pdf' or content_type == 'application/pdf':
            try:
                return '\n\n'.join((page.extract_text() or '') for page in PdfReader(BytesIO(raw)).pages)
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f'PDF 解析失败：{exc}') from exc
        if suffix in {'.docx', '.pptx'}:
            try:
                with zipfile.ZipFile(BytesIO(raw)) as archive:
                    prefix = 'word/' if suffix == '.docx' else 'ppt/slides/'
                    names = sorted(name for name in archive.namelist() if name.startswith(prefix) and name.endswith('.xml'))
                    parts: list[str] = []
                    for name in names:
                        root = ElementTree.fromstring(archive.read(name))
                        texts = [node.text for node in root.iter() if node.text and node.tag.rsplit('}', 1)[-1] in {'t', 'p'}]
                        if texts:
                            parts.append(' '.join(texts))
                    return '\n\n'.join(parts)
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f'Office 文件解析失败：{exc}') from exc
        for encoding in ('utf-8-sig', 'utf-8', 'gb18030', 'latin-1'):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        return raw.decode('utf-8', errors='ignore')

    def _split_sections(self, content: str, title: str) -> list[dict[str, str]]:
        lines = content.splitlines()
        result: list[dict[str, str]] = []
        current_title = title
        buffer: list[str] = []
        heading = re.compile(r'^(?:#{1,4}\s+|第[一二三四五六七八九十百0-9]+[章节部分]\s*|[0-9]+[.、]\s+)(.+)$')
        for line in lines:
            match = heading.match(line.strip())
            if match and len('\n'.join(buffer).strip()) >= 80:
                result.append({'title': current_title, 'content': '\n'.join(buffer).strip()})
                current_title = match.group(1).strip() or line.strip()
                buffer = []
            elif line.strip():
                buffer.append(line.strip())
        if buffer:
            result.append({'title': current_title, 'content': '\n'.join(buffer).strip()})
        if not result:
            result = [{'title': title, 'content': content}]
        expanded: list[dict[str, str]] = []
        for item in result:
            if len(item['content']) <= 9000:
                expanded.append(item)
            else:
                for index in range(0, len(item['content']), 7000):
                    expanded.append({'title': f'{item["title"]} {index // 7000 + 1}', 'content': item['content'][index:index + 7000]})
        return expanded[:120]

    def _chunks(self, content: str, size: int = 1200, overlap: int = 160) -> list[str]:
        chunks: list[str] = []
        start = 0
        while start < len(content):
            end = min(len(content), start + size)
            chunks.append(content[start:end].strip())
            if end == len(content):
                break
            start = max(start + 1, end - overlap)
        return [item for item in chunks if item]

    def _normalize(self, content: str) -> str:
        return re.sub(r'\n{3,}', '\n\n', content.replace('\x00', '').replace('\r\n', '\n')).strip()[:300000]

    def _keywords(self, text: str, limit: int) -> list[str]:
        tokens = re.findall(r'[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,8}', text.lower())
        stop = {'这个', '一个', '我们', '你们', '他们', '以及', '可以', '进行', '没有', '什么', '因为', '所以'}
        return [item for item, _ in Counter(token for token in tokens if token not in stop).most_common(limit)]

    def _tokens(self, text: str) -> set[str]:
        latin = re.findall(r'[a-z0-9_]{2,}', text.lower())
        cjk = re.findall(r'[\u4e00-\u9fff]', text)
        return set(latin + [''.join(cjk[i:i + 2]) for i in range(max(0, len(cjk) - 1))])

    def _document(self, source_id: str, user_id: str) -> SourceDocument:
        row = self.db.scalar(select(SourceDocument).where(SourceDocument.id == source_id, SourceDocument.user_id == user_id))
        if not row:
            raise HTTPException(status_code=404, detail='研读资料不存在。')
        return row

    def _summary(self, row: SourceDocument) -> StudySourceSummary:
        pack = row.knowledge_pack
        return StudySourceSummary(
            id=row.id, user_id=row.user_id, title=row.title, source_type=row.source_type, status=row.status,
            section_count=len(row.sections), chunk_count=len(row.chunks), summary=pack.summary[:600] if pack else '',
        )

    def _detail(self, row: SourceDocument) -> StudySourceDetail:
        pack = row.knowledge_pack
        metadata = dict(row.metadata_json or {})
        if row.video_asset:
            metadata['video'] = {
                'storage_path': row.video_asset.storage_path,
                'object_url': row.video_asset.object_url,
                'transcript': row.video_asset.transcript,
                'segments': row.video_asset.segments,
                'summary': row.video_asset.summary,
                'topics': row.video_asset.topics,
                'viewpoints': row.video_asset.viewpoints,
                'useful_quotes': row.video_asset.useful_quotes,
                'duration_seconds': row.video_asset.duration_seconds,
            }
        return StudySourceDetail(
            **self._summary(row).model_dump(), metadata=metadata,
            sections=[StudySourceSection(id=item.id, title=item.title, section_type=item.section_type,
                                         order_index=item.order_index, summary=item.summary or '')
                      for item in sorted(row.sections, key=lambda item: item.order_index)],
            knowledge_pack=StudyKnowledgePack(
                id=pack.id, document_id=pack.document_id, name=pack.name, summary=pack.summary,
                core_frameworks=pack.core_frameworks, topic_index=pack.topic_index, glossary=pack.glossary,
                patterns=pack.patterns, cheatsheet=pack.cheatsheet, compiler_version=pack.compiler_version,
            ) if pack else None,
        )

    def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
            raise HTTPException(status_code=400, detail='仅支持 http/https 网页地址。')
        host = parsed.hostname.lower()
        if host in {'localhost', '127.0.0.1', '::1'} or host.endswith('.local'):
            raise HTTPException(status_code=400, detail='不允许导入本机或内网地址。')
        try:
            if ipaddress.ip_address(host).is_private:
                raise HTTPException(status_code=400, detail='不允许导入内网地址。')
        except ValueError:
            pass

    def _validate_video_page_url(self, url: str) -> None:
        host = (urlparse(url).hostname or '').lower()
        allowed = ('youtube.com', 'youtu.be', 'ted.com', 'bilibili.com', 'vimeo.com')
        if not any(host == item or host.endswith(f'.{item}') for item in allowed):
            raise HTTPException(status_code=400, detail='视频页面链接目前支持 YouTube、TED、Bilibili 和 Vimeo。')


class SpeakerCardService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.llm = DeepSeekService()

    async def generate(self, request: SpeakerCardGenerateRequest) -> SpeakerCardSummary:
        document = self.db.scalar(select(SourceDocument).where(
            SourceDocument.id == request.source_document_id,
            SourceDocument.user_id == request.user_id,
        ))
        if not document:
            raise HTTPException(status_code=404, detail='视频资料不存在。')
        if document.source_type != 'video' or not document.video_asset:
            raise HTTPException(status_code=400, detail='学习型表达角色卡只能从视频资料生成。')
        if request.visibility == 'community' and request.consent_status not in {'self_confirmed', 'authorized'}:
            raise HTTPException(status_code=400, detail='发布到社区前需要确认本人授权或内容授权。')
        transcript = document.video_asset.transcript[:18000]
        prompt = (
            '你是学习型表达角色卡分析器。只分析视频文本中可观察到的观点和表达方式，'
            '不要声称复刻、模拟或代表真人，不推断敏感属性，不补写文本中没有的经历。\n'
            f'视频标题：{document.title}\n转写：\n{transcript}\n\n'
            '仅输出 JSON 对象，字段均为字符串数组：core_claims, speaking_style, thinking_style, '
            'rhetorical_patterns, useful_quotes, discussion_topics, limitations。'
            'useful_quotes 只能摘录转写中实际出现的短句；limitations 必须说明材料范围和角色卡不能代表真人。'
        )
        raw = await self.llm.chat(
            [{'role': 'system', 'content': prompt}], temperature=0.2, max_tokens=1400
        )
        data = self._json_object(raw)
        defaults = {
            'core_claims': document.video_asset.viewpoints[:6],
            'speaking_style': ['依据当前视频转写呈现的表达方式'],
            'thinking_style': ['围绕视频主题组织观点与例证'],
            'rhetorical_patterns': [],
            'useful_quotes': document.video_asset.useful_quotes[:8],
            'discussion_topics': document.video_asset.topics[:8],
            'limitations': ['仅基于当前视频内容生成，不代表或复刻真实人物。'],
        }
        values = {key: self._as_list(data.get(key)) or value for key, value in defaults.items()}
        card = SpeakerCard(
            id=str(uuid4()), user_id=request.user_id, source_document_id=document.id,
            display_name=request.display_name or f'{document.title} · 表达角色',
            role_title=request.role_title or '基于视频内容的学习型表达角色卡',
            consent_status=request.consent_status, visibility=request.visibility,
            metadata_json={'generator': 'speaker-card-v1', 'safety_scope': 'learning_expression_only'},
            **values,
        )
        self.db.add(card)
        self.db.commit()
        self.db.refresh(card)
        return self._schema(card)

    def list_cards(self, user_id: str) -> list[SpeakerCardSummary]:
        rows = self.db.scalars(
            select(SpeakerCard).where(SpeakerCard.user_id == user_id).order_by(SpeakerCard.updated_at.desc())
        ).all()
        return [self._schema(row) for row in rows]

    def get_card(self, card_id: str, user_id: str) -> SpeakerCard:
        row = self.db.scalar(select(SpeakerCard).where(SpeakerCard.id == card_id, SpeakerCard.user_id == user_id))
        if not row:
            raise HTTPException(status_code=404, detail='学习型表达角色卡不存在。')
        return row

    def _schema(self, row: SpeakerCard) -> SpeakerCardSummary:
        return SpeakerCardSummary(
            id=row.id, user_id=row.user_id, source_document_id=row.source_document_id,
            display_name=row.display_name, role_title=row.role_title, core_claims=row.core_claims,
            speaking_style=row.speaking_style, thinking_style=row.thinking_style,
            rhetorical_patterns=row.rhetorical_patterns, useful_quotes=row.useful_quotes,
            discussion_topics=row.discussion_topics, limitations=row.limitations,
            consent_status=row.consent_status, visibility=row.visibility,
        )

    def _json_object(self, value: str) -> dict:
        start, end = value.find('{'), value.rfind('}')
        if start < 0 or end <= start:
            return {}
        try:
            parsed = json.loads(value[start:end + 1])
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _as_list(self, value) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip()[:500] for item in value if str(item).strip()][:12]


class StudyRoundtableService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.sources = StudySourceService(db)
        self.roundtable = RoundtableService(db)

    async def respond(self, request: StudyRoundtableRequest) -> StudyRoundtableResponse:
        chunks = self.sources.retrieve(request.source_ids, request.user_id, request.question, limit=10)
        if not chunks:
            raise HTTPException(status_code=404, detail='所选资料没有可用于研读的文本片段。')
        context = '\n\n'.join(
            f'[资料：{item.source_name}｜{item.title}]\n{item.content[:1500]}' for item in chunks
        )
        mode = {
            'guide': '梳理核心框架、关键概念和作者结论',
            'critique': '检查证据、逻辑跳跃、盲点和适用边界',
            'apply': '把资料转化为针对用户问题的行动方案',
            'compare': '比较资料内部或不同资料之间的观点',
            'debate': '围绕关键争议形成明确的正反交锋',
        }[request.discussion_mode]
        enhanced = (
            f'这是一次研读圆桌。用户问题：{request.question}\n'
            f'解读任务：{mode}。回答必须以资料为主，但不要在回复末尾或句子后添加任何方括号资料标记、引用尾缀或来源编号。\n\n'
            f'资料片段：\n{context}'
        )[:12000]
        result = await self.roundtable.respond(RoundtableRequest(
            question=enhanced[:4000], conversation_id=request.conversation_id,
            memory_text=request.question,
            user_id=request.user_id, preferred_people=request.preferred_people,
            participant_refs=request.participant_refs,
            max_participants=request.max_participants, history=request.history,
        ))
        source_rows = [self.sources._summary(self.sources._document(source_id, request.user_id)) for source_id in request.source_ids]
        citations = [RetrievedChunk(
            chunk_type=item.chunk_type, title=item.title, source_name=item.source_name,
            score=item.importance_score, excerpt=item.content[:360],
        ) for item in chunks]
        cleaned_turns = [turn.model_copy(update={'content': self._clean_reply(turn.content)}) for turn in result.turns]
        return StudyRoundtableResponse(
            conversation_id=result.conversation_id, plan=result.plan, turns=cleaned_turns,
            final_answer=self._clean_reply(result.final_answer), memory=result.memory, sources=source_rows,
            source_citations=citations,
        )

    def _clean_reply(self, content: str) -> str:
        cleaned = content.strip()
        suffix_patterns = [
            r'\s*\[资料\s*[:：][^\]]+\]\s*$',
            r'\s*\[[^\]]+[｜|][^\]]+\]\s*$',
            r'\s*（资料\s*[:：][^）]+）\s*$',
        ]
        changed = True
        while changed:
            changed = False
            for pattern in suffix_patterns:
                updated = re.sub(pattern, '', cleaned, flags=re.I).strip()
                if updated != cleaned:
                    cleaned = updated
                    changed = True
        return cleaned
