from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Review-staging tables (existing, unchanged)
# ---------------------------------------------------------------------------

class VerifiedImageBrainrot(Base):
    """
    Staging table for low-confidence image classifications.
    Fed into future multimodal retraining pipeline.
    """

    __tablename__ = "verified_image_brainrot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_url: Mapped[str] = mapped_column(String(2048), default="", nullable=False)
    media_type: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_meaning: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    human_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    correct_meaning: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class VerifiedTextBrainrot(Base):
    __tablename__ = "verified_text_brainrot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_text: Mapped[str] = mapped_column(String(2048), nullable=False)
    page_url: Mapped[str] = mapped_column(String(2048), default="", nullable=False)
    agent_equivalent_text: Mapped[str] = mapped_column(String(2048), default="", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    human_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    correct_meaning: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


# ---------------------------------------------------------------------------
# Cache tables (new – local cache-first policy)
# ---------------------------------------------------------------------------

class CachedTextTranslation(Base):
    """
    Stores verified text-highlight analysis results keyed by the normalised
    (trimmed, lowercased) slang phrase.  Prevents redundant OpenRouter calls.
    """

    __tablename__ = "cached_text_translations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lookup_key: Mapped[str] = mapped_column(String(2048), unique=True, nullable=False, index=True)
    is_brainrot: Mapped[bool] = mapped_column(Boolean, nullable=False)
    brainrot_text: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    equivalent_text: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    formal_explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sentiment_label: Mapped[str] = mapped_column(String(32), default="unclear", nullable=False)
    sentiment_rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    model_used: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class CachedImageAnalysis(Base):
    """
    Stores vision/screenshot analysis results keyed by a SHA-256 hash of the
    raw image_base64 payload.  Prevents redundant Gemini calls.
    """

    __tablename__ = "cached_image_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    image_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    is_brainrot: Mapped[bool] = mapped_column(Boolean, nullable=False)
    brainrot_meaning: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    equivalent_text: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    formal_explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    model_used: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    used_frame_fallback: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


# ---------------------------------------------------------------------------
# Engine / session factory
# ---------------------------------------------------------------------------

def build_database_url() -> Optional[str]:
    _ = get_settings()
    direct_url = (os.getenv("DATABASE_URL") or "").strip()
    if direct_url:
        return direct_url
    return None


@lru_cache(maxsize=1)
def get_session_factory() -> Optional[sessionmaker[Session]]:
    database_url = build_database_url()
    if not database_url:
        return None

    try:
        engine = create_engine(database_url, future=True, pool_pre_ping=True)
        Base.metadata.create_all(engine)
        return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Review-staging helpers (existing, unchanged)
# ---------------------------------------------------------------------------

def flag_image_for_review(
    *,
    source_url: Optional[str],
    media_type: str,
    agent_meaning: Optional[str],
    confidence: float,
) -> bool:
    session_factory = get_session_factory()
    if session_factory is None:
        return False

    record = VerifiedImageBrainrot(
        source_url=(source_url or "").strip(),
        media_type=media_type,
        agent_meaning=(agent_meaning or "").strip(),
        confidence=confidence,
    )

    try:
        with session_factory() as session:
            session.add(record)
            session.commit()
        return True
    except SQLAlchemyError:
        return False


def flag_text_for_review(
    *,
    source_text: str,
    page_url: Optional[str],
    agent_equivalent_text: Optional[str],
    confidence: float,
) -> bool:
    session_factory = get_session_factory()
    if session_factory is None:
        return False

    record = VerifiedTextBrainrot(
        source_text=source_text.strip(),
        page_url=(page_url or "").strip(),
        agent_equivalent_text=(agent_equivalent_text or "").strip(),
        confidence=confidence,
    )

    try:
        with session_factory() as session:
            session.add(record)
            session.commit()
        return True
    except SQLAlchemyError:
        return False


def check_database_connection() -> bool:
    session_factory = get_session_factory()
    if session_factory is None:
        return False
    try:
        with session_factory() as session:
            session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Local JSON dataset index (slang_terms.json)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def load_slang_terms_index() -> dict[str, dict[str, Any]]:
    """
    Build a case-folded lookup index from data/processed/slang_terms.json.
    Returns {normalised_term: {term, meaning, ...}} for O(1) exact-match checks.
    """
    settings = get_settings()
    ref_path: Path = settings.reference_dataset_path
    if not ref_path.exists():
        return {}

    try:
        payload = json.loads(ref_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    if not isinstance(payload, list):
        return {}

    index: dict[str, dict[str, Any]] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        term = str(item.get("term", "")).strip()
        meaning = str(item.get("meaning", "")).strip()
        if term and meaning:
            index[term.casefold()] = {
                "term": term,
                "meaning": meaning,
                "example": str(item.get("example", "")).strip(),
                "category": str(item.get("category", "")).strip(),
            }
    return index


# ---------------------------------------------------------------------------
# Cache lookup / save – TEXT highlights
# ---------------------------------------------------------------------------

def lookup_cached_text(lookup_key: str) -> Optional[dict[str, Any]]:
    """
    Look for an exact-match cached text translation.
    Returns a plain dict matching HighlightedTextAnalysisResponse fields, or None.
    """
    session_factory = get_session_factory()
    if session_factory is None:
        return None

    try:
        with session_factory() as session:
            row = (
                session.query(CachedTextTranslation)
                .filter(CachedTextTranslation.lookup_key == lookup_key)
                .first()
            )
            if row is None:
                return None
            return {
                "is_brainrot": row.is_brainrot,
                "brainrot_text": row.brainrot_text,
                "equivalent_text": row.equivalent_text,
                "formal_explanation": row.formal_explanation,
                "sentiment_label": row.sentiment_label,
                "sentiment_rationale": row.sentiment_rationale,
                "confidence_score": row.confidence_score,
                "flagged_for_review": False,
                "model_used": row.model_used,
            }
    except SQLAlchemyError:
        return None


def save_cached_text(lookup_key: str, data: dict[str, Any]) -> bool:
    """Persist a text translation result into the cache table."""
    session_factory = get_session_factory()
    if session_factory is None:
        return False

    record = CachedTextTranslation(
        lookup_key=lookup_key,
        is_brainrot=bool(data.get("is_brainrot", False)),
        brainrot_text=data.get("brainrot_text"),
        equivalent_text=data.get("equivalent_text"),
        formal_explanation=data.get("formal_explanation"),
        sentiment_label=data.get("sentiment_label", "unclear"),
        sentiment_rationale=data.get("sentiment_rationale"),
        confidence_score=float(data.get("confidence_score", 0.0)),
        model_used=data.get("model_used"),
    )

    try:
        with session_factory() as session:
            session.add(record)
            session.commit()
        return True
    except SQLAlchemyError:
        return False


# ---------------------------------------------------------------------------
# Cache lookup / save – IMAGE / screenshot
# ---------------------------------------------------------------------------

def lookup_cached_image(image_hash: str) -> Optional[dict[str, Any]]:
    """
    Look for a cached image analysis by its SHA-256 hash.
    Returns a plain dict matching ImageAnalysisResponse fields, or None.
    """
    session_factory = get_session_factory()
    if session_factory is None:
        return None

    try:
        with session_factory() as session:
            row = (
                session.query(CachedImageAnalysis)
                .filter(CachedImageAnalysis.image_hash == image_hash)
                .first()
            )
            if row is None:
                return None
            return {
                "is_brainrot": row.is_brainrot,
                "brainrot_meaning": row.brainrot_meaning,
                "equivalent_text": row.equivalent_text,
                "formal_explanation": row.formal_explanation,
                "confidence_score": row.confidence_score,
                "flagged_for_review": False,
                "model_used": row.model_used,
                "used_frame_fallback": row.used_frame_fallback,
            }
    except SQLAlchemyError:
        return None


def save_cached_image(image_hash: str, data: dict[str, Any]) -> bool:
    """Persist an image analysis result into the cache table."""
    session_factory = get_session_factory()
    if session_factory is None:
        return False

    record = CachedImageAnalysis(
        image_hash=image_hash,
        is_brainrot=bool(data.get("is_brainrot", False)),
        brainrot_meaning=data.get("brainrot_meaning"),
        equivalent_text=data.get("equivalent_text"),
        formal_explanation=data.get("formal_explanation"),
        confidence_score=float(data.get("confidence_score", 0.0)),
        model_used=data.get("model_used"),
        used_frame_fallback=bool(data.get("used_frame_fallback", False)),
    )

    try:
        with session_factory() as session:
            session.add(record)
            session.commit()
        return True
    except SQLAlchemyError:
        return False
