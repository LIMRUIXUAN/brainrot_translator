from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import httpx

from .config import Settings
from .schemas import (
    HighlightedTextAnalysisResponse,
    ImageAnalysisResponse,
)


REFERENCE_FOCUS_TERMS = (
    "based",
    "mid",
    "ratio",
    "rizz",
    "skibidi",
    "skill issue",
    "slay",
    "aura",
    "ate",
    "bet",
    "bffr",
    "caught in 4K",
)
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def _trim_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


class BrainrotAgent:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def load_reference_examples(self) -> list[dict[str, str]]:
        reference_path: Path = self.settings.reference_dataset_path
        if not reference_path.exists():
            return []
        try:
            payload = json.loads(reference_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(payload, list):
            return []

        by_term = {
            str(item.get("term", "")).strip().casefold(): item
            for item in payload
            if isinstance(item, dict) and str(item.get("term", "")).strip()
        }
        examples: list[dict[str, str]] = []
        for term in REFERENCE_FOCUS_TERMS:
            entry = by_term.get(term.casefold())
            if not entry:
                continue
            examples.append(
                {
                    "term": str(entry.get("term", "")).strip(),
                    "meaning": str(entry.get("meaning", "")).strip(),
                }
            )
        return examples

    def build_reference_block(self) -> str:
        examples = self.load_reference_examples()
        if not examples:
            return "Reference slang terms: unavailable."

        lines = ["Reference slang terms from the local slang_terms.json dataset:"]
        for entry in examples:
            lines.append(f'- {entry["term"]}: {entry["meaning"]}')
        return "\n".join(lines)

    async def _execute_openrouter_call(
        self,
        *,
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        if not self.settings.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not configured.")

        headers = {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.settings.openrouter_http_referer,
            "X-OpenRouter-Title": self.settings.openrouter_app_title,
        }
        timeout = httpx.Timeout(timeout_seconds, connect=min(5.0, timeout_seconds))
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(OPENROUTER_URL, json=payload, headers=headers)
            response.raise_for_status()

        body = response.json()
        raw_content = body["choices"][0]["message"]["content"]
        if isinstance(raw_content, list):
            raw_content = "".join(
                part.get("text", "")
                for part in raw_content
                if isinstance(part, dict)
            )

        parsed = json.loads(raw_content)
        if not isinstance(parsed, dict):
            raise ValueError("OpenRouter response did not contain a JSON object.")
        return parsed

    def _build_text_system_prompt(self) -> str:
        return (
            "You are a structured internet-culture translation engine.\n"
            "Decide whether the highlighted text functions as brainrot, slang, or meme-coded internet speech.\n"
            "Return JSON only, following the schema exactly.\n"
            "Strict behavior rules:\n"
            "- Full Sentence Translation: translate the complete highlighted text structure into a natural, fully formed formal English sentence. Do not isolate only one slang keyword.\n"
            "- Preserve the user's full meaning, stance, and implied social judgment while making it formally understandable.\n"
            "- Punchy Explanations: keep formal_explanation direct, culturally precise, and focused on why the meme/slang is used, its vibe, and its current internet-culture stance.\n"
            "- Avoid dry dictionary-style definitions, etymology dumps, or academic linguistic filler.\n"
            "When the text is brainrot/slang, provide:\n"
            "- the complete original highlighted text in brainrot_text\n"
            "- a complete formal-English sentence in equivalent_text\n"
            "- a concise cultural explanation in formal_explanation\n"
            "- a sentiment_label of positive, negative, neutral, mixed, or unclear\n"
            "- a short sentiment_rationale\n"
            "- a confidence score between 0 and 1\n"
            "When the text is not brainrot, set is_brainrot to false and still provide the safest equivalent_text possible."
        )

    def _build_text_user_prompt(
        self,
        *,
        selected_text: str,
        page_url: Optional[str],
        surrounding_text: Optional[str],
    ) -> str:
        page_hint = page_url or "unavailable"
        surrounding = surrounding_text or "unavailable"
        return (
            f'Analyze the entire highlighted text selection: "{selected_text}"\n'
            "1. Translate the COMPLETE sentence context smoothly into formal English.\n"
            "2. Identify any core brainrot/slang elements and provide a sharp, concise explanation of its cultural context and exact internet stance.\n"
            f"Page URL hint: {page_hint}\n"
            f"Surrounding text hint: {surrounding}\n"
            "Estimate sentiment from the complete message, not from one isolated term.\n"
            f"{self.build_reference_block()}"
        )

    def _build_image_system_prompt(self) -> str:
        return (
            "You are a multimodal internet-culture classifier.\n"
            "Determine whether the attached image or GIF functions as brainrot vocabulary, "
            "not whether it is merely funny or emotional.\n"
            "Strict behavior rules:\n"
            "- Full Message Translation: translate the complete visual message into a natural, fully formed formal English sentence. Do not isolate only one meme label.\n"
            "- Capture the visual's social stance, implied joke, and internet-culture verdict.\n"
            "- Punchy Explanations: keep formal_explanation direct, culturally precise, and focused on why the meme works, its vibe, and its current internet-culture stance.\n"
            "- Avoid dry dictionary-style definitions, etymology dumps, or academic linguistic filler.\n"
            "Ignore generic reaction images, decorative assets, product images, and ordinary photos.\n"
            "If is_brainrot is true, provide brainrot_meaning, equivalent_text, and formal_explanation.\n"
            "If is_brainrot is false, set those fields to null.\n"
            "Return JSON only and follow the schema exactly."
        )

    def _build_image_user_prompt(self, *, source_url: Optional[str], using_frame: bool) -> str:
        source_line = f"Source URL hint: {source_url}" if source_url else "Source URL hint: unavailable"
        frame_line = (
            "The attached image is a first-frame fallback extracted from a GIF."
            if using_frame
            else "The attached asset is the original screenshot or raw media."
        )
        return (
            "Analyze the attached screenshot/media asset.\n"
            "1. Deconstruct the entire overarching message and translate it into a direct formal English sentence.\n"
            "2. Provide a brief, punchy explanation focusing on the core point of the brainrot meme meaning, ignoring unnecessary academic filler.\n"
            f"{source_line}\n"
            f"{frame_line}\n"
            f"{self.build_reference_block()}"
        )

    def _normalize_text_result(
        self,
        result: HighlightedTextAnalysisResponse,
        *,
        selected_text: str,
        model_used: str,
    ) -> HighlightedTextAnalysisResponse:
        confidence = max(0.0, min(1.0, float(result.confidence_score)))
        flagged = confidence < self.settings.low_confidence_threshold
        return HighlightedTextAnalysisResponse(
            is_brainrot=bool(result.is_brainrot),
            brainrot_text=_trim_text(result.brainrot_text) or selected_text,
            equivalent_text=_trim_text(result.equivalent_text) or selected_text,
            formal_explanation=_trim_text(result.formal_explanation),
            sentiment_label=result.sentiment_label,
            sentiment_rationale=_trim_text(result.sentiment_rationale),
            confidence_score=confidence,
            flagged_for_review=flagged,
            model_used=model_used,
        )

    def _normalize_image_result(
        self,
        result: ImageAnalysisResponse,
        *,
        model_used: str,
        used_frame_fallback: bool,
    ) -> ImageAnalysisResponse:
        confidence = max(0.0, min(1.0, float(result.confidence_score)))
        flagged = confidence < self.settings.low_confidence_threshold
        if not result.is_brainrot:
            return ImageAnalysisResponse.safe_fallback(
                confidence_score=confidence,
                flagged_for_review=flagged,
                model_used=model_used,
                used_frame_fallback=used_frame_fallback,
            )
        return ImageAnalysisResponse(
            is_brainrot=True,
            brainrot_meaning=_trim_text(result.brainrot_meaning),
            equivalent_text=_trim_text(result.equivalent_text),
            formal_explanation=_trim_text(result.formal_explanation),
            confidence_score=confidence,
            flagged_for_review=flagged,
            model_used=model_used,
            used_frame_fallback=used_frame_fallback,
        )

    def _heuristic_text_fallback(self, selected_text: str) -> HighlightedTextAnalysisResponse:
        lowered = selected_text.casefold()
        matches = [
            entry
            for entry in self.load_reference_examples()
            if entry["term"].casefold() in lowered
        ]
        if matches:
            equivalent = "; ".join(f'{entry["term"]}: {entry["meaning"]}' for entry in matches[:3])
            return HighlightedTextAnalysisResponse.safe_fallback(
                original_text=selected_text,
                equivalent_text=f"Mock glossary fallback: {equivalent}",
                confidence_score=0.35,
                flagged_for_review=True,
                model_used="mock_glossary_fallback",
            )
        return HighlightedTextAnalysisResponse.safe_fallback(
            original_text=selected_text,
            equivalent_text=f"Mock fallback: {selected_text}",
            confidence_score=0.15,
            flagged_for_review=True,
            model_used="mock_glossary_fallback",
        )

    async def analyze_highlighted_text(
        self,
        selected_text: str,
        page_url: Optional[str] = None,
        surrounding_text: Optional[str] = None,
    ) -> HighlightedTextAnalysisResponse:
        payload = {
            "model": self.settings.openrouter_text_model,
            "messages": [
                {"role": "system", "content": self._build_text_system_prompt()},
                {
                    "role": "user",
                    "content": self._build_text_user_prompt(
                        selected_text=selected_text,
                        page_url=page_url,
                        surrounding_text=surrounding_text,
                    ),
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "highlighted_text_analysis_response",
                    "strict": True,
                    "schema": HighlightedTextAnalysisResponse.model_json_schema(),
                },
            },
            "temperature": 0.1,
        }

        try:
            parsed = await self._execute_openrouter_call(payload=payload, timeout_seconds=8.0)
            result = HighlightedTextAnalysisResponse.model_validate(parsed)
            return self._normalize_text_result(
                result,
                selected_text=selected_text,
                model_used=self.settings.openrouter_text_model,
            )
        except httpx.TimeoutException:
            return self._heuristic_text_fallback(selected_text)
        except Exception:
            return self._heuristic_text_fallback(selected_text)

    async def _call_image_model(
        self,
        *,
        model: str,
        image_base64: str,
        media_type: str,
        source_url: Optional[str],
        using_frame: bool,
        timeout_seconds: float = 12.0,
    ) -> ImageAnalysisResponse:
        data_url = (
            image_base64.strip()
            if image_base64.strip().startswith("data:")
            else f"data:{media_type};base64,{image_base64.strip()}"
        )
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": self._build_image_system_prompt()},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": self._build_image_user_prompt(
                                source_url=source_url,
                                using_frame=using_frame,
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        },
                    ],
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "image_analysis_response",
                    "strict": True,
                    "schema": ImageAnalysisResponse.model_json_schema(),
                },
            },
            "temperature": 0.1,
        }

        parsed = await self._execute_openrouter_call(payload=payload, timeout_seconds=timeout_seconds)
        result = ImageAnalysisResponse.model_validate(parsed)
        return self._normalize_image_result(
            result,
            model_used=model,
            used_frame_fallback=using_frame,
        )

    async def analyze_screenshot_media(
        self,
        image_base64: str,
        media_type: str,
        source_url: Optional[str] = None,
        frame0_base64: Optional[str] = None,
        frame0_media_type: Optional[str] = None,
    ) -> ImageAnalysisResponse:
        try:
            return await self._call_image_model(
                model=self.settings.openrouter_vision_model,
                image_base64=image_base64,
                media_type=media_type,
                source_url=source_url,
                using_frame=False,
            )
        except httpx.TimeoutException:
            return ImageAnalysisResponse.safe_fallback(
                confidence_score=0.0,
                flagged_for_review=True,
                model_used=self.settings.openrouter_vision_model,
                used_frame_fallback=False,
            )
        except Exception:
            pass

        if frame0_base64 and frame0_media_type:
            for model in self.settings.openrouter_vision_fallback_models:
                try:
                    return await self._call_image_model(
                        model=model,
                        image_base64=frame0_base64,
                        media_type=frame0_media_type,
                        source_url=source_url,
                        using_frame=True,
                    )
                except httpx.TimeoutException:
                    return ImageAnalysisResponse.safe_fallback(
                        confidence_score=0.0,
                        flagged_for_review=True,
                        model_used=model,
                        used_frame_fallback=True,
                    )
                except Exception:
                    continue

        return ImageAnalysisResponse.safe_fallback(
            confidence_score=0.0,
            flagged_for_review=True,
            model_used=self.settings.openrouter_vision_model,
            used_frame_fallback=False,
        )
