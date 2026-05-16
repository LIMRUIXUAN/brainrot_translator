from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_PATH = PROJECT_ROOT / "data" / "processed" / "slang_terms.csv"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "slang_terms_brainrot_normal.csv"

OUTPUT_COLUMNS = ["brainrot", "normal"]
SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?])(?:["\']+)?\s+')
MULTI_SENSE_RE = re.compile(r"\(\s*\d+\s*\)|\b\d+\.\)")

MEANING_PREFIX_REWRITES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^refers to\s+", flags=re.IGNORECASE), ""),
    (re.compile(r"^used to express\s+", flags=re.IGNORECASE), "an expression of "),
    (re.compile(r"^used to describe\s+", flags=re.IGNORECASE), ""),
    (re.compile(r"^used in reference to\s+", flags=re.IGNORECASE), ""),
    (re.compile(r"^used as an insult to\s+", flags=re.IGNORECASE), "an insult used to describe "),
    (re.compile(r"^shortened version of\s+", flags=re.IGNORECASE), ""),
    (re.compile(r"^a variant of the word\s+", flags=re.IGNORECASE), ""),
    (re.compile(r"^a variant of\s+", flags=re.IGNORECASE), ""),
    (re.compile(r"^pertaining to those who\s+", flags=re.IGNORECASE), "people who prefer "),
    (re.compile(r"^commonly used to mean\s+", flags=re.IGNORECASE), ""),
    (re.compile(r"^effectively\s+", flags=re.IGNORECASE), ""),
    (re.compile(r"^more contemporary use has been to express\s+", flags=re.IGNORECASE), ""),
]

META_SENTENCE_PATTERNS = [
    re.compile(r"\boriginated from\b", flags=re.IGNORECASE),
    re.compile(r"\boriginating from\b", flags=re.IGNORECASE),
    re.compile(r"\bderived from\b", flags=re.IGNORECASE),
    re.compile(r"\bpopularized by\b", flags=re.IGNORECASE),
    re.compile(r"\bcoined and popularized\b", flags=re.IGNORECASE),
    re.compile(r"\boften associated with\b", flags=re.IGNORECASE),
    re.compile(r"\balternative forms include\b", flags=re.IGNORECASE),
    re.compile(r"\binspired multiple\b", flags=re.IGNORECASE),
    re.compile(r"\bthe term has its roots\b", flags=re.IGNORECASE),
]

MEANING_CUE_PATTERNS = [
    re.compile(r"^a\b", flags=re.IGNORECASE),
    re.compile(r"^an\b", flags=re.IGNORECASE),
    re.compile(r"^the state of\b", flags=re.IGNORECASE),
    re.compile(r"^to\b", flags=re.IGNORECASE),
    re.compile(r"^refers to\b", flags=re.IGNORECASE),
    re.compile(r"^used to\b", flags=re.IGNORECASE),
    re.compile(r"^abbreviation for\b", flags=re.IGNORECASE),
    re.compile(r"^acronym for\b", flags=re.IGNORECASE),
    re.compile(r"^short for\b", flags=re.IGNORECASE),
    re.compile(r"^shortened version of\b", flags=re.IGNORECASE),
    re.compile(r"^a variant of\b", flags=re.IGNORECASE),
    re.compile(r"^more contemporary use has been to express\b", flags=re.IGNORECASE),
]

PART_OF_SPEECH_SUFFIX_RE = re.compile(r"\s+\((?:verb|adjective|noun|phrase|interjection)\)\s*$", flags=re.IGNORECASE)


def clean_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\s+", " ", text)
    text = text.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    return text.strip()


def split_sentences(text: str) -> list[str]:
    cleaned = clean_text(text)
    if not cleaned:
        return []
    return [sentence.strip() for sentence in SENTENCE_SPLIT_RE.split(cleaned) if sentence.strip()]


def normalize_term(term: str) -> str:
    cleaned = clean_text(term)
    if not cleaned:
        return ""
    cleaned = PART_OF_SPEECH_SUFFIX_RE.sub("", cleaned)
    return cleaned.strip()


def split_term_variants(term: str) -> list[str]:
    cleaned = normalize_term(term)
    if not cleaned:
        return []

    variants = [cleaned]
    if "/" in cleaned:
        for part in cleaned.split("/"):
            piece = clean_text(part)
            if piece:
                variants.append(piece)
    return dedupe_preserve_order(variants)


def sentence_score(sentence: str) -> int:
    cleaned = clean_text(sentence)
    lowered = cleaned.casefold()
    score = 0

    if any(pattern.search(cleaned) for pattern in MEANING_CUE_PATTERNS):
        score += 4
    if any(pattern.search(cleaned) for pattern in META_SENTENCE_PATTERNS):
        score -= 3
    if "similar to" in lowered or "equivalent to" in lowered:
        score -= 1
    if len(cleaned) > 180:
        score -= 1
    return score


def simplify_meaning_sentence(sentence: str) -> str:
    cleaned = clean_text(sentence).strip().strip(".")

    short_for_two_match = re.match(
        r'^short for\s+"([^"]+)"\s+or\s+"([^"]+)"\s*$',
        cleaned,
        flags=re.IGNORECASE,
    )
    if short_for_two_match:
        left = clean_text(short_for_two_match.group(1))
        right = clean_text(short_for_two_match.group(2))
        if left.lower().startswith("i am ") and right.lower().startswith("i am "):
            left = left[5:]
            right = right[5:]
        return f"{left} or {right}".strip()

    short_for_one_match = re.match(r'^short for\s+"([^"]+)"\s*$', cleaned, flags=re.IGNORECASE)
    if short_for_one_match:
        return clean_text(short_for_one_match.group(1))

    for pattern, replacement in MEANING_PREFIX_REWRITES:
        cleaned = pattern.sub(replacement, cleaned, count=1)

    abbreviation_match = re.match(
        r'^abbreviation for\s+"([^"]+)"\s*:\s*(.+)$',
        cleaned,
        flags=re.IGNORECASE,
    )
    if abbreviation_match:
        return clean_text(abbreviation_match.group(2))

    acronym_match = re.match(
        r'^acronym for\s+"([^"]+)"\s*\.?\s*$',
        cleaned,
        flags=re.IGNORECASE,
    )
    if acronym_match:
        return clean_text(acronym_match.group(1))

    cleaned = re.sub(r'^abbreviation for\s+"([^"]+)"\s*$', r"\1", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'^acronym for\s+"([^"]+)"\s*$', r"\1", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'^to\s+"?be\s+[^"]+"?\s+is\s+to\s+be\s+(.+)$', r"to be \1", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'^to\s+"?cook"?\s+is\s+to\s+(.+)$', r"to \1", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^to have\s+", "to ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*;\s*", ", ", cleaned)
    cleaned = cleaned.replace(" or/ ", " or ")
    cleaned = cleaned.replace(" / ", " or ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if cleaned.lower().startswith("extremely good, excellent"):
        cleaned = "extremely good or excellent"
    if cleaned.lower().startswith("agreeing to something, yes, okay, sure"):
        cleaned = "yes, okay, or sure"
    if cleaned.lower().startswith("one's charm/ seduction skills"):
        cleaned = "charisma or flirting ability"
    if cleaned.lower().startswith("one's charm or seduction skills"):
        cleaned = "charisma or flirting ability"
    cleaned = cleaned.replace("agreeing with another's opinion", "agreement with another's opinion")
    if cleaned.lower().startswith("short for "):
        cleaned = cleaned[10:]

    if cleaned and re.match(r"^(A|An|The)\b", cleaned):
        cleaned = cleaned[0].lower() + cleaned[1:]
    elif cleaned and re.match(r"^[A-Z][a-z]", cleaned):
        cleaned = cleaned[0].lower() + cleaned[1:]

    return cleaned.strip(" .")


def choose_base_meaning(meaning: str) -> str | None:
    cleaned_meaning = clean_text(meaning)
    if not cleaned_meaning:
        return None
    if MULTI_SENSE_RE.search(cleaned_meaning):
        return None

    sentences = split_sentences(cleaned_meaning)
    if not sentences:
        return None

    best_sentence = max(sentences, key=sentence_score)
    simplified = simplify_meaning_sentence(best_sentence)
    if not simplified:
        return None
    return simplified


def extract_variants_from_meaning(term: str, meaning: str) -> list[str]:
    variants = split_term_variants(term)

    for sentence in split_sentences(meaning):
        lowered = sentence.casefold()
        should_extract = any(
            phrase in lowered
            for phrase in (
                "alternative forms include",
                "may be said to",
                "or be",
                "shortened to just",
                "often used in the phrase",
                "often used in phrases like",
            )
        )
        if not should_extract:
            continue

        for variant in re.findall(r'"([^"]+)"', sentence):
            piece = clean_text(variant)
            if not piece:
                continue
            if len(piece.split()) > 6:
                continue
            if piece.lower() in {"i'm crying", "dying of laughter"}:
                continue
            variants.append(piece)

    return dedupe_preserve_order(variants)


def dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = clean_text(value)
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


def build_pairs(dataframe: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    rows: list[dict[str, str]] = []
    source_rows = 0
    skipped_multi_sense = 0
    skipped_empty = 0

    for row in dataframe.fillna("").to_dict(orient="records"):
        source_rows += 1
        term = clean_text(row.get("term", ""))
        meaning = clean_text(row.get("meaning", ""))
        if not term or not meaning:
            skipped_empty += 1
            continue

        base_meaning = choose_base_meaning(meaning)
        if not base_meaning:
            skipped_multi_sense += 1
            continue

        for variant in extract_variants_from_meaning(term, meaning):
            rows.append({"brainrot": variant, "normal": base_meaning})

    pairs = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    if not pairs.empty:
        pairs = pairs.drop_duplicates(subset=OUTPUT_COLUMNS).sort_values(["brainrot", "normal"]).reset_index(drop=True)

    summary = {
        "source_rows": source_rows,
        "output_rows": len(pairs),
        "skipped_multi_sense_or_unusable": skipped_multi_sense,
        "skipped_empty": skipped_empty,
    }
    return pairs, summary


def write_output(dataframe: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix.lower() == ".xlsx":
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            dataframe.to_excel(writer, index=False, sheet_name="slang_pairs")
        return
    dataframe.to_csv(output_path, index=False, encoding="utf-8")


def safe_print(text: str = "") -> None:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    display_text = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
    print(display_text)


def print_summary(output_path: Path, dataframe: pd.DataFrame, summary: dict[str, int]) -> None:
    safe_print(f"Source rows: {summary['source_rows']}")
    safe_print(f"Output rows: {summary['output_rows']}")
    safe_print(f"Skipped multi-sense or unusable rows: {summary['skipped_multi_sense_or_unusable']}")
    safe_print(f"Skipped empty rows: {summary['skipped_empty']}")
    safe_print(f"Saved: {output_path}")
    safe_print()
    safe_print("Sample rows")
    if dataframe.empty:
        safe_print("- none")
        return
    for _, row in dataframe.head(15).iterrows():
        safe_print(f"- {row['brainrot']} -> {row['normal']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export slang_terms.csv into a CSV or XLSX file with brainrot and normal columns."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH, help="Input slang_terms CSV.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH, help="Output CSV or XLSX path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataframe = pd.read_csv(args.input)
    pairs, summary = build_pairs(dataframe)
    write_output(pairs, args.output)
    print_summary(args.output, pairs, summary)


if __name__ == "__main__":
    main()
