# SOURCE: NOT IN PAPERS. Own storage for accounts and personal health records.
"""SQLite database at aakaash/artifacts/app.db (gitignored), created on startup.

Every table except user carries user_id with ON DELETE CASCADE, so deleting a user removes
every row that belongs to them. Age, BMI and medicine course status are computed, never stored."""
from __future__ import annotations

import threading
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterator

from fastapi import Depends
from sqlalchemy import (Date, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, event)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from .config import Settings, get_settings

DB_FILE = "app.db"


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


def _owned() -> Mapped[int]:
    return mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False)


_CHILD = dict(cascade="all, delete-orphan", passive_deletes=True)


class User(Base):
    __tablename__ = "user"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    sessions: Mapped[list["LoginSession"]] = relationship(**_CHILD)
    profile: Mapped["Profile | None"] = relationship(**_CHILD)
    allergies: Mapped[list["Allergy"]] = relationship(**_CHILD)
    conditions: Mapped[list["Condition"]] = relationship(**_CHILD)
    medicines: Mapped[list["MedicineRecord"]] = relationship(**_CHILD)


class LoginSession(Base):
    __tablename__ = "session"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = _owned()
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class Profile(Base):
    __tablename__ = "profile"
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(100))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    sex: Mapped[str | None] = mapped_column(String(10))
    height_cm: Mapped[float | None] = mapped_column(Float)
    weight_kg: Mapped[float | None] = mapped_column(Float)
    blood_group: Mapped[str | None] = mapped_column(String(3))
    notes: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class Allergy(Base):
    __tablename__ = "allergy"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = _owned()
    allergen: Mapped[str] = mapped_column(String(200), nullable=False)
    reaction: Mapped[str | None] = mapped_column(String(500))
    severity: Mapped[str] = mapped_column(String(10), nullable=False, default="unknown")
    notes: Mapped[str | None] = mapped_column(Text)


class Condition(Base):
    __tablename__ = "condition"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = _owned()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    onset_date: Mapped[date | None] = mapped_column(Date)
    resolved_date: Mapped[date | None] = mapped_column(Date)
    outcome: Mapped[str] = mapped_column(String(10), nullable=False, default="unknown")
    notes: Mapped[str | None] = mapped_column(Text)


class MedicineRecord(Base):
    __tablename__ = "medicine_record"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = _owned()
    catalogue_id: Mapped[str | None] = mapped_column(String(40))
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    ingredients: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON list
    reason: Mapped[str | None] = mapped_column(String(300))
    dose: Mapped[str | None] = mapped_column(String(100))
    frequency: Mapped[str | None] = mapped_column(String(100))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    outcome: Mapped[str | None] = mapped_column(String(10))
    source: Mapped[str] = mapped_column(String(10), nullable=False, default="typed")
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


OWNED_TABLES = (LoginSession, Profile, Allergy, Condition, MedicineRecord)

_lock = threading.Lock()
_makers: dict[str, sessionmaker[Session]] = {}


def _foreign_keys_on(dbapi_conn, _record) -> None:
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


def db_path(settings: Settings) -> Path:
    return settings.artifacts_dir / DB_FILE


def session_maker(settings: Settings) -> sessionmaker[Session]:
    """One engine per database file; tables are created the first time a file is opened."""
    path = db_path(settings)
    key = str(path.resolve())
    with _lock:
        maker = _makers.get(key)
        if maker is None:
            path.parent.mkdir(parents=True, exist_ok=True)
            engine: Engine = create_engine(f"sqlite:///{path.as_posix()}",
                                           connect_args={"check_same_thread": False})
            event.listen(engine, "connect", _foreign_keys_on)
            Base.metadata.create_all(engine)
            maker = _makers[key] = sessionmaker(engine, expire_on_commit=False)
        return maker


def dispose_all() -> None:
    """Close every engine (tests use this before removing their temporary folder)."""
    with _lock:
        for m in _makers.values():
            m.kw["bind"].dispose()
        _makers.clear()


def get_db(settings: Settings = Depends(get_settings)) -> Iterator[Session]:
    with session_maker(settings)() as db:
        yield db
