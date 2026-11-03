# SOURCE: NOT IN PAPERS. Own login code: argon2 password hashes and a signed session cookie.
"""Passwords are hashed with argon2id and never stored or logged in plain text. The cookie holds a
random token plus its HMAC; the database keeps only the token's sha256, so logout and account
deletion really end a session. The login rate limit lives in this process only: it resets when the
server restarts and is not shared between processes."""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import threading
import time
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import LoginSession, User, get_db, utcnow

log = logging.getLogger("uvicorn.error")

COOKIE = "medsafe_session"
SESSION_DAYS = 14
MAX_FAILURES = 5
WINDOW_SECONDS = 15 * 60

_hasher = PasswordHasher()
_lock = threading.Lock()
_generated_secret: str | None = None
_failures: dict[tuple[str, str], list[float]] = {}


# ---- signing secret ---------------------------------------------------------------------------
def session_secret() -> bytes:
    """SESSION_SECRET from the environment. If it is unset a random key is made once per process and
    kept in memory only, so every restart signs everyone out. It is never written anywhere."""
    global _generated_secret
    configured = os.environ.get("SESSION_SECRET", "").strip()
    if configured:
        return configured.encode()
    with _lock:
        if _generated_secret is None:
            _generated_secret = secrets.token_urlsafe(32)
            log.warning("SESSION_SECRET is not set: using a random key, so sessions reset when the "
                        "server restarts. Set SESSION_SECRET in the environment to keep them.")
        return _generated_secret.encode()


# ---- passwords --------------------------------------------------------------------------------
def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored: str, password: str) -> bool:
    try:
        return _hasher.verify(stored, password)
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(stored: str) -> bool:
    return _hasher.check_needs_rehash(stored)


# ---- rate limit -------------------------------------------------------------------------------
def _key(email: str, request: Request) -> tuple[str, str]:
    return email, request.client.host if request.client else ""


def retry_after(email: str, request: Request) -> int:
    """Seconds to wait if this email and address have failed too often lately, else 0."""
    now = time.monotonic()
    with _lock:
        recent = [t for t in _failures.get(_key(email, request), []) if now - t < WINDOW_SECONDS]
        _failures[_key(email, request)] = recent
        if len(recent) < MAX_FAILURES:
            return 0
        return int(WINDOW_SECONDS - (now - recent[0])) + 1


def record_failure(email: str, request: Request) -> None:
    with _lock:
        _failures.setdefault(_key(email, request), []).append(time.monotonic())


def clear_failures(email: str, request: Request) -> None:
    with _lock:
        _failures.pop(_key(email, request), None)


def reset_rate_limit() -> None:
    with _lock:
        _failures.clear()


# ---- sessions ---------------------------------------------------------------------------------
def _sign(token: str) -> str:
    return hmac.new(session_secret(), token.encode(), hashlib.sha256).hexdigest()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _secure(request: Request) -> bool:
    """Secure cookie over https. Behind a proxy that ends TLS the app sees plain http, so
    MEDSAFE_COOKIE_SECURE=1 forces the flag."""
    return request.url.scheme == "https" or os.environ.get("MEDSAFE_COOKIE_SECURE", "").strip() in ("1", "true", "yes")


def start_session(db: Session, user: User, request: Request, response: Response) -> None:
    token = secrets.token_urlsafe(32)
    db.add(LoginSession(user_id=user.id, token_hash=_token_hash(token),
                        expires_at=utcnow() + timedelta(days=SESSION_DAYS)))
    db.commit()
    response.set_cookie(COOKIE, f"{token}.{_sign(token)}", max_age=SESSION_DAYS * 86400, httponly=True,
                        samesite="lax", secure=_secure(request), path="/")


def end_session(db: Session, request: Request, response: Response) -> None:
    token = _read_token(request)
    if token:
        row = db.scalar(select(LoginSession).where(LoginSession.token_hash == _token_hash(token)))
        if row:
            db.delete(row)
            db.commit()
    response.delete_cookie(COOKIE, path="/")


def _read_token(request: Request) -> str | None:
    raw = request.cookies.get(COOKIE, "")
    token, _, sig = raw.partition(".")
    if token and sig and hmac.compare_digest(sig, _sign(token)):
        return token
    return None


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """The signed-in user, or 401. Every personal endpoint filters by this user's id; no endpoint
    takes a user or profile id from the client."""
    denied = HTTPException(401, "Sign in to continue.")
    token = _read_token(request)
    if token is None:
        raise denied
    row = db.scalar(select(LoginSession).where(LoginSession.token_hash == _token_hash(token)))
    if row is None:
        raise denied
    if row.expires_at < utcnow():
        db.delete(row)
        db.commit()
        raise denied
    user = db.get(User, row.user_id)
    if user is None:
        raise denied
    return user
