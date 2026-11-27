"""Minimal account system: register / login / me / logout.

Passwords: PBKDF2-SHA256 (stdlib), 200k rounds, per-user salt.
Sessions: random bearer token stored server-side (table auth_tokens).
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db.session import Base, engine, get_db

router = APIRouter()
SESSION_LIFETIME_DAYS = 60
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(40))
    pw_hash: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuthToken(Base):
    __tablename__ = 'auth_tokens'
    token: Mapped[str] = mapped_column(String(80), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


Base.metadata.create_all(bind=engine, tables=[User.__table__, AuthToken.__table__])


def _hash(pw: str, salt: Optional[str] = None) -> str:
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', pw.encode(), salt.encode(), 200_000).hex()
    return f'pbkdf2${salt}${dk}'


def _verify(pw: str, stored: str) -> bool:
    try:
        _, salt, _dk = stored.split('$')
    except ValueError:
        return False
    return hmac.compare_digest(_hash(pw, salt), stored)


class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=6, max_length=128)


class LoginIn(BaseModel):
    email: str
    password: str


def _issue(db: Session, user: User) -> dict:
    tok = secrets.token_urlsafe(32)
    db.add(AuthToken(token=tok, user_id=user.id, expires_at=_now() + timedelta(days=SESSION_LIFETIME_DAYS)))
    db.commit()
    return {'token': tok, 'user': _pub(user)}


def _pub(u: User) -> dict:
    return {'id': u.id, 'name': u.name, 'email': u.email,
            'since': u.created_at.date().isoformat() if u.created_at else None}


def current_user(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.lower().startswith('bearer '):
        raise HTTPException(401, 'Not signed in')
    tok = db.get(AuthToken, authorization[7:].strip())
    if not tok:
        raise HTTPException(401, 'Session expired')
    exp = tok.expires_at if tok.expires_at.tzinfo else tok.expires_at.replace(tzinfo=timezone.utc)
    if exp < _now():
        db.delete(tok); db.commit()
        raise HTTPException(401, 'Session expired')
    user = db.get(User, tok.user_id)
    if not user:
        raise HTTPException(401, 'Account not found')
    return user


@router.post('/register')
def register(body: RegisterIn, db: Session = Depends(get_db)) -> dict:
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(422, 'That email doesn’t look right.')
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(409, 'An account with this email already exists. Sign in instead.')
    user = User(id=str(uuid.uuid4()), email=email, name=body.name.strip(), pw_hash=_hash(body.password), created_at=_now())
    db.add(user); db.commit()
    return _issue(db, user)


@router.post('/login')
def login(body: LoginIn, db: Session = Depends(get_db)) -> dict:
    user = db.query(User).filter(User.email == body.email.strip().lower()).first()
    if not user or not _verify(body.password, user.pw_hash):
        raise HTTPException(401, 'Email or password is incorrect.')
    return _issue(db, user)


@router.get('/me')
def me(user: User = Depends(current_user)) -> dict:
    return {'user': _pub(user)}


@router.post('/logout')
def logout(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)) -> dict:
    if authorization and authorization.lower().startswith('bearer '):
        tok = db.get(AuthToken, authorization[7:].strip())
        if tok:
            db.delete(tok); db.commit()
    return {'ok': True}
