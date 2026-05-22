from __future__ import annotations

import base64
import binascii
import hashlib
import logging
import os
import re
from functools import lru_cache

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .agent import BrainrotAgent
from .config import get_settings
from .database import (
    check_database_connection,
    flag_image_for_review,
    flag_text_for_review,
    increment_word_frequencies,
    list_word_frequencies,
    load_slang_terms_index,
    lookup_cached_image,
    lookup_cached_text,
    save_cached_image,
    save_cached_text,
)
from .local_translator import MockLocalTranslator
from .schemas import (
    DashboardWordFrequencyResponse,
    HighlightedTextAnalysisRequest,
    HighlightedTextAnalysisResponse,
    ImageAnalysisRequest,
    ImageAnalysisResponse,
    ScreenshotMediaRequest,
    TranslateResponse,
)

logger = logging.getLogger(__name__)

settings = get_settings()
agent = BrainrotAgent(settings=settings)
local_translator = MockLocalTranslator(settings.reference_dataset_path)

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


def _generate_local_translation(text: str) -> str | None:
    components = get_model_components()
    if components is None:
        return None

    tokenizer, model = components
    prompt = f"Convert brainrot English to normal English: {text.strip()}"
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=128)
    outputs = model.generate(
        **inputs,
        max_new_tokens=128,
        num_beams=4,
        do_sample=False,
    )
    return tokenizer.decode(outputs[0], skip_special_tokens=True).strip()


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


def _looks_like_brainrot_text(text: str) -> bool:
    lowered = text.casefold()
    for marker in SLANG_TEXT_MARKERS:
        pattern = rf"(?<![a-z0-9]){re.escape(marker.casefold())}(?![a-z0-9])"
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


def _record_text_frequency(selected_text: str, page_url: str | None) -> None:
    increment_word_frequencies(
        _extract_brainrot_frequency_terms(selected_text),
        page_url=page_url,
    )


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
    """Trim whitespace, lowercase – used as the cache lookup key for text."""
    return raw.strip().casefold()


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
    flagged = result.flagged_for_review or _is_low_confidence_result(result)
    if flagged:
        flag_text_for_review(
            source_text=request.selected_text,
            page_url=request.page_url,
            agent_equivalent_text=result.equivalent_text,
            confidence=result.confidence_score,
        )
    return result.model_copy(update={"flagged_for_review": flagged})


async def _run_openrouter_text_analysis(
    request: HighlightedTextAnalysisRequest,
    lookup_key: str,
) -> HighlightedTextAnalysisResponse:
    result = await agent.analyze_highlighted_text(
        selected_text=request.selected_text,
        page_url=request.page_url,
        surrounding_text=request.surrounding_text,
    )
    final = _stage_low_confidence_text(request, result)
    save_cached_text(lookup_key, final.model_dump())
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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, object]:
        local_text_model_available = settings.model_dir.exists()
        local_text_model_loaded = get_model_components() is not None
        local_quality_classifier_available = settings.quality_classifier_dir.exists()
        local_quality_classifier_loaded = get_quality_classifier_components() is not None
        return {
            "status": "ok",
            "database_configured": bool(check_database_connection()),
            "local_text_model_available": local_text_model_available,
            "local_text_model_loaded": local_text_model_loaded,
            "local_quality_classifier_available": local_quality_classifier_available,
            "local_quality_classifier_loaded": local_quality_classifier_loaded,
            "openrouter_configured": bool(settings.openrouter_api_key),
            "text_recheck_configured": bool(settings.openrouter_api_key),
            "api_base_url": settings.extension_api_base_url,
        }

    @app.post("/translate", response_model=TranslateResponse)
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

    # ------------------------------------------------------------------
    # TEXT HIGHLIGHT – cache-first policy
    # ------------------------------------------------------------------

    @app.post(
        "/api/v1/analyze-highlighted-text",
        response_model=HighlightedTextAnalysisResponse,
    )
    async def analyze_highlighted_text(
        request: HighlightedTextAnalysisRequest,
    ) -> HighlightedTextAnalysisResponse:
        lookup_key = _normalise_text_key(request.selected_text)
        _record_text_frequency(request.selected_text, request.page_url)

        # ── Step 1: Check local slang_terms.json ──────────────────────
        json_hit = _try_slang_json_lookup(lookup_key)
        if json_hit is not None:
            logger.info("TEXT CACHE HIT (slang_terms.json) for '%s'", lookup_key)
            return json_hit

        # ── Step 2: Prefer the current trained local model/filter ──────
        local_hit = _try_local_model_text_analysis(request.selected_text)
        if local_hit is not None:
            logger.info("TEXT LOCAL MODEL HIT for '%s'", lookup_key)
            if _is_low_confidence_result(local_hit):
                logger.info(
                    "TEXT LOCAL MODEL LOW CONFIDENCE for '%s' → calling OpenRouter",
                    lookup_key,
                )
                return await _run_openrouter_text_analysis(request, lookup_key)

            final = _stage_low_confidence_text(request, local_hit)
            save_cached_text(lookup_key, final.model_dump())
            return final

        # ── Step 3: Check PostgreSQL cache table if no local model exists
        db_hit = _try_db_text_lookup(lookup_key)
        if db_hit is not None:
            logger.info("TEXT CACHE HIT (database) for '%s'", lookup_key)
            if _is_low_confidence_result(db_hit):
                logger.info(
                    "TEXT CACHE HIT LOW CONFIDENCE for '%s' → refreshing with OpenRouter",
                    lookup_key,
                )
                return await _run_openrouter_text_analysis(request, lookup_key)
            return db_hit

        # ── Step 4: Cache miss → call DeepSeek via OpenRouter ─────────
        logger.info("TEXT CACHE MISS for '%s' → calling OpenRouter", lookup_key)
        return await _run_openrouter_text_analysis(request, lookup_key)

    @app.post(
        "/api/v1/recheck-highlighted-text",
        response_model=HighlightedTextAnalysisResponse,
    )
    async def recheck_highlighted_text(
        request: HighlightedTextAnalysisRequest,
    ) -> HighlightedTextAnalysisResponse:
        lookup_key = _normalise_text_key(request.selected_text)
        _record_text_frequency(request.selected_text, request.page_url)
        logger.info("TEXT MANUAL RECHECK for '%s' → calling OpenRouter", lookup_key)
        return await _run_openrouter_text_analysis(request, lookup_key)

    @app.get(
        "/api/v1/dashboard/word-frequency",
        response_model=DashboardWordFrequencyResponse,
    )
    async def dashboard_word_frequency(limit: int = 20) -> DashboardWordFrequencyResponse:
        safe_limit = max(1, min(int(limit), 100))
        return DashboardWordFrequencyResponse(items=list_word_frequencies(safe_limit))

    # ------------------------------------------------------------------
    # SCREENSHOT / VISION – cache-first policy
    # ------------------------------------------------------------------

    @app.post(
        "/api/v1/analyze-screenshot-media",
        response_model=ImageAnalysisResponse,
    )
    async def analyze_screenshot_media(
        request: ScreenshotMediaRequest,
    ) -> ImageAnalysisResponse:
        image_bytes = decode_base64_payload(
            request.image_base64,
            field_name="image_base64",
        )
        if len(image_bytes) > settings.max_image_bytes:
            raise HTTPException(
                status_code=422,
                detail="Images larger than 5MB are not accepted.",
            )

        if request.frame0_base64:
            frame_bytes = decode_base64_payload(
                request.frame0_base64,
                field_name="frame0_base64",
            )
            if len(frame_bytes) > settings.max_image_bytes:
                raise HTTPException(
                    status_code=422,
                    detail="GIF first-frame payloads larger than 5MB are not accepted.",
                )

        # ── Step 1: Hash the image payload ────────────────────────────
        image_hash = _hash_image_payload(request.image_base64)

        # ── Step 2: Check PostgreSQL cache table ──────────────────────
        db_hit = _try_db_image_lookup(image_hash)
        if db_hit is not None:
            logger.info("IMAGE CACHE HIT (database) for hash %s", image_hash[:16])
            return db_hit

        # ── Step 3: Cache miss → call Gemini via OpenRouter ───────────
        logger.info("IMAGE CACHE MISS for hash %s → calling OpenRouter", image_hash[:16])
        result = await agent.analyze_screenshot_media(
            image_base64=request.image_base64,
            media_type=request.media_type,
            source_url=request.source_url,
            frame0_base64=request.frame0_base64,
            frame0_media_type=request.frame0_media_type,
        )

        flagged = result.flagged_for_review or result.confidence_score < settings.low_confidence_threshold
        if flagged:
            flag_image_for_review(
                source_url=request.source_url,
                media_type=request.media_type,
                agent_meaning=result.brainrot_meaning or result.equivalent_text,
                confidence=result.confidence_score,
            )

        final = result.model_copy(update={"flagged_for_review": flagged})

        # ── Persist to DB cache for next time ─────────────────────────
        save_cached_image(image_hash, final.model_dump())

        return final

    @app.post("/api/v1/analyze-image", response_model=ImageAnalysisResponse)
    async def analyze_image_alias(request: ImageAnalysisRequest) -> ImageAnalysisResponse:
        screenshot_request = ScreenshotMediaRequest.model_validate(request.model_dump())
        return await analyze_screenshot_media(screenshot_request)

    return app


app = create_app()
