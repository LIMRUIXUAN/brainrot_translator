from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, Text, UniqueConstraint, create_engine, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .config import get_settings


logger = logging.getLogger(__name__)


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


class BrainrotWordFrequency(Base):
    """Dashboard counter for slang terms found in highlighted text requests."""

    __tablename__ = "brainrot_word_frequency"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    normalized_term: Mapped[str] = mapped_column(String(256), unique=True, nullable=False, index=True)
    display_label: Mapped[str] = mapped_column(String(256), nullable=False)
    count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    last_page_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)


class MonthlySlangFrequency(Base):
    """Anonymous shared slang counts bucketed by calendar month."""

    __tablename__ = "monthly_slang_frequency"
    __table_args__ = (
        UniqueConstraint("normalized_term", "month_start", name="uq_monthly_slang_frequency_term_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    normalized_term: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    display_label: Mapped[str] = mapped_column(String(256), nullable=False)
    month_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class SlangModeration(Base):
    """Admin moderation state for public leaderboard terms."""

    __tablename__ = "slang_moderation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    normalized_term: Mapped[str] = mapped_column(String(256), unique=True, nullable=False, index=True)
    display_label: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="visible", nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    unsafe_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_by: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)


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
        logger.exception("get_session_factory failed for database_url=%s", database_url)
        return None


def _is_cache_expired(created_at: Optional[datetime]) -> bool:
    if created_at is None:
        return True

    settings = get_settings()
    cached_at = created_at
    if cached_at.tzinfo is None:
        cached_at = cached_at.replace(tzinfo=timezone.utc)
    return cached_at + timedelta(hours=settings.cache_ttl_hours) < datetime.now(timezone.utc)


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
        logger.exception(
            "flag_image_for_review failed for source_url=%s media_type=%s confidence=%s",
            source_url,
            media_type,
            confidence,
        )
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
        logger.exception(
            "flag_text_for_review failed for source_text=%s page_url=%s confidence=%s",
            source_text[:120],
            page_url,
            confidence,
        )
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
            if _is_cache_expired(row.created_at):
                session.delete(row)
                session.commit()
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
        logger.exception("lookup_cached_text failed for lookup_key=%s", lookup_key)
        return None


def save_cached_text(lookup_key: str, data: dict[str, Any]) -> bool:
    """Persist or refresh a text translation result in the cache table."""
    session_factory = get_session_factory()
    if session_factory is None:
        return False

    try:
        with session_factory() as session:
            row = (
                session.query(CachedTextTranslation)
                .filter(CachedTextTranslation.lookup_key == lookup_key)
                .first()
            )
            if row is None:
                row = CachedTextTranslation(lookup_key=lookup_key)
                session.add(row)

            row.is_brainrot = bool(data.get("is_brainrot", False))
            row.brainrot_text = data.get("brainrot_text")
            row.equivalent_text = data.get("equivalent_text")
            row.formal_explanation = data.get("formal_explanation")
            row.sentiment_label = data.get("sentiment_label", "unclear")
            row.sentiment_rationale = data.get("sentiment_rationale")
            row.confidence_score = float(data.get("confidence_score", 0.0))
            row.model_used = data.get("model_used")
            session.commit()
        return True
    except SQLAlchemyError:
        logger.exception("save_cached_text failed for lookup_key=%s", lookup_key)
        return False


# ---------------------------------------------------------------------------
# Shared monthly slang-frequency helpers
# ---------------------------------------------------------------------------

MODERATION_VISIBLE_STATUSES = {"visible", "hidden", "banned"}


def normalize_slang_term(term: str) -> str:
    return " ".join(term.strip().casefold().split())[:256]


def month_start_for(value: Optional[datetime] = None) -> date:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return date(current.year, current.month, 1)


def _is_unsafe_term(normalized_term: str, unsafe_keywords: tuple[str, ...]) -> bool:
    lowered = normalized_term.casefold()
    return any(keyword.strip().casefold() and keyword.strip().casefold() in lowered for keyword in unsafe_keywords)


def _get_or_create_moderation(
    session: Session,
    *,
    normalized_term: str,
    display_label: str,
    unsafe_flag: bool,
    updated_by: Optional[str] = None,
) -> SlangModeration:
    row = (
        session.query(SlangModeration)
        .filter(SlangModeration.normalized_term == normalized_term)
        .first()
    )
    now = datetime.now(timezone.utc)
    if row is None:
        row = SlangModeration(
            normalized_term=normalized_term,
            display_label=display_label,
            status="hidden" if unsafe_flag else "visible",
            reason="Auto-hidden by unsafe keyword filter." if unsafe_flag else None,
            unsafe_flag=unsafe_flag,
            updated_at=now,
            updated_by=updated_by,
        )
        session.add(row)
        return row

    row.display_label = display_label or row.display_label
    if unsafe_flag and not row.unsafe_flag:
        row.unsafe_flag = True
        row.status = "hidden"
        row.reason = row.reason or "Auto-hidden by unsafe keyword filter."
        row.updated_at = now
        row.updated_by = updated_by
    return row


def increment_word_frequencies(
    terms: dict[str, str],
    *,
    page_url: Optional[str] = None,
) -> bool:
    """Legacy wrapper: increment anonymous current-month counters."""
    del page_url
    return record_slang_detections(
        [{"term": label, "count": 1} for label in terms.values()],
        unsafe_keywords=get_settings().unsafe_slang_keywords,
    )


def record_slang_detections(
    items: list[dict[str, Any]],
    *,
    unsafe_keywords: tuple[str, ...],
    seen_at: Optional[datetime] = None,
) -> bool:
    """Store opt-in anonymous slang counts in the current calendar month bucket."""
    if not items:
        return True

    session_factory = get_session_factory()
    if session_factory is None:
        return False

    now = seen_at or datetime.now(timezone.utc)
    bucket = month_start_for(now)
    aggregate: dict[str, dict[str, Any]] = {}
    for item in items:
        label = " ".join(str(item.get("term", "")).strip().split())[:256]
        normalized = normalize_slang_term(label)
        if not normalized or not label:
            continue
        try:
            count = max(1, min(int(item.get("count", 1)), 100))
        except (TypeError, ValueError):
            count = 1
        if normalized not in aggregate:
            aggregate[normalized] = {"term": label, "count": 0}
        aggregate[normalized]["count"] += count

    if not aggregate:
        return True

    try:
        with session_factory() as session:
            for normalized, data in aggregate.items():
                label = str(data["term"])
                unsafe_flag = _is_unsafe_term(normalized, unsafe_keywords)
                _get_or_create_moderation(
                    session,
                    normalized_term=normalized,
                    display_label=label,
                    unsafe_flag=unsafe_flag,
                )
                row = (
                    session.query(MonthlySlangFrequency)
                    .filter(
                        MonthlySlangFrequency.normalized_term == normalized,
                        MonthlySlangFrequency.month_start == bucket,
                    )
                    .first()
                )
                if row is None:
                    row = MonthlySlangFrequency(
                        normalized_term=normalized,
                        display_label=label,
                        month_start=bucket,
                        count=0,
                    )
                    session.add(row)
                row.display_label = label
                row.count += int(data["count"])
                row.last_seen_at = now
            session.commit()
        return True
    except SQLAlchemyError:
        logger.exception("record_slang_detections failed for items=%s", items[:20])
        return False


def _visible_filter_query(session: Session):
    del session
    return select(SlangModeration.normalized_term).where(SlangModeration.status.in_(("hidden", "banned")))


def list_word_frequencies(limit: int = 20) -> list[dict[str, Any]]:
    """Return current-month public counters sorted by frequency."""
    return list_top_slang(period="month", limit=limit)["items"]


def list_top_slang(
    *,
    period: str = "month",
    limit: int = 20,
    year: Optional[int] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    session_factory = get_session_factory()
    current = now or datetime.now(timezone.utc)
    target_year = int(year or current.year)
    safe_limit = max(1, min(int(limit), 100))
    if session_factory is None:
        return {
            "period": "year" if period == "year" else "month",
            "year": target_year,
            "month": None if period == "year" else current.month,
            "items": [],
        }

    try:
        with session_factory() as session:
            hidden_terms = _visible_filter_query(session)
            if period == "year":
                start = date(target_year, 1, 1)
                end = date(target_year + 1, 1, 1)
                rows = (
                    session.query(
                        MonthlySlangFrequency.display_label,
                        func.sum(MonthlySlangFrequency.count).label("count"),
                        func.max(MonthlySlangFrequency.last_seen_at).label("last_seen_at"),
                    )
                    .filter(
                        MonthlySlangFrequency.month_start >= start,
                        MonthlySlangFrequency.month_start < end,
                        ~MonthlySlangFrequency.normalized_term.in_(hidden_terms),
                    )
                    .group_by(MonthlySlangFrequency.normalized_term, MonthlySlangFrequency.display_label)
                    .order_by(text("count DESC"), text("last_seen_at DESC"), MonthlySlangFrequency.display_label.asc())
                    .limit(safe_limit)
                    .all()
                )
                return {
                    "period": "year",
                    "year": target_year,
                    "month": None,
                    "items": [
                        {
                            "term": row.display_label,
                            "count": int(row.count or 0),
                            "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
                        }
                        for row in rows
                    ],
                }

            bucket = month_start_for(current)
            rows = (
                session.query(MonthlySlangFrequency)
                .filter(
                    MonthlySlangFrequency.month_start == bucket,
                    ~MonthlySlangFrequency.normalized_term.in_(hidden_terms),
                )
                .order_by(
                    MonthlySlangFrequency.count.desc(),
                    MonthlySlangFrequency.last_seen_at.desc(),
                    MonthlySlangFrequency.display_label.asc(),
                )
                .limit(safe_limit)
                .all()
            )
            return {
                "period": "month",
                "year": bucket.year,
                "month": bucket.month,
                "items": [
                    {
                        "term": row.display_label,
                        "count": row.count,
                        "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
                    }
                    for row in rows
                ],
            }
    except SQLAlchemyError:
        logger.exception("list_top_slang failed for period=%s year=%s limit=%s", period, year, limit)
        return {
            "period": "year" if period == "year" else "month",
            "year": target_year,
            "month": None if period == "year" else current.month,
            "items": [],
        }


def list_admin_slang(limit: int = 100) -> list[dict[str, Any]]:
    session_factory = get_session_factory()
    if session_factory is None:
        return []

    safe_limit = max(1, min(int(limit), 500))
    try:
        with session_factory() as session:
            totals = (
                session.query(
                    MonthlySlangFrequency.normalized_term.label("normalized_term"),
                    func.sum(MonthlySlangFrequency.count).label("count"),
                    func.max(MonthlySlangFrequency.last_seen_at).label("last_seen_at"),
                )
                .group_by(MonthlySlangFrequency.normalized_term)
                .subquery()
            )
            rows = (
                session.query(SlangModeration, totals.c.count, totals.c.last_seen_at)
                .outerjoin(totals, SlangModeration.normalized_term == totals.c.normalized_term)
                .order_by(
                    SlangModeration.status.desc(),
                    text("count DESC"),
                    SlangModeration.display_label.asc(),
                )
                .limit(safe_limit)
                .all()
            )
            return [
                {
                    "term": moderation.display_label,
                    "count": int(count or 0),
                    "status": moderation.status,
                    "reason": moderation.reason,
                    "unsafe_flag": moderation.unsafe_flag,
                    "last_seen_at": last_seen_at.isoformat() if last_seen_at else None,
                    "updated_at": moderation.updated_at.isoformat() if moderation.updated_at else None,
                    "updated_by": moderation.updated_by,
                }
                for moderation, count, last_seen_at in rows
            ]
    except SQLAlchemyError:
        logger.exception("list_admin_slang failed")
        return []


def update_slang_moderation(
    normalized_term: str,
    *,
    status: str,
    reason: Optional[str],
    updated_by: str,
) -> Optional[dict[str, Any]]:
    if status not in MODERATION_VISIBLE_STATUSES:
        return None

    normalized = normalize_slang_term(normalized_term)
    if not normalized:
        return None

    session_factory = get_session_factory()
    if session_factory is None:
        return None

    try:
        with session_factory() as session:
            row = (
                session.query(SlangModeration)
                .filter(SlangModeration.normalized_term == normalized)
                .first()
            )
            if row is None:
                display_label = normalized_term.strip() or normalized
                row = SlangModeration(
                    normalized_term=normalized,
                    display_label=display_label,
                    unsafe_flag=False,
                )
                session.add(row)
            row.status = status
            row.reason = reason
            row.updated_at = datetime.now(timezone.utc)
            row.updated_by = updated_by
            session.commit()
            return {
                "term": row.display_label,
                "count": 0,
                "status": row.status,
                "reason": row.reason,
                "unsafe_flag": row.unsafe_flag,
                "last_seen_at": None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                "updated_by": row.updated_by,
            }
    except SQLAlchemyError:
        logger.exception("update_slang_moderation failed for term=%s", normalized_term)
        return None


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
            if _is_cache_expired(row.created_at):
                session.delete(row)
                session.commit()
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
        logger.exception("lookup_cached_image failed for image_hash=%s", image_hash)
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
        logger.exception("save_cached_image failed for image_hash=%s", image_hash)
        return False


def get_dashboard_stats() -> dict[str, Any]:
    """Return aggregate dashboard statistics for public current-month slang."""
    session_factory = get_session_factory()
    defaults: dict[str, Any] = {
        "total_text_analyses": 0,
        "total_image_analyses": 0,
        "unique_terms": 0,
        "top_term": None,
        "top_term_count": 0,
    }
    if session_factory is None:
        return defaults

    try:
        with session_factory() as session:
            total_text = session.query(CachedTextTranslation).count()
            total_image = session.query(CachedImageAnalysis).count()
            bucket = month_start_for()
            hidden_terms = _visible_filter_query(session)
            visible_rows = (
                session.query(MonthlySlangFrequency)
                .filter(
                    MonthlySlangFrequency.month_start == bucket,
                    ~MonthlySlangFrequency.normalized_term.in_(hidden_terms),
                )
            )
            unique_terms = visible_rows.count()
            top_row = visible_rows.order_by(MonthlySlangFrequency.count.desc()).first()
            return {
                "total_text_analyses": total_text,
                "total_image_analyses": total_image,
                "unique_terms": unique_terms,
                "top_term": top_row.display_label if top_row else None,
                "top_term_count": top_row.count if top_row else 0,
            }
    except SQLAlchemyError:
        logger.exception("get_dashboard_stats failed")
        return defaults
