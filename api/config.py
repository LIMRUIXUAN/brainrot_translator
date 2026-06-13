from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"
load_dotenv(ENV_PATH, override=False)


def _env_flag(name: str, default: bool) -> bool:
    value = (os.getenv(name) or "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def _env_list(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    items = [item.strip() for item in raw.split(",")]
    return tuple(item for item in items if item)


@dataclass(frozen=True)
class Settings:
    project_root: Path
    env_path: Path
    model_dir: Path
    quality_classifier_dir: Path
    reference_dataset_path: Path
    openrouter_text_model: str
    openrouter_text_fast_model: str
    openrouter_text_slow_model: str
    openrouter_text_free_model: str
    openrouter_text_premium_model: str
    openrouter_vision_model: str
    openrouter_image_free_model: str
    openrouter_image_premium_model: str
    openrouter_vision_fallback_models: tuple[str, ...]
    openrouter_http_referer: str
    openrouter_app_title: str
    google_admin_client_id: str
    admin_google_emails: tuple[str, ...]
    unsafe_slang_keywords: tuple[str, ...]
    low_confidence_threshold: float
    max_image_bytes: int
    cache_ttl_hours: int
    rate_limit_analyze_text: str
    rate_limit_recheck_text: str
    rate_limit_analyze_media: str
    rate_limit_dashboard: str
    enable_local_translation_stub: bool
    extension_api_base_url: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        project_root=PROJECT_ROOT,
        env_path=ENV_PATH,
        model_dir=PROJECT_ROOT / "models" / "brainrot-translator-v1",
        quality_classifier_dir=PROJECT_ROOT / "models" / "brainrot-quality-classifier-v1",
        reference_dataset_path=PROJECT_ROOT / "data" / "processed" / "slang_terms.json",
        openrouter_text_model=(
            os.getenv("OPENROUTER_TEXT_MODEL") or "deepseek/deepseek-v4-flash"
        ).strip(),
        openrouter_text_fast_model=(
            os.getenv("OPENROUTER_TEXT_FAST_MODEL") or "deepseek/deepseek-v4-flash"
        ).strip(),
        openrouter_text_slow_model=(
            os.getenv("OPENROUTER_TEXT_SLOW_MODEL") or "nvidia/nemotron-3-super-120b-a12b:free"
        ).strip(),
        openrouter_text_free_model=(
            os.getenv("OPENROUTER_TEXT_FREE_MODEL") or "nvidia/nemotron-3-super-120b-a12b:free"
        ).strip(),
        openrouter_text_premium_model=(
            os.getenv("OPENROUTER_TEXT_PREMIUM_MODEL") or "deepseek/deepseek-v4-flash"
        ).strip(),
        openrouter_vision_model=(
            os.getenv("OPENROUTER_VISION_MODEL") or "google/gemini-3-flash-preview"
        ).strip(),
        openrouter_image_free_model=(
            os.getenv("OPENROUTER_IMAGE_FREE_MODEL")
            or "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"
        ).strip(),
        openrouter_image_premium_model=(
            os.getenv("OPENROUTER_IMAGE_PREMIUM_MODEL") or "google/gemini-3.1-flash-lite"
        ).strip(),
        openrouter_vision_fallback_models=_env_list(
            "OPENROUTER_VISION_FALLBACK_MODELS",
            ("google/gemini-3-flash-preview",),
        ),
        openrouter_http_referer=(
            os.getenv("OPENROUTER_HTTP_REFERER")
            or "https://brainrot-translator.local"
        ).strip(),
        openrouter_app_title=(
            os.getenv("OPENROUTER_APP_TITLE") or "Brainrot Translator"
        ).strip(),
        google_admin_client_id=(os.getenv("GOOGLE_ADMIN_CLIENT_ID") or "").strip(),
        admin_google_emails=_env_list("ADMIN_GOOGLE_EMAILS", ()),
        unsafe_slang_keywords=_env_list(
            "BRAINROT_UNSAFE_SLANG_KEYWORDS",
            (
                "porn",
                "porno",
                "pornographic",
                "nsfw",
                "hentai",
                "sex",
                "nude",
                "nudes",
                "rape",
                "slur",
            ),
        ),
        low_confidence_threshold=float(
            (os.getenv("BRAINROT_LOW_CONFIDENCE_THRESHOLD") or "0.7").strip()
        ),
        max_image_bytes=int((os.getenv("BRAINROT_MAX_IMAGE_BYTES") or str(5 * 1024 * 1024)).strip()),
        cache_ttl_hours=int((os.getenv("BRAINROT_CACHE_TTL_HOURS") or "168").strip()),
        rate_limit_analyze_text=(
            os.getenv("BRAINROT_RATE_LIMIT_ANALYZE_TEXT") or "30/minute"
        ).strip(),
        rate_limit_recheck_text=(
            os.getenv("BRAINROT_RATE_LIMIT_RECHECK_TEXT") or "10/minute"
        ).strip(),
        rate_limit_analyze_media=(
            os.getenv("BRAINROT_RATE_LIMIT_ANALYZE_MEDIA") or "10/minute"
        ).strip(),
        rate_limit_dashboard=(
            os.getenv("BRAINROT_RATE_LIMIT_DASHBOARD") or "60/minute"
        ).strip(),
        enable_local_translation_stub=_env_flag(
            "ENABLE_LOCAL_TRANSLATION_STUB",
            True,
        ),
        extension_api_base_url=(
            os.getenv("BRAINROT_API_BASE_URL") or "http://127.0.0.1:8000"
        ).strip(),
    )
# Trigger reload again
