#!/usr/bin/env python3
"""
Lightweight Auth API for VICA.

Default DB: SQLite (local file in this folder)
Postgres-ready: set DATABASE_URL to a postgresql://... URL

Run:
  python -m uvicorn app:app --host 0.0.0.0 --port 8001 --reload
"""

from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Generator, Optional

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import Boolean, DateTime, Integer, String, create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, declarative_base, mapped_column, sessionmaker
from werkzeug.security import check_password_hash, generate_password_hash


logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [AUTH_API] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("auth_api")


def _redact_url(url: str) -> str:
    if "@" not in url or "://" not in url:
        return url
    prefix, rest = url.split("://", 1)
    if "@" not in rest:
        return url
    creds, host = rest.split("@", 1)
    if ":" in creds:
        user = creds.split(":", 1)[0]
        return f"{prefix}://{user}:***@{host}"
    return f"{prefix}://***@{host}"


def _db_url() -> str:
    env_url = os.getenv("DATABASE_URL", "").strip()
    if env_url:
        if env_url.startswith("postgres://"):
            env_url = "postgresql://" + env_url[len("postgres://") :]
        log.info("Using DATABASE_URL=%s", _redact_url(env_url))
        return env_url

    sqlite_path = Path(__file__).resolve().parent / "auth_local.db"
    fallback = f"sqlite:///{sqlite_path}"
    log.warning("DATABASE_URL not set, using SQLite at %s", sqlite_path)
    return fallback


DATABASE_URL = _db_url()
ENGINE_KWARGS = (
    {"connect_args": {"check_same_thread": False}}
    if DATABASE_URL.startswith("sqlite")
    else {"pool_pre_ping": True}
)
engine = create_engine(DATABASE_URL, **ENGINE_KWARGS)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
Base = declarative_base()


class User(Base):
    __tablename__ = "auth_users"

    id = mapped_column(Integer, primary_key=True, index=True)
    email = mapped_column(String(254), unique=True, nullable=False, index=True)
    password_hash = mapped_column(String(255), nullable=False)
    is_active = mapped_column(Boolean, default=True, nullable=False)
    created_at = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    last_login = mapped_column(DateTime(timezone=True), nullable=True)


class SessionToken(Base):
    __tablename__ = "auth_sessions"

    id = mapped_column(Integer, primary_key=True, index=True)
    token = mapped_column(String(128), unique=True, nullable=False, index=True)
    user_id = mapped_column(Integer, nullable=False, index=True)
    created_at = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = mapped_column(DateTime(timezone=True), nullable=False)
    is_revoked = mapped_column(Boolean, default=False, nullable=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenRequest(BaseModel):
    token: str = Field(min_length=20)


TOKEN_TTL_HOURS = int(os.getenv("AUTH_TOKEN_TTL_HOURS", "12"))

app = FastAPI(title="VICA Auth API", version="0.1.0")


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    log.info("Auth API started. DB backend=%s", engine.dialect.name)


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return {"ok": True, "service": "auth_api", "db": engine.dialect.name}


@app.post("/signup")
def signup(payload: SignupRequest, db: Session = Depends(get_db)) -> dict:
    email = payload.email.strip().lower()
    log.info("Signup attempt email=%s", email)

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists")

    user = User(email=email, password_hash=generate_password_hash(payload.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists")
    db.refresh(user)
    log.info("Signup success user_id=%s email=%s", user.id, user.email)
    return {"ok": True, "user_id": user.id, "email": user.email}


def _issue_token(db: Session, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_HOURS)
    db.add(SessionToken(token=token, user_id=user_id, expires_at=expires_at))
    db.commit()
    return token


@app.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> dict:
    email = payload.email.strip().lower()
    log.info("Login attempt email=%s", email)

    user: Optional[User] = db.query(User).filter(User.email == email).first()
    if not user or not user.is_active or not check_password_hash(user.password_hash, payload.password):
        log.warning("Login failed email=%s", email)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    user.last_login = datetime.now(timezone.utc)
    token = _issue_token(db, user.id)
    log.info("Login success user_id=%s email=%s", user.id, user.email)
    return {
        "ok": True,
        "token": token,
        "token_type": "session",
        "expires_in_seconds": TOKEN_TTL_HOURS * 3600,
        "user": {"id": user.id, "email": user.email},
    }


@app.post("/validate-token")
def validate_token(payload: TokenRequest, db: Session = Depends(get_db)) -> dict:
    now = datetime.now(timezone.utc)
    sess: Optional[SessionToken] = db.query(SessionToken).filter(SessionToken.token == payload.token).first()
    if not sess or sess.is_revoked:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    # SQLite often returns naive datetimes; normalize to UTC-aware before compare.
    expires_at = sess.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    user = db.query(User).filter(User.id == sess.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not active")

    return {
        "ok": True,
        "user": {"id": user.id, "email": user.email},
        "expires_at": expires_at.isoformat(),
    }

