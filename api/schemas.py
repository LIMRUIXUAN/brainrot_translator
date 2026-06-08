from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


SUPPORTED_MEDIA_TYPES = {
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/webp",
}


class TranslateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("text cannot be empty")
        return cleaned


class TranslateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    normal: str
    used_mock: bool = False
    model_source: str = "local_transformer"


class ReverseTranslateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1)
    page_url: Optional[str] = None
    text_model_speed: Literal["fast", "slow"] = "fast"

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("text cannot be empty")
        return cleaned

    @field_validator("page_url")
    @classmethod
    def validate_page_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ReverseTranslateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reverse_text: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    model_used: str


class HighlightedTextAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_text: str = Field(..., min_length=1)
    text_model_speed: Literal["fast", "slow"] = "fast"
    page_url: Optional[str] = None
    surrounding_text: Optional[str] = None
    page_title: Optional[str] = None
    page_domain: Optional[str] = None
    nearest_heading: Optional[str] = None

    @field_validator("selected_text")
    @classmethod
    def validate_selected_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("selected_text cannot be empty")
        return cleaned

    @field_validator("page_url", "surrounding_text", "page_title", "page_domain", "nearest_heading")
    @classmethod
    def validate_optional_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class HighlightedTextAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_brainrot: bool
    brainrot_text: Optional[str] = None
    equivalent_text: Optional[str] = None
    formal_explanation: Optional[str] = None
    sentiment_label: Literal["positive", "negative", "neutral", "mixed", "unclear"] = "unclear"
    sentiment_rationale: Optional[str] = None
    confidence_score: float = Field(ge=0.0, le=1.0)
    flagged_for_review: bool = False
    model_used: Optional[str] = None

    @classmethod
    def safe_fallback(
        cls,
        *,
        original_text: str,
        equivalent_text: Optional[str] = None,
        confidence_score: float = 0.0,
        flagged_for_review: bool = True,
        model_used: Optional[str] = None,
    ) -> "HighlightedTextAnalysisResponse":
        return cls(
            is_brainrot=False,
            brainrot_text=original_text,
            equivalent_text=equivalent_text or original_text,
            formal_explanation="No model response was available, so the original text was returned unchanged.",
            sentiment_label="unclear",
            sentiment_rationale="No live model evidence was available.",
            confidence_score=confidence_score,
            flagged_for_review=flagged_for_review,
            model_used=model_used,
        )


class ScreenshotMediaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_base64: str = Field(..., min_length=1)
    media_type: str
    source_url: Optional[str] = None
    frame0_base64: Optional[str] = None
    frame0_media_type: Optional[str] = None
    page_title: Optional[str] = None
    page_domain: Optional[str] = None

    @field_validator("image_base64")
    @classmethod
    def validate_image_base64(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("image_base64 cannot be empty")
        return cleaned

    @field_validator("media_type")
    @classmethod
    def validate_media_type(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if cleaned not in SUPPORTED_MEDIA_TYPES:
            raise ValueError(
                f"media_type must be one of: {', '.join(sorted(SUPPORTED_MEDIA_TYPES))}"
            )
        return cleaned

    @field_validator("source_url", "frame0_base64")
    @classmethod
    def validate_optional_base_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("frame0_media_type")
    @classmethod
    def validate_frame_media_type(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip().lower()
        if cleaned not in SUPPORTED_MEDIA_TYPES:
            raise ValueError(
                f"frame0_media_type must be one of: {', '.join(sorted(SUPPORTED_MEDIA_TYPES))}"
            )
        return cleaned


class ImageAnalysisRequest(ScreenshotMediaRequest):
    pass


class ImageAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_brainrot: bool
    brainrot_meaning: Optional[str] = None
    equivalent_text: Optional[str] = None
    formal_explanation: Optional[str] = None
    confidence_score: float = Field(ge=0.0, le=1.0)
    flagged_for_review: bool = False
    model_used: Optional[str] = None
    used_frame_fallback: bool = False

    @classmethod
    def safe_fallback(
        cls,
        *,
        confidence_score: float = 0.0,
        flagged_for_review: bool = True,
        model_used: Optional[str] = None,
        used_frame_fallback: bool = False,
    ) -> "ImageAnalysisResponse":
        return cls(
            is_brainrot=False,
            brainrot_meaning=None,
            equivalent_text=None,
            formal_explanation=None,
            confidence_score=confidence_score,
            flagged_for_review=flagged_for_review,
            model_used=model_used,
            used_frame_fallback=used_frame_fallback,
        )


class WordFrequencyItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term: str
    count: int
    last_seen_at: Optional[str] = None


class DashboardWordFrequencyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[WordFrequencyItem]


class DashboardStatsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_text_analyses: int = 0
    total_image_analyses: int = 0
    unique_terms: int = 0
    top_term: Optional[str] = None
    top_term_count: int = 0
