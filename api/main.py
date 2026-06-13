from __future__ import annotations

import base64
import binascii
import hashlib
import logging
import os
import re
from functools import lru_cache

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .agent import BrainrotAgent, OpenRouterAuthError
from .config import get_settings
from .database import (
    check_database_connection,
    get_dashboard_stats,
    list_admin_slang,
    list_word_frequencies,
    list_top_slang,
    load_slang_terms_index,
    lookup_cached_image,
    lookup_cached_text,
    normalize_slang_term,
    record_slang_detections,
    save_cached_image,
    update_slang_moderation,
)
from .local_translator import MockLocalTranslator
from .schemas import (
    AdminSlangListResponse,
    AdminSlangModerationUpdate,
    AdminSlangItem,
    DashboardStatsResponse,
    DashboardWordFrequencyResponse,
    HighlightedTextAnalysisRequest,
    HighlightedTextAnalysisResponse,
    ImageAnalysisRequest,
    ImageAnalysisResponse,
    PublicTopSlangResponse,
    ReverseTranslateRequest,
    ReverseTranslateResponse,
    ScreenshotMediaRequest,
    SlangDetectionsTelemetryRequest,
    SlangDetectionsTelemetryResponse,
    TranslateResponse,
)

logger = logging.getLogger(__name__)

settings = get_settings()
agent = BrainrotAgent(settings=settings)
local_translator = MockLocalTranslator(settings.reference_dataset_path)
limiter = Limiter(key_func=get_remote_address)

SENSITIVE_HEADER_NAMES = {
    "authorization",
    "x-openrouter-api-key",
}


def redact_sensitive_value(value: object) -> object:
    if value is None:
        return None
    text = str(value)
    if len(text) <= 8:
        return "[REDACTED]"
    return f"{text[:4]}...[REDACTED]...{text[-4:]}"


class SensitiveValueRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, dict):
            record.args = {
                key: redact_sensitive_value(value)
                if str(key).casefold() in SENSITIVE_HEADER_NAMES
                else value
                for key, value in record.args.items()
            }
        elif isinstance(record.args, tuple):
            record.args = tuple(
                redact_sensitive_value(value)
                if isinstance(value, str) and ("sk-or-" in value or "Bearer " in value)
                else value
                for value in record.args
            )
        return True


logging.getLogger().addFilter(SensitiveValueRedactionFilter())

SLANG_TEXT_MARKERS = (
    "aura",
    "ate",
    "based",
    "bet",
    "bffr",
    "brainrot",
    "bro",
    "cap",
    "canon event",
    "caught in 4k",
    "caught slipping",
    "chronically online",
    "cooked",
    "cooked in the replies",
    "cringe",
    "delulu",
    "drip",
    "fanum tax",
    "fell off",
    "glazing",
    "goated",
    "gyatt",
    "highkey",
    "ick",
    "it's giving",
    "left no crumbs",
    "let him cook",
    "living rent free",
    "lore",
    "lowkey",
    "main character energy",
    "mid",
    "no cap",
    "npc",
    "periodt",
    "pressed",
    "ratio",
    "rizz",
    "say less",
    "sigma",
    "simp",
    "skibidi",
    "skill issue",
    "slay",
    "stan",
    "sus",
    "tea",
    "touch grass",
    "vibe check",
    "vibing",
    "w take",
    "yapping",
)

SLANG_OUTPUT_REPLACEMENTS = (
    (r"\bnegative aura points\b", "a loss of social reputation points"),
    (r"\baura points\b", "social reputation points"),
    (r"\bnegative aura\b", "poor social reputation"),
    (r"\bzero aura\b", "no social presence"),
    (r"\bno aura\b", "no social presence"),
    (r"(?<![a-z0-9])-?(\d+)\s+aura\b", r"\1 social reputation points"),
    (r"\bgetting caught slipping\b", "being caught making a mistake"),
    (r"\bcaught slipping\b", "caught making a mistake"),
    (r"\bhot corporate stock\b", "rapidly falling company stock"),
)


@lru_cache(maxsize=1)
def get_model_components():
    if not settings.model_dir.exists():
        return None

    os.environ.setdefault("USE_TF", "0")
    os.environ.setdefault("TRANSFORMERS_NO_TF", "1")

    try:
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
    except Exception:
        return None

    try:
        tokenizer = AutoTokenizer.from_pretrained(settings.model_dir)
        model = AutoModelForSeq2SeqLM.from_pretrained(settings.model_dir)
        model.eval()
        return tokenizer, model
    except Exception:
        return None


@lru_cache(maxsize=1)
def get_quality_classifier_components():
    if not settings.quality_classifier_dir.exists():
        return None

    os.environ.setdefault("USE_TF", "0")
    os.environ.setdefault("TRANSFORMERS_NO_TF", "1")

    try:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
    except Exception:
        return None

    try:
        tokenizer = AutoTokenizer.from_pretrained(settings.quality_classifier_dir)
        model = AutoModelForSequenceClassification.from_pretrained(settings.quality_classifier_dir)
        model.eval()
        return tokenizer, model
    except Exception:
        logger.exception("Failed to load local quality classifier from %s", settings.quality_classifier_dir)
        return None


def _generate_local_model_output(prompt: str) -> str | None:
    components = get_model_components()
    if components is None:
        return None

    tokenizer, model = components
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=128)
    outputs = model.generate(
        **inputs,
        max_new_tokens=128,
        num_beams=4,
        do_sample=False,
    )
    return tokenizer.decode(outputs[0], skip_special_tokens=True).strip()


def _generate_local_translation(text: str) -> str | None:
    return _generate_local_model_output(f"Convert brainrot English to normal English: {text.strip()}")


def _generate_local_reverse_translation(text: str) -> str | None:
    return _generate_local_model_output(f"Convert normal English to brainrot English: {text.strip()}")


def _heuristic_translation_confidence(source_text: str, candidate_text: str, *, changed: bool) -> float:
    source = source_text.strip().casefold()
    candidate = candidate_text.strip().casefold()
    if not candidate:
        return 0.2
    if not changed or source == candidate:
        return 0.55
    if _looks_like_brainrot_text(candidate_text):
        return 0.62
    return 0.78


def _normalise_for_equivalence(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def _cap_quality_score_for_obvious_failures(
    source_text: str,
    candidate_text: str,
    score: float,
    *,
    changed: bool,
) -> float:
    if not candidate_text.strip():
        return min(score, 0.2)
    if not changed:
        return min(score, 0.2)
    if _normalise_for_equivalence(source_text) == _normalise_for_equivalence(candidate_text):
        return min(score, 0.2)
    if _looks_like_brainrot_text(candidate_text):
        return min(score, 0.45)
    return score


def _score_translation_quality(
    source_text: str,
    candidate_text: str,
    *,
    changed: bool,
) -> tuple[float, bool]:
    components = get_quality_classifier_components()
    if components is None:
        score = _heuristic_translation_confidence(source_text, candidate_text, changed=changed)
        return _cap_quality_score_for_obvious_failures(
            source_text,
            candidate_text,
            score,
            changed=changed,
        ), False

    try:
        import torch
    except Exception:
        score = _heuristic_translation_confidence(source_text, candidate_text, changed=changed)
        return _cap_quality_score_for_obvious_failures(
            source_text,
            candidate_text,
            score,
            changed=changed,
        ), False

    tokenizer, model = components
    text_pair = (
        f"Source brainrot text: {source_text.strip()}\n"
        f"Candidate normal English translation: {candidate_text.strip()}"
    )
    inputs = tokenizer(
        text_pair,
        return_tensors="pt",
        truncation=True,
        max_length=256,
    )

    try:
        device = next(model.parameters()).device
        inputs = {key: value.to(device) for key, value in inputs.items()}
        with torch.no_grad():
            logits = model(**inputs).logits
        probabilities = torch.softmax(logits, dim=-1)[0]
        if probabilities.numel() < 2:
            score = _heuristic_translation_confidence(source_text, candidate_text, changed=changed)
            return _cap_quality_score_for_obvious_failures(
                source_text,
                candidate_text,
                score,
                changed=changed,
            ), False
        score = float(probabilities[1].detach().cpu().item())
        score = max(0.0, min(1.0, score))
        return _cap_quality_score_for_obvious_failures(
            source_text,
            candidate_text,
            score,
            changed=changed,
        ), True
    except Exception:
        logger.exception("Local quality classifier scoring failed")
        score = _heuristic_translation_confidence(source_text, candidate_text, changed=changed)
        return _cap_quality_score_for_obvious_failures(
            source_text,
            candidate_text,
            score,
            changed=changed,
        ), False


def translate_text(text: str) -> TranslateResponse:
    normal = _generate_local_translation(text)
    if normal is None:
        fallback = local_translator.translate(text)
        return TranslateResponse(
            normal=fallback.normal,
            used_mock=fallback.used_mock,
            model_source=fallback.model_source,
        )

    return TranslateResponse(
        normal=normal,
        used_mock=False,
        model_source="local_transformer",
    )


async def reverse_translate_text(
    text: str,
    text_model_speed: str | None = None,
    text_model_tier: str | None = None,
    openrouter_api_key: str | None = None,
) -> ReverseTranslateResponse:
    cleaned = text.strip()
    return await agent.reverse_translate(
        cleaned,
        text_model_speed=text_model_speed,
        text_model_tier=text_model_tier,
        openrouter_api_key=openrouter_api_key,
    )


def _looks_like_brainrot_text(text: str) -> bool:
    lowered = text.casefold()
    # Check static markers first (fast)
    for marker in SLANG_TEXT_MARKERS:
        pattern = rf"(?<![a-z0-9]){re.escape(marker.casefold())}(?![a-z0-9])"
        if re.search(pattern, lowered):
            return True

    # Check dynamic slang terms index keys
    for marker in load_slang_terms_index().keys():
        pattern = rf"(?<![a-z0-9]){re.escape(marker)}(?![a-z0-9])"
        if re.search(pattern, lowered):
            return True
    return False


def _normalise_frequency_term(term: str) -> str:
    return re.sub(r"\s+", " ", term.strip().casefold())


def _extract_brainrot_frequency_terms(text: str) -> dict[str, str]:
    """Find dashboard terms using built-in markers plus exact slang_terms.json entries."""
    lowered = text.casefold()
    candidates: dict[str, str] = {}
    for marker in SLANG_TEXT_MARKERS:
        normalized = _normalise_frequency_term(marker)
        candidates[normalized] = marker

    for normalized, entry in load_slang_terms_index().items():
        label = str(entry.get("term", "")).strip()
        if label:
            candidates[_normalise_frequency_term(normalized)] = label

    matches: dict[str, str] = {}
    for normalized, label in candidates.items():
        if not normalized:
            continue
        pattern = rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])"
        if re.search(pattern, lowered):
            matches[normalized] = label
    return matches


def get_user_openrouter_api_key(request: Request) -> str | None:
    value = request.headers.get("X-OpenRouter-API-Key", "")
    cleaned = value.strip()
    return cleaned or None


def require_user_openrouter_api_key(request: Request) -> str:
    api_key = get_user_openrouter_api_key(request)
    if api_key is None:
        raise HTTPException(
            status_code=401,
            detail="OpenRouter API key is required in extension settings.",
        )
    return api_key


async def require_google_admin(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "").strip()
    if not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Google admin login is required.")

    if not settings.google_admin_client_id or not settings.admin_google_emails:
        raise HTTPException(status_code=403, detail="Admin Google login is not configured.")

    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Google admin login is required.")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": token},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=401, detail="Unable to verify Google login.") from exc

    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Google admin login is invalid.")

    payload = response.json()
    email = str(payload.get("email", "")).strip().casefold()
    aud = str(payload.get("aud", "")).strip()
    email_verified = str(payload.get("email_verified", "")).strip().casefold() in {"true", "1"}
    allowed_emails = {item.strip().casefold() for item in settings.admin_google_emails if item.strip()}
    if aud != settings.google_admin_client_id or not email_verified or email not in allowed_emails:
        raise HTTPException(status_code=403, detail="Google account is not allowed for admin moderation.")
    return email


def _safe_non_brainrot_text_analysis(selected_text: str) -> HighlightedTextAnalysisResponse:
    cleaned = selected_text.strip()
    return HighlightedTextAnalysisResponse(
        is_brainrot=False,
        brainrot_text=None,
        equivalent_text=cleaned,
        formal_explanation="No brainrot or internet slang marker was detected, so the text was left unchanged.",
        sentiment_label="unclear",
        sentiment_rationale="Sentiment was not analyzed because the text was not routed to the local slang model.",
        confidence_score=0.9,
        flagged_for_review=False,
        model_used="local_slang_filter",
    )


def _apply_slang_output_cleanup(text: str) -> str:
    cleaned = text
    for pattern, replacement in SLANG_OUTPUT_REPLACEMENTS:
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
    return cleaned


def _try_local_model_text_analysis(selected_text: str) -> HighlightedTextAnalysisResponse | None:
    if not _looks_like_brainrot_text(selected_text):
        return _safe_non_brainrot_text_analysis(selected_text)

    normal = _generate_local_translation(selected_text)
    if normal is None:
        return None

    cleaned = selected_text.strip()
    equivalent = _apply_slang_output_cleanup(normal or cleaned)
    changed = equivalent.casefold() != cleaned.casefold()
    confidence, used_quality_classifier = _score_translation_quality(
        cleaned,
        equivalent,
        changed=changed,
    )
    return HighlightedTextAnalysisResponse(
        is_brainrot=changed,
        brainrot_text=cleaned if changed else None,
        equivalent_text=equivalent,
        formal_explanation="Analyzed locally with the fine-tuned FLAN-T5 text model.",
        sentiment_label="unclear",
        sentiment_rationale="The local text model does not produce sentiment labels.",
        confidence_score=confidence,
        flagged_for_review=confidence < settings.low_confidence_threshold,
        model_used="local_transformer+quality_classifier" if used_quality_classifier else "local_transformer",
    )


def decode_base64_payload(value: str, *, field_name: str) -> bytes:
    payload = value.strip()
    if payload.startswith("data:"):
        _, _, payload = payload.partition(",")

    try:
        return base64.b64decode(payload, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"{field_name} must be valid base64-encoded image bytes.",
        ) from exc


# ---------------------------------------------------------------------------
# Cache-first helpers
# ---------------------------------------------------------------------------

def _normalise_text_key(raw: str) -> str:
    """Trim whitespace, lowercase, strip punctuation, and condense spaces."""
    cleaned = raw.strip().casefold()
    cleaned = re.sub(r"[^\w\s]", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _text_model_cache_key(lookup_key: str, text_model_tier: str) -> str:
    tier = text_model_tier if text_model_tier in {"free", "premium"} else "free"
    return f"{lookup_key}::text_model_tier={tier}"


def _hash_image_payload(image_base64: str) -> str:
    """SHA-256 hex digest of the raw base64 string (after strip)."""
    return hashlib.sha256(image_base64.strip().encode("utf-8")).hexdigest()


def _try_slang_json_lookup(lookup_key: str) -> HighlightedTextAnalysisResponse | None:
    """
    Check the local slang_terms.json dataset for an exact match.
    Returns a pre-built response on hit, None on miss.
    """
    index = load_slang_terms_index()
    entry = index.get(lookup_key)
    if entry is None:
        return None

    return HighlightedTextAnalysisResponse(
        is_brainrot=True,
        brainrot_text=entry["term"],
        equivalent_text=entry["meaning"],
        formal_explanation=f"Matched from local slang_terms.json dataset ({entry.get('category', 'internet slang')}).",
        sentiment_label="neutral",
        sentiment_rationale="Determined from local reference data without AI inference.",
        confidence_score=0.95,
        flagged_for_review=False,
        model_used="local_cache_slang_json",
    )


def _try_db_text_lookup(lookup_key: str) -> HighlightedTextAnalysisResponse | None:
    """
    Check the PostgreSQL cached_text_translations table for an exact match.
    Returns a pre-built response on hit, None on miss.
    """
    cached = lookup_cached_text(lookup_key)
    if cached is None:
        return None

    cached["model_used"] = f"cached:{cached.get('model_used', 'unknown')}"
    return HighlightedTextAnalysisResponse.model_validate(cached)


def _is_low_confidence_result(result: HighlightedTextAnalysisResponse) -> bool:
    return result.confidence_score < settings.low_confidence_threshold


def _stage_low_confidence_text(
    request: HighlightedTextAnalysisRequest,
    result: HighlightedTextAnalysisResponse,
) -> HighlightedTextAnalysisResponse:
    del request
    flagged = result.flagged_for_review or _is_low_confidence_result(result)
    return result.model_copy(update={"flagged_for_review": flagged})


async def _run_openrouter_text_analysis(
    request: HighlightedTextAnalysisRequest,
    lookup_key: str,
    openrouter_api_key: str,
) -> HighlightedTextAnalysisResponse:
    try:
        result = await agent.analyze_highlighted_text(
            selected_text=request.selected_text,
            page_url=request.page_url,
            surrounding_text=request.surrounding_text,
            page_title=request.page_title,
            page_domain=request.page_domain,
            nearest_heading=request.nearest_heading,
            text_model_speed=request.text_model_speed,
            text_model_tier=request.text_model_tier,
            openrouter_api_key=openrouter_api_key,
        )
    except OpenRouterAuthError as exc:
        raise HTTPException(
            status_code=401,
            detail="OpenRouter API key is missing or invalid.",
        ) from exc
    final = _stage_low_confidence_text(request, result)
    del lookup_key
    return final


def _try_db_image_lookup(image_hash: str) -> ImageAnalysisResponse | None:
    """
    Check the PostgreSQL cached_image_analyses table for an exact hash match.
    Returns a pre-built response on hit, None on miss.
    """
    cached = lookup_cached_image(image_hash)
    if cached is None:
        return None

    cached["model_used"] = f"cached:{cached.get('model_used', 'unknown')}"
    return ImageAnalysisResponse.model_validate(cached)


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    app = FastAPI(title="Brainrot Translator API")
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    @app.middleware("http")
    async def reject_openrouter_key_on_public_routes(request: Request, call_next):
        if request.url.path.startswith("/api/v1/telemetry/") and get_user_openrouter_api_key(request):
            return JSONResponse(
                status_code=400,
                content={"detail": "Do not send OpenRouter API keys to telemetry routes."},
            )
        return await call_next(request)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health(request: Request) -> dict[str, object]:
        local_text_model_available = settings.model_dir.exists()
        local_text_model_loaded = (
            get_model_components.cache_info().currsize > 0
            if hasattr(get_model_components, "cache_info")
            else False
        )
        local_quality_classifier_available = settings.quality_classifier_dir.exists()
        local_quality_classifier_loaded = (
            get_quality_classifier_components.cache_info().currsize > 0
            if hasattr(get_quality_classifier_components, "cache_info")
            else False
        )
        return {
            "status": "ok",
            "database_configured": bool(check_database_connection()),
            "local_text_model_available": local_text_model_available,
            "local_text_model_loaded": local_text_model_loaded,
            "local_quality_classifier_available": local_quality_classifier_available,
            "local_quality_classifier_loaded": local_quality_classifier_loaded,
            "user_openrouter_key_present": bool(get_user_openrouter_api_key(request)),
            "openrouter_configured": bool(get_user_openrouter_api_key(request)),
            "text_recheck_configured": bool(get_user_openrouter_api_key(request)),
            "api_base_url": settings.extension_api_base_url,
        }

    @app.get("/api/v1/public/model-config")
    async def public_model_config() -> dict[str, object]:
        return {
            "text": {
                "free": settings.openrouter_text_free_model,
                "premium": settings.openrouter_text_premium_model,
            },
            "image": {
                "free": settings.openrouter_image_free_model,
                "premium": settings.openrouter_image_premium_model,
                "fallbacks": list(settings.openrouter_vision_fallback_models),
            },
        }

    @app.post(
        "/translate",
        response_model=TranslateResponse,
    )
    async def translate(request: Request):
        try:
            payload = await request.json()
        except Exception:
            payload = None

        if not isinstance(payload, dict):
            return JSONResponse(
                status_code=400,
                content={"error": "Request body must be valid JSON."},
            )

        if "text" not in payload:
            return JSONResponse(
                status_code=400,
                content={"error": "Missing 'text' field."},
            )

        text = str(payload.get("text", "")).strip()
        if not text:
            return JSONResponse(
                status_code=400,
                content={"error": "The 'text' field cannot be empty."},
            )

        try:
            return translate_text(text)
        except Exception as exc:
            return JSONResponse(
                status_code=500,
                content={"error": f"Generation failed: {exc}"},
            )

    @app.post(
        "/api/v1/reverse-translate",
        response_model=ReverseTranslateResponse,
    )
    async def reverse_translate(
        request: Request,
        payload: ReverseTranslateRequest,
    ) -> ReverseTranslateResponse:
        openrouter_api_key = require_user_openrouter_api_key(request)
        try:
            result = await reverse_translate_text(
                payload.text,
                text_model_speed=payload.text_model_speed,
                text_model_tier=payload.text_model_tier,
                openrouter_api_key=openrouter_api_key,
            )
        except OpenRouterAuthError as exc:
            raise HTTPException(
                status_code=401,
                detail="OpenRouter API key is missing or invalid.",
            ) from exc
        logger.info(
            "REVERSE TRANSLATE for %r via %s",
            payload.text[:80],
            result.model_used,
        )
        return result

    # ------------------------------------------------------------------
    # TEXT HIGHLIGHT – cache-first policy
    # ------------------------------------------------------------------

    @app.post(
        "/api/v1/analyze-highlighted-text",
        response_model=HighlightedTextAnalysisResponse,
    )
    @limiter.limit(settings.rate_limit_analyze_text)
    async def analyze_highlighted_text(
        request: Request,
        payload: HighlightedTextAnalysisRequest,
    ) -> HighlightedTextAnalysisResponse:
        lookup_key = _normalise_text_key(payload.selected_text)
        openrouter_cache_key = _text_model_cache_key(lookup_key, payload.text_model_tier)

        # ── Step 1: Check local slang_terms.json ──────────────────────
        json_hit = _try_slang_json_lookup(lookup_key)
        if json_hit is not None:
            logger.info("TEXT CACHE HIT (slang_terms.json) for '%s'", lookup_key)
            return json_hit

        # ── Step 2: Prefer the current trained local model/filter ──────
        local_hit = _try_local_model_text_analysis(payload.selected_text)
        if local_hit is not None:
            logger.info("TEXT LOCAL MODEL HIT for '%s'", lookup_key)
            if _is_low_confidence_result(local_hit):
                logger.info(
                    "TEXT LOCAL MODEL LOW CONFIDENCE for '%s' → calling OpenRouter",
                    lookup_key,
                )
                openrouter_api_key = require_user_openrouter_api_key(request)
                return await _run_openrouter_text_analysis(payload, openrouter_cache_key, openrouter_api_key)

            final = _stage_low_confidence_text(payload, local_hit)
            return final

        # ── Step 3: Check PostgreSQL cache table if no local model exists
        db_hit = _try_db_text_lookup(openrouter_cache_key)
        if db_hit is not None:
            logger.info("TEXT CACHE HIT (database) for '%s'", lookup_key)
            if _is_low_confidence_result(db_hit):
                logger.info(
                    "TEXT CACHE HIT LOW CONFIDENCE for '%s' → refreshing with OpenRouter",
                    lookup_key,
                )
                openrouter_api_key = require_user_openrouter_api_key(request)
                return await _run_openrouter_text_analysis(payload, openrouter_cache_key, openrouter_api_key)
            return db_hit

        # ── Step 4: Cache miss → call DeepSeek via OpenRouter ─────────
        logger.info("TEXT CACHE MISS for '%s' → calling OpenRouter", lookup_key)
        openrouter_api_key = require_user_openrouter_api_key(request)
        return await _run_openrouter_text_analysis(payload, openrouter_cache_key, openrouter_api_key)

    @app.post(
        "/api/v1/recheck-highlighted-text",
        response_model=HighlightedTextAnalysisResponse,
    )
    @limiter.limit(settings.rate_limit_recheck_text)
    async def recheck_highlighted_text(
        request: Request,
        payload: HighlightedTextAnalysisRequest,
    ) -> HighlightedTextAnalysisResponse:
        lookup_key = _normalise_text_key(payload.selected_text)
        openrouter_cache_key = _text_model_cache_key(lookup_key, payload.text_model_tier)
        logger.info("TEXT MANUAL RECHECK for '%s' → calling OpenRouter", lookup_key)
        openrouter_api_key = require_user_openrouter_api_key(request)
        return await _run_openrouter_text_analysis(payload, openrouter_cache_key, openrouter_api_key)

    @app.post(
        "/api/v1/telemetry/slang-detections",
        response_model=SlangDetectionsTelemetryResponse,
    )
    @limiter.limit(settings.rate_limit_dashboard)
    async def ingest_slang_detections(
        request: Request,
        payload: SlangDetectionsTelemetryRequest,
    ) -> SlangDetectionsTelemetryResponse:
        del request
        items = [{"term": item.term, "count": item.count} for item in payload.items]
        stored = record_slang_detections(
            items,
            unsafe_keywords=settings.unsafe_slang_keywords,
        )
        return SlangDetectionsTelemetryResponse(accepted=len(items), stored=stored)

    @app.get(
        "/api/v1/public/top-slang",
        response_model=PublicTopSlangResponse,
    )
    @limiter.limit(settings.rate_limit_dashboard)
    async def public_top_slang(
        request: Request,
        period: str = "month",
        year: int | None = None,
        limit: int = 20,
    ) -> PublicTopSlangResponse:
        del request
        safe_period = "year" if str(period).casefold() == "year" else "month"
        raw = list_top_slang(period=safe_period, year=year, limit=limit)
        return PublicTopSlangResponse(**raw)

    @app.get(
        "/api/v1/admin/slang",
        response_model=AdminSlangListResponse,
    )
    @limiter.limit(settings.rate_limit_dashboard)
    async def admin_list_slang(
        request: Request,
        limit: int = 100,
    ) -> AdminSlangListResponse:
        await require_google_admin(request)
        return AdminSlangListResponse(items=list_admin_slang(limit))

    @app.patch(
        "/api/v1/admin/slang/{normalized_term}",
        response_model=AdminSlangItem,
    )
    @limiter.limit(settings.rate_limit_dashboard)
    async def admin_update_slang(
        request: Request,
        normalized_term: str,
        payload: AdminSlangModerationUpdate,
    ) -> AdminSlangItem:
        admin_email = await require_google_admin(request)
        updated = update_slang_moderation(
            normalize_slang_term(normalized_term),
            status=payload.status,
            reason=payload.reason,
            updated_by=admin_email,
        )
        if updated is None:
            raise HTTPException(status_code=404, detail="Slang term could not be updated.")
        return AdminSlangItem(**updated)

    @app.get(
        "/api/v1/dashboard/word-frequency",
        response_model=DashboardWordFrequencyResponse,
    )
    @limiter.limit(settings.rate_limit_dashboard)
    async def dashboard_word_frequency(
        request: Request,
        limit: int = 20,
    ) -> DashboardWordFrequencyResponse:
        safe_limit = max(1, min(int(limit), 100))
        return DashboardWordFrequencyResponse(items=list_word_frequencies(safe_limit))

    @app.get(
        "/api/v1/dashboard/stats",
        response_model=DashboardStatsResponse,
    )
    @limiter.limit(settings.rate_limit_dashboard)
    async def dashboard_stats(request: Request) -> DashboardStatsResponse:
        raw = get_dashboard_stats()
        return DashboardStatsResponse(**raw)

    # ------------------------------------------------------------------
    # SCREENSHOT / VISION – cache-first policy
    # ------------------------------------------------------------------

    @app.post(
        "/api/v1/analyze-screenshot-media",
        response_model=ImageAnalysisResponse,
    )
    @limiter.limit(settings.rate_limit_analyze_media)
    async def analyze_screenshot_media(
        request: Request,
        payload: ScreenshotMediaRequest,
    ) -> ImageAnalysisResponse:
        image_bytes = decode_base64_payload(
            payload.image_base64,
            field_name="image_base64",
        )
        if len(image_bytes) > settings.max_image_bytes:
            raise HTTPException(
                status_code=422,
                detail="Images larger than 5MB are not accepted.",
            )

        if payload.frame0_base64:
            frame_bytes = decode_base64_payload(
                payload.frame0_base64,
                field_name="frame0_base64",
            )
            if len(frame_bytes) > settings.max_image_bytes:
                raise HTTPException(
                    status_code=422,
                    detail="GIF first-frame payloads larger than 5MB are not accepted.",
                )

        # ── Step 1: Hash the image payload ────────────────────────────
        image_hash = _hash_image_payload(payload.image_base64)

        # ── Step 2: Check PostgreSQL cache table ──────────────────────
        db_hit = _try_db_image_lookup(image_hash)
        if db_hit is not None:
            logger.info("IMAGE CACHE HIT (database) for hash %s", image_hash[:16])
            return db_hit

        # ── Step 3: Cache miss → call Gemini via OpenRouter ───────────
        openrouter_api_key = require_user_openrouter_api_key(request)
        logger.info("IMAGE CACHE MISS for hash %s → calling OpenRouter", image_hash[:16])
        try:
            result = await agent.analyze_screenshot_media(
                image_base64=payload.image_base64,
                media_type=payload.media_type,
                source_url=payload.source_url,
                frame0_base64=payload.frame0_base64,
                frame0_media_type=payload.frame0_media_type,
                page_title=payload.page_title,
                page_domain=payload.page_domain,
                image_model_tier=payload.image_model_tier,
                openrouter_api_key=openrouter_api_key,
            )
        except OpenRouterAuthError as exc:
            raise HTTPException(
                status_code=401,
                detail="OpenRouter API key is missing or invalid.",
            ) from exc

        flagged = result.flagged_for_review or result.confidence_score < settings.low_confidence_threshold
        final = result.model_copy(update={"flagged_for_review": flagged})

        # ── Persist to DB cache for next time ─────────────────────────
        save_cached_image(image_hash, final.model_dump())

        return final

    @app.post(
        "/api/v1/analyze-image",
        response_model=ImageAnalysisResponse,
    )
    async def analyze_image_alias(
        request: Request,
        payload: ImageAnalysisRequest,
    ) -> ImageAnalysisResponse:
        screenshot_payload = ScreenshotMediaRequest.model_validate(payload.model_dump())
        return await analyze_screenshot_media(request, screenshot_payload)

    return app


app = create_app()
