from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class LocalTranslationResult:
    normal: str
    used_mock: bool
    matched_terms: tuple[str, ...]
    model_source: str


class MockLocalTranslator:
    def __init__(self, reference_dataset_path: Path) -> None:
        self.reference_dataset_path = reference_dataset_path

    @lru_cache(maxsize=1)
    def _load_reference_entries(self) -> tuple[tuple[str, str], ...]:
        if not self.reference_dataset_path.exists():
            return ()

        try:
            payload = json.loads(self.reference_dataset_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return ()

        if not isinstance(payload, list):
            return ()

        entries: list[tuple[str, str]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            term = str(item.get("term", "")).strip()
            meaning = str(item.get("meaning", "")).strip()
            if term and meaning:
                entries.append((term, meaning))
        return tuple(entries)

    def translate(self, text: str) -> LocalTranslationResult:
        cleaned = text.strip()
        if not cleaned:
            return LocalTranslationResult(
                normal="",
                used_mock=True,
                matched_terms=(),
                model_source="mock_glossary",
            )

        lowered = cleaned.casefold()
        exact_matches = [
            (term, meaning)
            for term, meaning in self._load_reference_entries()
            if term.casefold() == lowered
        ]
        if exact_matches:
            term, meaning = exact_matches[0]
            return LocalTranslationResult(
                normal=meaning,
                used_mock=True,
                matched_terms=(term,),
                model_source="mock_glossary",
            )

        matched: list[tuple[str, str]] = []
        for term, meaning in sorted(
            self._load_reference_entries(),
            key=lambda item: len(item[0]),
            reverse=True,
        ):
            normalized_term = term.casefold().strip()
            if len(normalized_term) < 2:
                continue
            pattern = re.compile(rf"(?<!\w){re.escape(normalized_term)}(?!\w)")
            if pattern.search(lowered):
                matched.append((term, meaning))

        if matched:
            if len(matched) == 1 and matched[0][0].casefold() == lowered:
                normal = matched[0][1]
            else:
                explanations = [f"{term}: {meaning}" for term, meaning in matched[:4]]
                normal = "Mock translation fallback from local slang glossary: " + " | ".join(explanations)
            return LocalTranslationResult(
                normal=normal,
                used_mock=True,
                matched_terms=tuple(term for term, _ in matched),
                model_source="mock_glossary",
            )

        return LocalTranslationResult(
            normal=f"Mock translation fallback: {cleaned}",
            used_mock=True,
            matched_terms=(),
            model_source="mock_glossary",
        )
