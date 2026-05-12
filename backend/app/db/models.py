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
