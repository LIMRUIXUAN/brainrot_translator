from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "processed" / "slang_terms.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "processed" / "training_dataset_final_local_only.csv"
DEFAULT_REPORT = PROJECT_ROOT / "data" / "processed" / "training_dataset_quality_report.txt"

PROMPT_PREFIX = "Convert brainrot English to normal English:"
REQUIRED_COLUMNS = (
    "input_text",
    "target_text",
    "task_type",
    "source",
    "quality_label",
    "reason",
)


def clean_space(value: object) -> str:
    text = str(value or "").strip()
    return re.sub(r"\s+", " ", text)


def load_terms(path: Path) -> list[dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"{path} must contain a JSON list.")

    rows: list[dict[str, str]] = []
    seen_terms: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        term = clean_space(item.get("term"))
        meaning = clean_space(item.get("meaning"))
        if not term or not meaning:
            continue
        key = term.casefold()
        if key in seen_terms:
            continue
        seen_terms.add(key)
        rows.append(
            {
                "term": term,
                "meaning": meaning,
                "example": clean_space(item.get("example")),
                "source": clean_space(item.get("source")) or "slang_terms.json",
            }
        )
    return rows


def build_training_rows(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()

    def add(input_text: str, target_text: str, task_type: str, source: str, reason: str) -> None:
        input_text = clean_space(input_text)
        target_text = clean_space(target_text)
        key = (input_text.casefold(), target_text.casefold())
        if not input_text or not target_text or key in seen_pairs:
            return
        seen_pairs.add(key)
        rows.append(
            {
                "input_text": input_text,
                "target_text": target_text,
                "task_type": task_type,
                "source": source,
                "quality_label": "local_reference",
                "reason": reason,
            }
        )

    for entry in entries:
        term = entry["term"]
        meaning = entry["meaning"]
        source = entry["source"]

        add(
            f"{PROMPT_PREFIX} {term}",
            meaning,
            "term_definition",
            source,
            "Exact glossary term converted to normal English meaning.",
        )
        add(
            f"{PROMPT_PREFIX} What does '{term}' mean?",
            meaning,
            "term_definition_question",
            source,
            "Question-form glossary prompt for robustness.",
        )
        add(
            f"{PROMPT_PREFIX} People online said '{term}'.",
            f"People online used slang meaning: {meaning}",
            "sentence_translation",
            source,
            "Conservative synthetic sentence built from local glossary meaning.",
        )

        if entry["example"]:
            add(
                f"{PROMPT_PREFIX} {entry['example']}",
                meaning,
                "example_translation",
                source,
                "Original example from source glossary.",
            )

    return rows


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REQUIRED_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_report(path: Path, entries: list[dict[str, str]], rows: list[dict[str, str]]) -> None:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["task_type"]] = counts.get(row["task_type"], 0) + 1

    lines = [
        "Brainrot Translator training dataset report",
        "",
        f"source_entries: {len(entries)}",
        f"training_rows: {len(rows)}",
        "",
        "rows_by_task_type:",
    ]
    for task_type in sorted(counts):
        lines.append(f"- {task_type}: {counts[task_type]}")

    lines.extend(
        [
            "",
            "notes:",
            "- slang_terms.json remains the fixed reference vocabulary.",
            "- This CSV is for local FLAN-T5 training and is not updated automatically by app usage.",
            "- Review random samples before training; quality matters more than row count.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the local-only FLAN-T5 training CSV from slang_terms.json.",
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    entries = load_terms(args.input)
    rows = build_training_rows(entries)
    write_csv(args.output, rows)
    write_report(args.report, entries, rows)
    print(f"Wrote {len(rows)} rows to {args.output}")
    print(f"Wrote report to {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
