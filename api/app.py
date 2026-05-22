from __future__ import annotations

try:
    from .main import app, create_app, get_model_components, get_quality_classifier_components, translate_text
except ImportError:  # pragma: no cover - compatibility for direct execution
    from main import app, create_app, get_model_components, get_quality_classifier_components, translate_text


__all__ = [
    "app",
    "create_app",
    "get_model_components",
    "get_quality_classifier_components",
    "translate_text",
]
