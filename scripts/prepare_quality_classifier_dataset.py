from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "processed" / "training_dataset_final_local_only.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "processed" / "translation_quality_classifier_dataset.csv"
PROMPT_PREFIX = "Convert brainrot English to normal English:"


def clean_space(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def strip_prompt(value: str) -> str:
    cleaned = clean_space(value)
    if cleaned.casefold().startswith(PROMPT_PREFIX.casefold()):
        return cleaned[len(PROMPT_PREFIX):].strip()
    return cleaned


def load_translation_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = {"input_text", "target_text"} - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing required columns in {path}: {sorted(missing)}")

        rows: list[dict[str, str]] = []
        for index, row in enumerate(reader, start=1):
            source_text = strip_prompt(row.get("input_text", ""))
            target_text = clean_space(row.get("target_text", ""))
            if not source_text or not target_text:
                continue
            rows.append(
                {
                    "source_row_id": str(index),
                    "source_text": source_text,
                    "target_text": target_text,
                }
            )
    if len(rows) < 100:
        raise ValueError(f"Need at least 100 usable translation rows, found {len(rows)}")
    return rows


def make_bad_candidate(row: dict[str, str], wrong_target: str, variant: int) -> tuple[str, str]:
    source_text = row["source_text"]
    target_text = row["target_text"]

    if variant == 0:
        return source_text, "bad_unchanged_source"
    if variant == 1:
        return f"{source_text[:1].upper()}{source_text[1:]}.", "bad_unchanged_source_with_surface_change"
    if variant == 2:
        return wrong_target, "bad_wrong_translation_pair"
    if variant == 3:
        return f"{target_text} {source_text}", "bad_slang_leak"
    return target_text[: max(1, len(target_text) // 2)].strip(), "bad_truncated_translation"


def build_quality_rows(
    translation_rows: list[dict[str, str]],
    *,
    bad_per_good: int,
    seed: int,
) -> list[dict[str, object]]:
    rng = random.Random(seed)
    shuffled_targets = [row["target_text"] for row in translation_rows]
    rng.shuffle(shuffled_targets)

    output_rows: list[dict[str, object]] = []
    for index, row in enumerate(translation_rows):
        output_rows.append(
            {
                "source_text": row["source_text"],
                "candidate_translation": row["target_text"],
                "label": 1,
                "label_text": "good_translation",
                "reason": "Gold target_text from the translation training dataset.",
                "source_row_id": row["source_row_id"],
            }
        )

        wrong_target = shuffled_targets[index]
        if wrong_target == row["target_text"]:
            wrong_target = shuffled_targets[(index + 1) % len(shuffled_targets)]

        for bad_index in range(bad_per_good):
            candidate, reason = make_bad_candidate(row, wrong_target, (index + bad_index) % 5)
            if clean_space(candidate).casefold() == clean_space(row["target_text"]).casefold():
                continue
            output_rows.append(
                {
                    "source_text": row["source_text"],
                    "candidate_translation": clean_space(candidate),
                    "label": 0,
                    "label_text": "bad_translation",
                    "reason": reason,
                    "source_row_id": row["source_row_id"],
                }
            )

    rng.shuffle(output_rows)
    return output_rows


def write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "source_text",
        "candidate_translation",
        "label",
        "label_text",
        "reason",
        "source_row_id",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a local good/bad translation dataset for the quality classifier.",
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--bad-per-good", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.bad_per_good < 1:
        raise ValueError("--bad-per-good must be at least 1")

    translation_rows = load_translation_rows(args.input)
    quality_rows = build_quality_rows(
        translation_rows,
        bad_per_good=args.bad_per_good,
        seed=args.seed,
    )
    write_rows(args.output, quality_rows)

    good = sum(1 for row in quality_rows if int(row["label"]) == 1)
    bad = sum(1 for row in quality_rows if int(row["label"]) == 0)
    print(f"input translation rows: {len(translation_rows)}")
    print(f"quality classifier rows: {len(quality_rows)}")
    print(f"good rows: {good}")
    print(f"bad rows: {bad}")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
