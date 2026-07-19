from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class Person(Base, TimestampMixin):
    __tablename__ = 'people'

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    english_name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    chinese_name: Mapped[str] = mapped_column(String(160), index=True)
    domain_category: Mapped[str] = mapped_column(String(160), index=True)
    ai_archetype: Mapped[str] = mapped_column(String(120), index=True)
    brief_intro: Mapped[str] = mapped_column(Text)
    portrait_asset: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_fictional: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    era_context: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_dataset_version: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default='active', nullable=False)

    persona_profiles: Mapped[list['PersonaProfile']] = relationship(back_populates='person', cascade='all, delete-orphan')
    knowledge_chunks: Mapped[list['KnowledgeChunk']] = relationship(back_populates='person', cascade='all, delete-orphan')
    quotes: Mapped[list['Quote']] = relationship(back_populates='person', cascade='all, delete-orphan')
    works_or_events: Mapped[list['WorkEvent']] = relationship(back_populates='person', cascade='all, delete-orphan')


class PersonaProfile(Base, TimestampMixin):
    __tablename__ = 'persona_profiles'
    __table_args__ = (UniqueConstraint('person_id', 'version', name='uq_persona_profile_version'),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    person_id: Mapped[str] = mapped_column(ForeignKey('people.id', ondelete='CASCADE'), index=True)
    slug: Mapped[str] = mapped_column(String(120), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    profile_status: Mapped[str] = mapped_column(String(40), default='draft', nullable=False)
    identity: Mapped[dict] = mapped_column(JSON, nullable=False)
    core_traits: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    thinking_style: Mapped[dict] = mapped_column(JSON, nullable=False)
    speaking_style: Mapped[dict] = mapped_column(JSON, nullable=False)
    values: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    blind_spots: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    taboos: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    preferred_topics: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    disallowed_claims: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    response_strategy: Mapped[dict] = mapped_column(JSON, nullable=False)
    prompt_contract: Mapped[dict] = mapped_column(JSON, nullable=False)
    generation_notes: Mapped[dict] = mapped_column(JSON, nullable=False)
    metadata_json: Mapped[dict] = mapped_column('metadata', JSON, nullable=False)

    person: Mapped[Person] = relationship(back_populates='persona_profiles')


class KnowledgeChunk(Base):
    __tablename__ = 'knowledge_chunks'

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    person_id: Mapped[str] = mapped_column(ForeignKey('people.id', ondelete='CASCADE'), index=True)
    chunk_type: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_name: Mapped[str] = mapped_column(String(120))
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    source_priority: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    theme_tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    era: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    importance_score: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    embedding: Mapped[Optional[list[float]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    person: Mapped[Person] = relationship(back_populates='knowledge_chunks')


class SourceDocument(Base, TimestampMixin):
    __tablename__ = 'source_documents'

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(120), default='default_user', nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    source_type: Mapped[str] = mapped_column(String(60), default='text', nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), default='compiled', nullable=False, index=True)
    original_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict] = mapped_column('metadata', JSON, default=dict, nullable=False)
    sections: Mapped[list['SourceSection']] = relationship(back_populates='document', cascade='all, delete-orphan')
    chunks: Mapped[list['SourceKnowledgeChunk']] = relationship(back_populates='document', cascade='all, delete-orphan')
    knowledge_pack: Mapped[Optional['KnowledgePack']] = relationship(back_populates='document', cascade='all, delete-orphan')
    video_asset: Mapped[Optional['VideoSourceAsset']] = relationship(back_populates='document', cascade='all, delete-orphan')
    speaker_cards: Mapped[list['SpeakerCard']] = relationship(back_populates='source_document', cascade='all, delete-orphan')


class SourceSection(Base):
    __tablename__ = 'source_sections'

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey('source_documents.id', ondelete='CASCADE'), index=True)
    title: Mapped[str] = mapped_column(String(255))
    section_type: Mapped[str] = mapped_column(String(60), default='section', nullable=False, index=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column('metadata', JSON, default=dict, nullable=False)
    document: Mapped[SourceDocument] = relationship(back_populates='sections')
    chunks: Mapped[list['SourceKnowledgeChunk']] = relationship(back_populates='section', cascade='all, delete-orphan')


class KnowledgePack(Base, TimestampMixin):
    __tablename__ = 'knowledge_packs'

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey('source_documents.id', ondelete='CASCADE'), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str] = mapped_column(Text, default='', nullable=False)
    core_frameworks: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    topic_index: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    glossary: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    patterns: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    cheatsheet: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    compiler_version: Mapped[str] = mapped_column(String(80), default='study-pack-v1', nullable=False)
    metadata_json: Mapped[dict] = mapped_column('metadata', JSON, default=dict, nullable=False)

    document: Mapped[SourceDocument] = relationship(back_populates='knowledge_pack')


class SourceKnowledgeChunk(Base):
    __tablename__ = 'source_knowledge_chunks'

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey('source_documents.id', ondelete='CASCADE'), index=True)
    section_id: Mapped[Optional[str]] = mapped_column(ForeignKey('source_sections.id', ondelete='SET NULL'), nullable=True, index=True)
    chunk_type: Mapped[str] = mapped_column(String(64), default='source_excerpt', nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_name: Mapped[str] = mapped_column(String(255))
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    source_priority: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    theme_tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    importance_score: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    embedding: Mapped[Optional[list[float]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    document: Mapped[SourceDocument] = relationship(back_populates='chunks')
    section: Mapped[Optional[SourceSection]] = relationship(back_populates='chunks')


class VideoSourceAsset(Base, TimestampMixin):
    __tablename__ = 'video_source_assets'

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey('source_documents.id', ondelete='CASCADE'), unique=True, index=True)
    storage_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    object_url: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    transcript: Mapped[str] = mapped_column(Text, default='', nullable=False)
    segments: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    summary: Mapped[str] = mapped_column(Text, default='', nullable=False)
    topics: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    viewpoints: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    useful_quotes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[dict] = mapped_column('metadata', JSON, default=dict, nullable=False)

    document: Mapped[SourceDocument] = relationship(back_populates='video_asset')


class SpeakerCard(Base, TimestampMixin):
    __tablename__ = 'speaker_cards'

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(120), default='default_user', nullable=False, index=True)
    source_document_id: Mapped[str] = mapped_column(ForeignKey('source_documents.id', ondelete='CASCADE'), index=True)
    display_name: Mapped[str] = mapped_column(String(160), index=True)
    role_title: Mapped[str] = mapped_column(String(255), default='学习型表达角色卡', nullable=False)
    core_claims: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    speaking_style: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    thinking_style: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    rhetorical_patterns: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    useful_quotes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    discussion_topics: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    limitations: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    consent_status: Mapped[str] = mapped_column(String(60), default='learning_use_only', nullable=False, index=True)
    visibility: Mapped[str] = mapped_column(String(30), default='private', nullable=False, index=True)
    metadata_json: Mapped[dict] = mapped_column('metadata', JSON, default=dict, nullable=False)

    source_document: Mapped[SourceDocument] = relationship(back_populates='speaker_cards')


class Quote(Base, TimestampMixin):
    __tablename__ = 'quotes'

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    person_id: Mapped[str] = mapped_column(ForeignKey('people.id', ondelete='CASCADE'), index=True)
    quote_text: Mapped[str] = mapped_column(Text)
    quote_translation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_name: Mapped[str] = mapped_column(String(160))
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    authenticity_level: Mapped[str] = mapped_column(String(40), default='unverified', nullable=False)
    theme_tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    person: Mapped[Person] = relationship(back_populates='quotes')


class WorkEvent(Base, TimestampMixin):
    __tablename__ = 'works_or_events'

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    person_id: Mapped[str] = mapped_column(ForeignKey('people.id', ondelete='CASCADE'), index=True)
    name: Mapped[str] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(80))
    period: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    summary: Mapped[str] = mapped_column(Text)
    significance: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    theme_tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    person: Mapped[Person] = relationship(back_populates='works_or_events')


class ConversationSession(Base, TimestampMixin):
    __tablename__ = 'sessions'

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mode: Mapped[str] = mapped_column(String(40), nullable=False)
    selected_people: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    topic_analysis: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    messages: Mapped[list['ChatMessage']] = relationship(back_populates='session', cascade='all, delete-orphan')
    roundtable_turns: Mapped[list['RoundtableTurn']] = relationship(back_populates='session', cascade='all, delete-orphan')
    summaries: Mapped[list['SessionSummary']] = relationship(back_populates='session', cascade='all, delete-orphan')


class ChatMessage(Base):
    __tablename__ = 'messages'

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey('sessions.id', ondelete='CASCADE'), index=True)
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    person_slug: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_chunks: Mapped[Optional[list[dict]]] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column('metadata', JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    session: Mapped[ConversationSession] = relationship(back_populates='messages')


class RoundtableTurn(Base):
    __tablename__ = 'roundtable_turns'

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey('sessions.id', ondelete='CASCADE'), index=True)
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker_slug: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    speaker_role: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    task: Mapped[str] = mapped_column(Text, default='', nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict] = mapped_column('metadata', JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    session: Mapped[ConversationSession] = relationship(back_populates='roundtable_turns')


class SessionSummary(Base, TimestampMixin):
    __tablename__ = 'session_summaries'

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey('sessions.id', ondelete='CASCADE'), index=True)
    summary: Mapped[str] = mapped_column(Text, default='', nullable=False)
    open_questions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    decisions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    memory_highlights: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_character_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    trigger_reason: Mapped[str] = mapped_column(String(80), default='threshold', nullable=False)

    session: Mapped[ConversationSession] = relationship(back_populates='summaries')


class UserMemory(Base, TimestampMixin):
    __tablename__ = 'user_memories'
    __table_args__ = (UniqueConstraint('user_id', 'memory_type', 'memory_key', name='uq_user_memory_key'),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(120), default='default_user', nullable=False, index=True)
    memory_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    memory_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    importance: Mapped[float] = mapped_column(Float, default=0.5, nullable=False, index=True)
    evidence_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default='active', nullable=False, index=True)
    last_accessed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    source_session_id: Mapped[Optional[str]] = mapped_column(ForeignKey('sessions.id', ondelete='SET NULL'), nullable=True)
    metadata_json: Mapped[dict] = mapped_column('metadata', JSON, default=dict, nullable=False)
