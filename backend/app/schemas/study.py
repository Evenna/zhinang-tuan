from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, model_validator

from app.schemas.chat import ConversationTurn, RetrievedChunk
from app.schemas.roundtable import RoundtableMemoryState, RoundtableParticipantRef, RoundtablePlan, RoundtableTurnResponse


class StudySourceCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=20, max_length=300000)
    source_type: str = Field(default='text', pattern='^(text|markdown|html|paper|book|note|transcript|webpage|document|presentation|video)$')
    user_id: str = Field(default='default_user', min_length=1, max_length=120)
    original_filename: Optional[str] = Field(default=None, max_length=255)
    metadata: dict = Field(default_factory=dict)


class StudySourceFileImportRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content: Optional[str] = Field(default=None, max_length=300000)
    content_base64: Optional[str] = Field(default=None, max_length=20000000)
    content_type: str = Field(default='text/plain', max_length=120)
    title: Optional[str] = Field(default=None, max_length=255)
    user_id: str = Field(default='default_user', min_length=1, max_length=120)
    metadata: dict = Field(default_factory=dict)

    @model_validator(mode='after')
    def require_content(self) -> 'StudySourceFileImportRequest':
        if not (self.content and self.content.strip()) and not (self.content_base64 and self.content_base64.strip()):
            raise ValueError('Either content or content_base64 is required.')
        return self


class StudySourceUrlImportRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    title: Optional[str] = Field(default=None, max_length=255)
    user_id: str = Field(default='default_user', min_length=1, max_length=120)
    metadata: dict = Field(default_factory=dict)


class StudyVideoImportRequest(BaseModel):
    filename: Optional[str] = Field(default=None, max_length=255)
    content_base64: Optional[str] = Field(default=None, max_length=85000000)
    video_url: Optional[str] = Field(default=None, max_length=2000)
    extract_from_page: bool = False
    transcript: str = Field(default='', max_length=300000)
    segments: list[dict] = Field(default_factory=list, max_length=5000)
    title: Optional[str] = Field(default=None, max_length=255)
    user_id: str = Field(default='default_user', min_length=1, max_length=120)
    duration_seconds: Optional[float] = Field(default=None, ge=0, le=86400)
    metadata: dict = Field(default_factory=dict)

    @model_validator(mode='after')
    def require_video_location(self) -> 'StudyVideoImportRequest':
        if not (self.content_base64 and self.content_base64.strip()) and not (self.video_url and self.video_url.strip()):
            raise ValueError('Either video content or video_url is required.')
        return self


class StudySourceSummary(BaseModel):
    id: str
    user_id: str
    title: str
    source_type: str
    status: str
    section_count: int
    chunk_count: int
    summary: str = ''


class StudySourceSection(BaseModel):
    id: str
    title: str
    section_type: str
    order_index: int
    summary: str = ''


class StudyKnowledgePack(BaseModel):
    id: str
    document_id: str
    name: str
    summary: str
    core_frameworks: list[str]
    topic_index: list[dict]
    glossary: list[dict]
    patterns: list[str]
    cheatsheet: list[str]
    compiler_version: str


class StudySourceDetail(StudySourceSummary):
    metadata: dict = Field(default_factory=dict)
    sections: list[StudySourceSection] = Field(default_factory=list)
    knowledge_pack: Optional[StudyKnowledgePack] = None


class SpeakerCardGenerateRequest(BaseModel):
    source_document_id: str
    display_name: Optional[str] = Field(default=None, max_length=160)
    role_title: Optional[str] = Field(default=None, max_length=255)
    user_id: str = Field(default='default_user', min_length=1, max_length=120)
    consent_status: str = Field(default='learning_use_only', pattern='^(learning_use_only|self_confirmed|authorized|unknown)$')
    visibility: str = Field(default='private', pattern='^(private|community)$')


class SpeakerCardSummary(BaseModel):
    id: str
    user_id: str
    source_document_id: str
    display_name: str
    role_title: str
    core_claims: list[str]
    speaking_style: list[str]
    thinking_style: list[str]
    rhetorical_patterns: list[str]
    useful_quotes: list[str]
    discussion_topics: list[str]
    limitations: list[str]
    consent_status: str
    visibility: str


class StudyRoundtableRequest(BaseModel):
    question: str = Field(min_length=2, max_length=4000)
    source_ids: list[str] = Field(default_factory=list, min_length=1, max_length=8)
    discussion_mode: str = Field(default='guide', pattern='^(guide|critique|apply|compare|debate)$')
    conversation_id: Optional[str] = None
    user_id: str = Field(default='default_user', min_length=1, max_length=120)
    preferred_people: list[str] = Field(default_factory=list, max_length=5)
    participant_refs: list[RoundtableParticipantRef] = Field(default_factory=list, max_length=6)
    max_participants: int = Field(default=3, ge=1, le=4)
    history: list[ConversationTurn] = Field(default_factory=list)


class StudyRoundtableResponse(BaseModel):
    conversation_id: str
    plan: RoundtablePlan
    turns: list[RoundtableTurnResponse]
    final_answer: str
    memory: RoundtableMemoryState
    sources: list[StudySourceSummary]
    source_citations: list[RetrievedChunk]
