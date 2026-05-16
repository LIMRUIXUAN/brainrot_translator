from __future__ import annotations

import argparse
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from random import Random
from typing import Iterable

import pandas as pd
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.filter_training_dataset import (  # noqa: E402
    SENTENCE_TRANSLATION_PREFIX,
    TERM_DEFINITION_PREFIX,
    classify_and_repair_row,
    clean_text,
    contains_hallucination_filler,
    count_words,
    detect_text_columns,
    looks_corrupted,
    normalize_for_compare,
    repair_term_definition,
)


PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

DEFAULT_LOCAL_INPUT_PATH = PROCESSED_DIR / "slang_terms_brainrot_normal.csv"
DEFAULT_HF_INPUT_PATH = PROCESSED_DIR / "huggingface_parallel_dataset.csv"
DEFAULT_LOCAL_ONLY_OUTPUT_PATH = PROCESSED_DIR / "training_dataset_final_local_only.csv"
DEFAULT_COMBINED_OUTPUT_PATH = PROCESSED_DIR / "training_dataset_final_combined.csv"
DEFAULT_REJECTED_OUTPUT_PATH = PROCESSED_DIR / "training_dataset_rejected.csv"
DEFAULT_REPORT_OUTPUT_PATH = PROCESSED_DIR / "training_dataset_quality_report.txt"

FINAL_OUTPUT_COLUMNS = ["input_text", "target_text", "task_type", "source", "quality_label", "reason"]
REJECTED_OUTPUT_COLUMNS = FINAL_OUTPUT_COLUMNS + ["raw_input", "raw_target"]

MIN_HIGH_QUALITY_ROWS = 1000
MIN_HF_SOURCE_KEEP_RATE = 0.90
MIN_HF_SOURCE_CLEAN_ROWS = 200
MAX_HF_TO_LOCAL_RATIO = 6
DEFAULT_RANDOM_SEED = 42

LOCAL_ALIAS_SPLIT_RE = re.compile(r"\s*(?:,|/)\s*")
LOCAL_SENSITIVE_TARGET_PATTERNS = [
    re.compile(r"\bstereotypical mannerisms\b", flags=re.IGNORECASE),
]


@dataclass
class PreparedExample:
    input_text: str
    target_text: str
    task_type: str
    source: str
    quality_label: str
    reason: str
    raw_input: str
    raw_target: str
    row_index: int
    score: int
    source_group: str


@dataclass
class SourceSummary:
    source_group: str
    original_rows: int
    cleaned_rows: int
    rejected_rows: int
    duplicate_rows: int
    keep_rate: float
    accepted: bool
    note: str


@dataclass
class Recommendation:
    strategy: str
    final_dataset_path: Path
    reasons: list[str]


def safe_print(text: str = "") -> None:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    rendered = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
    print(rendered)


def ensure_directory(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_csv(dataframe: pd.DataFrame, output_path: Path) -> None:
    ensure_directory(output_path)
    dataframe.to_csv(output_path, index=False, encoding="utf-8")


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path).fillna("")


def build_prompt(task_type: str, source_text: str) -> str:
    if task_type == "sentence_translation":
        return SENTENCE_TRANSLATION_PREFIX + clean_text(source_text)
    return TERM_DEFINITION_PREFIX + clean_text(source_text)


def example_priority(example: PreparedExample) -> tuple[int, int, int, int]:
    source_bonus = 2 if example.source.startswith("local_glossary:") else 0
    keep_bonus = 1 if example.quality_label == "keep" else 0
    return (example.score + source_bonus + keep_bonus, keep_bonus, source_bonus, -example.row_index)


def reject_example(
    raw_input: str,
    raw_target: str,
    reason: str,
    row_index: int,
    source: str,
    source_group: str,
) -> PreparedExample:
    return PreparedExample(
        input_text="",
        target_text="",
        task_type="rejected",
        source=source,
        quality_label="rejected",
        reason=reason,
        raw_input=clean_text(raw_input),
        raw_target=clean_text(raw_target),
        row_index=row_index,
        score=0,
        source_group=source_group,
    )


def local_glossary_decision(
    source_text: str,
    target_text: str,
    row_index: int,
    source: str,
    source_group: str,
) -> PreparedExample:
    cleaned_source = clean_text(source_text)
    cleaned_target = clean_text(target_text)

    if not cleaned_source or not cleaned_target:
        return reject_example(cleaned_source, cleaned_target, "empty_input_or_target", row_index, source, source_group)
    if looks_corrupted(cleaned_source):
        return reject_example(cleaned_source, cleaned_target, "corrupted_text", row_index, source, source_group)
    if contains_hallucination_filler(cleaned_target):
        return reject_example(cleaned_source, cleaned_target, "hallucinated_target", row_index, source, source_group)
    if any(pattern.search(cleaned_target) for pattern in LOCAL_SENSITIVE_TARGET_PATTERNS):
        return reject_example(
            cleaned_source,
            cleaned_target,
            "sensitive_definition_manual_review",
            row_index,
            source,
            source_group,
        )

    repaired_target, quality_label, reason = repair_term_definition(cleaned_source, cleaned_target)
    if not repaired_target:
        return reject_example(cleaned_source, cleaned_target, reason, row_index, source, source_group)

    return PreparedExample(
        input_text=build_prompt("term_definition", cleaned_source),
        target_text=repaired_target,
        task_type="term_definition",
        source=source,
        quality_label=quality_label,
        reason=reason,
        raw_input=cleaned_source,
        raw_target=cleaned_target,
        row_index=row_index,
        score=110 if quality_label == "keep" else 108,
        source_group=source_group,
    )


def generic_decision(
    source_text: str,
    target_text: str,
    row_index: int,
    source: str,
    source_group: str,
) -> PreparedExample:
    decision = classify_and_repair_row(source_text, target_text, row_index)
    if decision.quality_label == "rejected":
        return reject_example(decision.raw_input, decision.raw_target, decision.reason, row_index, source, source_group)

    return PreparedExample(
        input_text=decision.input_text,
        target_text=decision.target_text,
        task_type=decision.task_type,
        source=source,
        quality_label=decision.quality_label,
        reason=decision.reason,
        raw_input=decision.raw_input,
        raw_target=decision.raw_target,
        row_index=row_index,
        score=decision.score,
        source_group=source_group,
    )


def split_local_term_variants(term_text: str) -> list[str]:
    cleaned = clean_text(term_text)
    if not cleaned:
        return []

    parts = [cleaned]
    if "," in cleaned or "/" in cleaned:
        parts = [piece.strip() for piece in LOCAL_ALIAS_SPLIT_RE.split(cleaned) if piece.strip()]

    deduped: list[str] = []
    seen: set[str] = set()
    for part in parts:
        key = normalize_for_compare(part)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(part)
    return deduped or [cleaned]


def prepare_examples_from_dataframe(
    dataframe: pd.DataFrame,
    source_group: str,
    source_builder,
    local_glossary_mode: bool = False,
) -> tuple[list[PreparedExample], list[PreparedExample]]:
    if dataframe.empty:
        return [], []

    column_selection = detect_text_columns(dataframe)
    prepared: list[PreparedExample] = []
    rejected: list[PreparedExample] = []

    for row_index, row in dataframe.iterrows():
        source_text = row[column_selection.input_column]
        target_text = row[column_selection.target_column]
        source_label = source_builder(row)

        if local_glossary_mode:
            term_variants = split_local_term_variants(source_text)
            for variant_index, variant in enumerate(term_variants):
                example = local_glossary_decision(
                    variant,
                    target_text,
                    row_index * 100 + variant_index,
                    source_label,
                    source_group,
                )
                if example.quality_label == "rejected":
                    rejected.append(example)
                else:
                    prepared.append(example)
            continue

        example = generic_decision(source_text, target_text, row_index, source_label, source_group)

        if example.quality_label == "rejected":
            rejected.append(example)
        else:
            prepared.append(example)

    return prepared, rejected


def rows_are_near_duplicates(left: PreparedExample, right: PreparedExample) -> bool:
    if left.task_type != right.task_type:
        return False
    if normalize_for_compare(left.input_text) != normalize_for_compare(right.input_text):
        return False

    left_target = normalize_for_compare(left.target_text)
    right_target = normalize_for_compare(right.target_text)
    if not left_target or not right_target:
        return False

    similarity = SequenceMatcher(None, left_target, right_target).ratio()
    return similarity >= 0.96


def deduplicate_examples(
    examples: Iterable[PreparedExample],
) -> tuple[list[PreparedExample], list[PreparedExample], int]:
    exact_lookup: dict[tuple[str, str], PreparedExample] = {}
    duplicate_rows: list[PreparedExample] = []

    for example in examples:
        key = (normalize_for_compare(example.input_text), normalize_for_compare(example.target_text))
        existing = exact_lookup.get(key)
        if existing is None:
            exact_lookup[key] = example
            continue

        preferred = max([existing, example], key=example_priority)
        duplicate = example if preferred is existing else existing
        exact_lookup[key] = preferred
        duplicate_rows.append(
            reject_example(
                duplicate.raw_input,
                duplicate.raw_target,
                "duplicate_exact_pair",
                duplicate.row_index,
                duplicate.source,
                duplicate.source_group,
            )
        )

    final_rows: list[PreparedExample] = []
    grouped_by_input: dict[str, list[PreparedExample]] = defaultdict(list)
    for example in exact_lookup.values():
        grouped_by_input[normalize_for_compare(example.input_text)].append(example)

    for input_key in sorted(grouped_by_input):
        local_kept: list[PreparedExample] = []
        for example in sorted(grouped_by_input[input_key], key=example_priority, reverse=True):
            match_index = next(
                (index for index, existing in enumerate(local_kept) if rows_are_near_duplicates(existing, example)),
                None,
            )
            if match_index is None:
                local_kept.append(example)
                continue

            existing = local_kept[match_index]
            preferred = max([existing, example], key=example_priority)
            duplicate = example if preferred is existing else existing
            local_kept[match_index] = preferred
            duplicate_rows.append(
                reject_example(
                    duplicate.raw_input,
                    duplicate.raw_target,
                    "duplicate_near_pair",
                    duplicate.row_index,
                    duplicate.source,
                    duplicate.source_group,
                )
            )

        final_rows.extend(sorted(local_kept, key=lambda item: item.row_index))

    return final_rows, duplicate_rows, len(duplicate_rows)


def examples_to_dataframe(examples: list[PreparedExample]) -> pd.DataFrame:
    rows = [
        {
            "input_text": example.input_text,
            "target_text": example.target_text,
            "task_type": example.task_type,
            "source": example.source,
            "quality_label": example.quality_label,
            "reason": example.reason,
        }
        for example in examples
    ]
    return pd.DataFrame(rows, columns=FINAL_OUTPUT_COLUMNS)


def rejected_to_dataframe(examples: list[PreparedExample]) -> pd.DataFrame:
    rows = [
        {
            "input_text": example.input_text or example.raw_input,
            "target_text": example.target_text or example.raw_target,
            "task_type": example.task_type,
            "source": example.source,
            "quality_label": example.quality_label,
            "reason": example.reason,
            "raw_input": example.raw_input,
            "raw_target": example.raw_target,
        }
        for example in examples
    ]
    return pd.DataFrame(rows, columns=REJECTED_OUTPUT_COLUMNS)


def classify_local_dataset_type(cleaned_examples: list[PreparedExample], rejected_count: int) -> str:
    if not cleaned_examples:
        return "no usable data"
    if rejected_count >= len(cleaned_examples):
        return "noisy/metadata data"

    task_counts = Counter(example.task_type for example in cleaned_examples)
    total = len(cleaned_examples)
    term_ratio = task_counts.get("term_definition", 0) / total
    sentence_ratio = task_counts.get("sentence_translation", 0) / total

    if term_ratio >= 0.70:
        return "term-definition data"
    if sentence_ratio >= 0.70:
        return "sentence-translation data"
    return "mixed data"


def target_quality_snapshot(dataframe: pd.DataFrame) -> dict[str, int]:
    text_columns = detect_text_columns(dataframe)
    target_series = dataframe[text_columns.target_column].fillna("").astype(str).map(clean_text)
    input_series = dataframe[text_columns.input_column].fillna("").astype(str).map(clean_text)

    return {
        "empty_rows": int(((input_series == "") | (target_series == "")).sum()),
        "duplicate_exact_rows": int(dataframe.duplicated().sum()),
        "very_short_inputs": int(input_series.map(count_words).le(1).sum()),
        "very_short_targets": int(target_series.map(count_words).le(2).sum()),
        "very_long_inputs": int(input_series.str.len().ge(60).sum()),
        "very_long_targets": int(target_series.str.len().ge(160).sum()),
        "corrupted_targets": int(target_series.map(looks_corrupted).sum()),
        "hallucinated_targets": int(target_series.map(contains_hallucination_filler).sum()),
    }


def random_local_example_lines(dataframe: pd.DataFrame, random_seed: int, limit: int = 20) -> list[str]:
    sample = dataframe.sample(n=min(limit, len(dataframe)), random_state=random_seed).reset_index(drop=True)
    column_selection = detect_text_columns(sample)
    lines: list[str] = []

    for index, row in sample.iterrows():
        decision = local_glossary_decision(
            row[column_selection.input_column],
            row[column_selection.target_column],
            index,
            "local_glossary:slang_terms_brainrot_normal.csv",
            "local_glossary",
        )
        classification = decision.task_type if decision.quality_label != "rejected" else f"rejected ({decision.reason})"
        lines.append(
            f"{index + 1:02d}. [{classification}] "
            f"brainrot={clean_text(row[column_selection.input_column])} | "
            f"normal={clean_text(row[column_selection.target_column])}"
        )
    return lines


def build_local_analysis(
    raw_dataframe: pd.DataFrame,
    cleaned_examples: list[PreparedExample],
    rejected_examples: list[PreparedExample],
    random_seed: int,
) -> list[str]:
    quality = target_quality_snapshot(raw_dataframe)
    dataset_type = classify_local_dataset_type(cleaned_examples, len(rejected_examples))
    lines = [
        "Local dataset analysis",
        f"- Column names: {list(raw_dataframe.columns)}",
        f"- Row count: {len(raw_dataframe)}",
        f"- Dataset type: {dataset_type}",
        f"- Usable FLAN-T5 rows after source-aware cleaning: {len(cleaned_examples)}",
        f"- Rejected rows after source-aware cleaning: {len(rejected_examples)}",
        f"- Task counts: {Counter(example.task_type for example in cleaned_examples)}",
        "- Quality snapshot:",
        f"  empty rows={quality['empty_rows']}",
        f"  exact duplicate rows={quality['duplicate_exact_rows']}",
        f"  very short inputs={quality['very_short_inputs']}",
        f"  very short targets={quality['very_short_targets']}",
        f"  very long inputs={quality['very_long_inputs']}",
        f"  very long targets={quality['very_long_targets']}",
        f"  corrupted targets={quality['corrupted_targets']}",
        f"  hallucinated targets={quality['hallucinated_targets']}",
        "- 20 random local examples with classification:",
    ]
    lines.extend(f"  {line}" for line in random_local_example_lines(raw_dataframe, random_seed=random_seed, limit=20))
    return lines


def summarise_source(cleaned_count: int, rejected_count: int, duplicates: int, original_rows: int, accepted: bool, note: str, source_group: str) -> SourceSummary:
    keep_rate = cleaned_count / original_rows if original_rows else 0.0
    return SourceSummary(
        source_group=source_group,
        original_rows=original_rows,
        cleaned_rows=cleaned_count,
        rejected_rows=rejected_count,
        duplicate_rows=duplicates,
        keep_rate=keep_rate,
        accepted=accepted,
        note=note,
    )


def build_hf_examples(
    raw_dataframe: pd.DataFrame,
    min_keep_rate: float,
    min_clean_rows: int,
) -> tuple[list[PreparedExample], list[PreparedExample], list[SourceSummary]]:
    accepted_examples: list[PreparedExample] = []
    rejected_examples: list[PreparedExample] = []
    source_summaries: list[SourceSummary] = []

    if raw_dataframe.empty:
        return accepted_examples, rejected_examples, source_summaries

    if "source_dataset" not in raw_dataframe.columns:
        prepared, rejected = prepare_examples_from_dataframe(
            raw_dataframe,
            source_group="hf_parallel",
            source_builder=lambda _: "hf_parallel:unknown",
        )
        deduped, duplicate_rows, duplicate_count = deduplicate_examples(prepared)
        accepted_examples.extend(deduped)
        rejected_examples.extend(rejected)
        rejected_examples.extend(duplicate_rows)
        source_summaries.append(
            summarise_source(
                cleaned_count=len(deduped),
                rejected_count=len(rejected) + duplicate_count,
                duplicates=duplicate_count,
                original_rows=len(raw_dataframe),
                accepted=True,
                note="No source_dataset column was available, so the file was treated as one source.",
                source_group="hf_parallel",
            )
        )
        return accepted_examples, rejected_examples, source_summaries

    for source_dataset, source_frame in raw_dataframe.groupby("source_dataset", dropna=False):
        source_group = f"hf_parallel::{source_dataset}"
        prepared, rejected = prepare_examples_from_dataframe(
            source_frame.reset_index(drop=True),
            source_group=source_group,
            source_builder=lambda row: f"hf_parallel:{row.get('source_dataset', 'unknown')}",
        )
        deduped, duplicate_rows, duplicate_count = deduplicate_examples(prepared)

        keep_rate = len(deduped) / len(source_frame) if len(source_frame) else 0.0
        accepted = keep_rate >= min_keep_rate and len(deduped) >= min_clean_rows

        if accepted:
            accepted_examples.extend(deduped)
            rejected_examples.extend(rejected)
            rejected_examples.extend(duplicate_rows)
            note = "Accepted for final pooling."
        else:
            note = "Excluded because the cleaned keep rate or usable row count was too low."
            rejected_examples.extend(rejected)
            rejected_examples.extend(duplicate_rows)
            rejected_examples.extend(
                reject_example(
                    example.raw_input,
                    example.raw_target,
                    "source_excluded_low_keep_rate",
                    example.row_index,
                    example.source,
                    example.source_group,
                )
                for example in deduped
            )

        source_summaries.append(
            summarise_source(
                cleaned_count=len(deduped),
                rejected_count=len(rejected) + duplicate_count,
                duplicates=duplicate_count,
                original_rows=len(source_frame),
                accepted=accepted,
                note=note,
                source_group=source_group,
            )
        )

    return accepted_examples, rejected_examples, source_summaries


def hf_length_bucket(example: PreparedExample) -> str:
    words = count_words(example.raw_input or example.input_text)
    if words <= 5:
        return "short"
    if words <= 10:
        return "medium"
    return "long"


def proportional_counts(total: int, group_sizes: dict[str, int]) -> dict[str, int]:
    if total <= 0 or not group_sizes:
        return {group: 0 for group in group_sizes}

    total_available = sum(group_sizes.values())
    if total_available <= total:
        return dict(group_sizes)

    raw_counts = {group: (size / total_available) * total for group, size in group_sizes.items()}
    floor_counts = {group: min(group_sizes[group], int(math.floor(raw_count))) for group, raw_count in raw_counts.items()}
    assigned = sum(floor_counts.values())

    ranked_remainders = sorted(
        (
            raw_counts[group] - floor_counts[group],
            group_sizes[group],
            group,
        )
        for group in group_sizes
    )

    while assigned < total and ranked_remainders:
        _, _, group = ranked_remainders.pop()
        if floor_counts[group] >= group_sizes[group]:
            continue
        floor_counts[group] += 1
        assigned += 1

    return floor_counts


def sample_hf_examples_for_final_dataset(
    hf_examples: list[PreparedExample],
    local_count: int,
    random_seed: int,
    min_high_quality_rows: int = MIN_HIGH_QUALITY_ROWS,
    max_hf_to_local_ratio: int = MAX_HF_TO_LOCAL_RATIO,
) -> tuple[list[PreparedExample], list[str]]:
    notes: list[str] = []
    if not hf_examples:
        return [], ["No acceptable Hugging Face rows were available."]

    if local_count >= min_high_quality_rows:
        return [], ["Local dataset already meets the minimum row target."]

    preferred_hf_rows = max(min_high_quality_rows - local_count, 0)
    max_ratio_rows = local_count * max_hf_to_local_ratio if local_count > 0 else preferred_hf_rows

    if local_count > 0 and preferred_hf_rows <= max_ratio_rows:
        target_hf_rows = preferred_hf_rows
        notes.append(
            f"Sampled {target_hf_rows} Hugging Face rows to reach {min_high_quality_rows} total rows without exceeding the {max_hf_to_local_ratio}:1 source ratio."
        )
    else:
        target_hf_rows = min(len(hf_examples), max(preferred_hf_rows, max_ratio_rows))
        notes.append(
            "The local dataset was too small to satisfy both the 1,000-row minimum and a tighter source ratio, so the script prioritized reaching the minimum total rows."
        )

    if target_hf_rows >= len(hf_examples):
        notes.append("All acceptable Hugging Face rows were kept after cleaning.")
        return list(hf_examples), notes

    grouped: dict[str, list[PreparedExample]] = defaultdict(list)
    for example in hf_examples:
        group_key = f"{example.source_group}|{hf_length_bucket(example)}"
        grouped[group_key].append(example)

    group_sizes = {group: len(items) for group, items in grouped.items()}
    quotas = proportional_counts(target_hf_rows, group_sizes)

    rng = Random(random_seed)
    sampled: list[PreparedExample] = []
    for group_key, items in grouped.items():
        quota = quotas[group_key]
        if quota <= 0:
            continue
        ordered = sorted(items, key=lambda item: (item.score, item.input_text, item.target_text), reverse=True)
        selected = ordered[:quota]
        if len(selected) < quota:
            remaining = [item for item in items if item not in selected]
            rng.shuffle(remaining)
            selected.extend(remaining[: quota - len(selected)])
        sampled.extend(selected)

    sampled = sorted(sampled, key=lambda item: (item.task_type, item.source, item.input_text, item.target_text))
    notes.append(f"Final Hugging Face sample size: {len(sampled)} rows.")
    return sampled, notes


def recommend_dataset_strategy(
    local_examples: list[PreparedExample],
    hf_examples: list[PreparedExample],
) -> Recommendation:
    local_count = len(local_examples)
    local_task_counts = Counter(example.task_type for example in local_examples)
    local_term_ratio = (local_task_counts.get("term_definition", 0) / local_count) if local_count else 0.0

    reasons: list[str] = []
    if local_count < MIN_HIGH_QUALITY_ROWS:
        reasons.append(f"Local dataset has only {local_count} usable rows after cleaning, which is below the 1,000-row minimum.")
    if local_term_ratio >= 0.60:
        reasons.append("Local dataset is mostly term-definition data, so it does not provide enough sentence-level translation coverage.")

    if local_count >= MIN_HIGH_QUALITY_ROWS and local_term_ratio < 0.60:
        return Recommendation(
            strategy="Use local-only dataset",
            final_dataset_path=DEFAULT_LOCAL_ONLY_OUTPUT_PATH,
            reasons=["Local dataset already meets the size target and has enough task diversity."],
        )

    if hf_examples:
        reasons.append("Cleaned Hugging Face parallel data adds high-quality sentence translation pairs after filtering.")
        return Recommendation(
            strategy="Use combined dataset",
            final_dataset_path=DEFAULT_COMBINED_OUTPUT_PATH,
            reasons=reasons,
        )

    reasons.append("No acceptable Hugging Face rows passed the cleaning filters, so local-only is the safest fallback.")
    return Recommendation(
        strategy="Use local-only dataset",
        final_dataset_path=DEFAULT_LOCAL_ONLY_OUTPUT_PATH,
        reasons=reasons,
    )


def build_quality_report(
    local_analysis_lines: list[str],
    hf_summaries: list[SourceSummary],
    recommendation: Recommendation,
    local_final_count: int,
    hf_final_count: int,
    rejected_count: int,
    final_dataset_path: Path,
    rejected_output_path: Path,
) -> str:
    lines = list(local_analysis_lines)
    lines.append("")
    lines.append("Hugging Face source analysis")
    if hf_summaries:
        for summary in sorted(hf_summaries, key=lambda item: item.source_group):
            lines.append(
                "- "
                f"{summary.source_group}: original_rows={summary.original_rows}, "
                f"cleaned_rows={summary.cleaned_rows}, rejected_rows={summary.rejected_rows}, "
                f"duplicates={summary.duplicate_rows}, keep_rate={summary.keep_rate:.3f}, "
                f"accepted={summary.accepted}, note={summary.note}"
            )
    else:
        lines.append("- No Hugging Face file was evaluated.")

    lines.append("")
    lines.append("Recommendation")
    lines.append(f"- Strategy: {recommendation.strategy}")
    for reason in recommendation.reasons:
        lines.append(f"- Reason: {reason}")

    lines.append("")
    lines.append("Final dataset outputs")
    lines.append(f"- Final local rows kept: {local_final_count}")
    lines.append(f"- Final Hugging Face rows kept: {hf_final_count}")
    lines.append(f"- Final dataset row count: {local_final_count + hf_final_count}")
    lines.append(f"- Final dataset path: {final_dataset_path}")
    lines.append(f"- Rejected dataset path: {rejected_output_path}")
    lines.append(f"- Rejected row count: {rejected_count}")

    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare a cleaned FLAN-T5 training dataset for the brainrot translator."
    )
    parser.add_argument("--local-input", type=Path, default=DEFAULT_LOCAL_INPUT_PATH, help="Local glossary CSV to inspect first.")
    parser.add_argument("--hf-input", type=Path, default=DEFAULT_HF_INPUT_PATH, help="Optional Hugging Face-derived CSV with sentence pairs.")
    parser.add_argument("--use-hf", dest="use_hf", action="store_true", default=True, help="Include the Hugging Face CSV when available.")
    parser.add_argument("--no-hf", dest="use_hf", action="store_false", help="Skip the Hugging Face CSV and build only the local dataset.")
    parser.add_argument("--local-only-output", type=Path, default=DEFAULT_LOCAL_ONLY_OUTPUT_PATH, help="Output CSV for the cleaned local-only dataset.")
    parser.add_argument("--combined-output", type=Path, default=DEFAULT_COMBINED_OUTPUT_PATH, help="Output CSV for the cleaned combined dataset.")
    parser.add_argument("--rejected-output", type=Path, default=DEFAULT_REJECTED_OUTPUT_PATH, help="Output CSV for rejected rows.")
    parser.add_argument("--report-output", type=Path, default=DEFAULT_REPORT_OUTPUT_PATH, help="Output text report with the dataset recommendation.")
    parser.add_argument("--min-high-quality-rows", type=int, default=MIN_HIGH_QUALITY_ROWS, help="Minimum number of usable rows to target.")
    parser.add_argument("--min-hf-source-keep-rate", type=float, default=MIN_HF_SOURCE_KEEP_RATE, help="Minimum cleaned keep rate for each Hugging Face source.")
    parser.add_argument("--min-hf-source-clean-rows", type=int, default=MIN_HF_SOURCE_CLEAN_ROWS, help="Minimum usable cleaned rows required for each Hugging Face source.")
    parser.add_argument("--max-hf-to-local-ratio", type=int, default=MAX_HF_TO_LOCAL_RATIO, help="Maximum preferred ratio of Hugging Face rows to local rows.")
    parser.add_argument("--random-seed", type=int, default=DEFAULT_RANDOM_SEED, help="Random seed used for sampling and report examples.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    local_raw = read_csv(args.local_input)
    local_prepared, local_rejected = prepare_examples_from_dataframe(
        local_raw,
        source_group="local_glossary",
        source_builder=lambda _: "local_glossary:slang_terms_brainrot_normal.csv",
        local_glossary_mode=True,
    )
    local_cleaned, local_duplicate_rows, _ = deduplicate_examples(local_prepared)
    local_rejected.extend(local_duplicate_rows)

    write_csv(examples_to_dataframe(local_cleaned), args.local_only_output)

    hf_cleaned: list[PreparedExample] = []
    hf_rejected: list[PreparedExample] = []
    hf_summaries: list[SourceSummary] = []

    if args.use_hf and args.hf_input.exists():
        hf_raw = read_csv(args.hf_input)
        hf_candidate_examples, hf_rejected, hf_summaries = build_hf_examples(
            hf_raw,
            min_keep_rate=args.min_hf_source_keep_rate,
            min_clean_rows=args.min_hf_source_clean_rows,
        )
        hf_cleaned, cross_source_duplicate_rows, _ = deduplicate_examples(hf_candidate_examples)
        hf_rejected.extend(cross_source_duplicate_rows)
    elif args.use_hf:
        hf_rejected.append(
            reject_example(
                raw_input="",
                raw_target="",
                reason="hf_input_missing",
                row_index=0,
                source=f"hf_parallel:{args.hf_input}",
                source_group="hf_parallel",
            )
        )

    recommendation = recommend_dataset_strategy(local_cleaned, hf_cleaned)

    selected_hf_examples: list[PreparedExample] = []
    hf_sampling_notes: list[str] = []
    if recommendation.strategy == "Use combined dataset":
        selected_hf_examples, hf_sampling_notes = sample_hf_examples_for_final_dataset(
            hf_examples=hf_cleaned,
            local_count=len(local_cleaned),
            random_seed=args.random_seed,
            min_high_quality_rows=args.min_high_quality_rows,
            max_hf_to_local_ratio=args.max_hf_to_local_ratio,
        )

    final_examples = list(local_cleaned)
    final_examples.extend(selected_hf_examples)
    final_examples = sorted(final_examples, key=lambda item: (item.task_type, item.source, item.input_text, item.target_text))

    final_dataset_path = args.local_only_output if recommendation.strategy == "Use local-only dataset" else args.combined_output
    write_csv(examples_to_dataframe(final_examples), final_dataset_path)

    rejected_examples = sorted(local_rejected + hf_rejected, key=lambda item: (item.reason, item.source, item.row_index))
    write_csv(rejected_to_dataframe(rejected_examples), args.rejected_output)

    local_analysis_lines = build_local_analysis(
        raw_dataframe=local_raw,
        cleaned_examples=local_cleaned,
        rejected_examples=local_rejected,
        random_seed=args.random_seed,
    )

    if hf_sampling_notes:
        local_analysis_lines.append("")
        local_analysis_lines.append("Sampling notes")
        local_analysis_lines.extend(f"- {note}" for note in hf_sampling_notes)

    report_text = build_quality_report(
        local_analysis_lines=local_analysis_lines,
        hf_summaries=hf_summaries,
        recommendation=recommendation,
        local_final_count=len(local_cleaned),
        hf_final_count=len(selected_hf_examples),
        rejected_count=len(rejected_examples),
        final_dataset_path=final_dataset_path,
        rejected_output_path=args.rejected_output,
    )
    ensure_directory(args.report_output)
    args.report_output.write_text(report_text, encoding="utf-8")

    safe_print(f"Recommendation: {recommendation.strategy}")
    for reason in recommendation.reasons:
        safe_print(f"- {reason}")
    for note in hf_sampling_notes:
        safe_print(f"- {note}")
    safe_print(f"Final dataset path: {final_dataset_path}")
    safe_print(f"Rejected dataset path: {args.rejected_output}")
    safe_print(f"Quality report path: {args.report_output}")


if __name__ == "__main__":
    main()
