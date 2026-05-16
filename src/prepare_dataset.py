from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
ANALYSIS_DIR = PROJECT_ROOT / "data" / "analysis"
TRAINING_DATASET_PATH = PROCESSED_DIR / "brainrot_dataset.csv"
TRAINING_DATASET_CLEAN_PATH = PROCESSED_DIR / "brainrot_dataset_cleaned.csv"
TRAINING_READY_DATASET_PATH = PROCESSED_DIR / "brainrot_dataset_training_ready.csv"
REPORT_PATH = ANALYSIS_DIR / "dataset_report.md"
FLAGGED_BAD_PAIRS_PATH = ANALYSIS_DIR / "flagged_bad_pairs.csv"
TRAINING_READY_REVIEW_PATH = ANALYSIS_DIR / "training_ready_review.csv"

SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".json", ".txt", ".md"}
MAX_BRAINROT_LENGTH = 280
MAX_NORMAL_LENGTH = 500
MAX_GLOSSARY_NORMAL_LENGTH = 1200
DEFAULT_MAX_NORMAL_WORDS = 45
STRICT_MAX_NORMAL_WORDS = 35
DEFAULT_LENGTH_RATIO_LIMIT = 3.25
STRICT_LENGTH_RATIO_LIMIT = 2.5
RANDOM_SEED = 42

INPUT_COLUMN_CANDIDATES = [
    "brainrot",
    "slang",
    "slang_text",
    "input",
    "source",
    "original",
    "sentence",
    "phrase",
    "term",
    "example",
    "reply",
    "informal",
    "meme_text",
    "text",
    "comment",
    "content",
]

OUTPUT_COLUMN_CANDIDATES = [
    "normal",
    "meaning",
    "translation",
    "target",
    "output",
    "explanation",
    "standard",
    "standard_text",
    "formal",
    "rewritten",
    "normalized",
    "definition",
    "clean",
    "response",
]

TERM_COLUMN_CANDIDATES = ["term", "slang", "phrase", "brainrot"]
MEANING_COLUMN_CANDIDATES = ["meaning", "definition", "translation", "explanation", "normal"]
EXAMPLE_COLUMN_CANDIDATES = ["example", "sentence", "usage", "reply", "comment", "content", "text"]
METADATA_LIKE_COLUMNS = {
    "source",
    "source_url",
    "source_file",
    "category",
    "split",
    "role",
    "context",
    "collected_at",
}

SUPPLEMENTAL_SEED_FILE_GROUPS = {
    "wikipedia_seed": [
        PROCESSED_DIR / "slang_terms.csv",
        PROCESSED_DIR / "slang_terms.json",
    ],
    "parallel_seed": [
        PROCESSED_DIR / "huggingface_parallel_dataset.csv",
        PROCESSED_DIR / "huggingface_parallel_dataset.json",
    ],
}

QUOTE_TRANSLATION_TABLE = str.maketrans(
    {
        "“": '"',
        "”": '"',
        "„": '"',
        "‟": '"',
        "’": "'",
        "‘": "'",
        "‚": "'",
        "`": "'",
        "\u00a0": " ",
    }
)

WORD_RE = re.compile(r"[A-Za-z0-9']+")

QUALITY_STOPWORDS = {
    "a",
    "about",
    "above",
    "after",
    "again",
    "against",
    "all",
    "am",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "because",
    "been",
    "before",
    "being",
    "below",
    "between",
    "both",
    "but",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "doing",
    "down",
    "during",
    "each",
    "few",
    "for",
    "from",
    "further",
    "had",
    "has",
    "have",
    "having",
    "he",
    "her",
    "here",
    "hers",
    "herself",
    "him",
    "himself",
    "his",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "itself",
    "just",
    "me",
    "more",
    "most",
    "my",
    "myself",
    "no",
    "nor",
    "not",
    "of",
    "off",
    "on",
    "once",
    "only",
    "or",
    "other",
    "our",
    "ours",
    "ourselves",
    "out",
    "over",
    "own",
    "same",
    "she",
    "should",
    "so",
    "some",
    "such",
    "than",
    "that",
    "the",
    "their",
    "theirs",
    "them",
    "themselves",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "to",
    "too",
    "under",
    "until",
    "up",
    "very",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "while",
    "who",
    "whom",
    "why",
    "will",
    "with",
    "would",
    "you",
    "your",
    "yours",
    "yourself",
    "yourselves",
    "actually",
    "af",
    "bro",
    "bruh",
    "cap",
    "definitely",
    "fr",
    "frfr",
    "god",
    "gonna",
    "gotta",
    "highkey",
    "honestly",
    "just",
    "kinda",
    "like",
    "literally",
    "lmfao",
    "lmao",
    "lowkey",
    "maybe",
    "mega",
    "ngl",
    "pls",
    "please",
    "really",
    "rn",
    "shi",
    "shit",
    "sorta",
    "super",
    "tho",
    "though",
    "type",
    "vibes",
    "wanna",
    "yall",
}

IRREGULAR_KEYWORD_NORMALIZATION = {
    "burned": "burn",
    "burnt": "burn",
    "cleaning": "clean",
    "forgot": "forget",
    "forgotten": "forget",
    "forgetting": "forget",
    "keys": "key",
    "liked": "like",
    "likes": "like",
    "messier": "messy",
    "replied": "reply",
    "replying": "reply",
    "sunburned": "sunburn",
    "sunburnt": "sunburn",
    "texts": "text",
    "told": "tell",
    "worse": "bad",
}

HALLUCINATION_FILLER_PHRASES = [
    "without exaggeration",
    "i was genuinely pleased to see that",
    "i was struck by the fact that",
    "i couldn't help but notice that",
    "one has to appreciate that",
    "looking at the situation",
    "it struck me that",
    "it's remarkable how",
    "the overall quality was noticeably high",
    "i certainly wasn't expecting that outcome",
    "definitely something worth recognizing",
    "overall quality",
    "remarkable how i",
    "i could tell real thought went into it",
    "i found myself genuinely impressed by the result",
    "genuinely impressed by the result",
    "genuinely quite memorable",
    "everything came together remarkably well",
    "that level of quality is hard to come by",
    "i was pleasantly surprised by the overall quality",
    "the execution was particularly impressive",
    "what really stood out was",
    "it bears mentioning that",
    "to be perfectly honest",
    "in all honesty",
    "i think it's fair to say that",
    "frankly speaking",
    "from what i can tell",
    "i must admit",
    "i have to give credit where it's due",
    "which really says a lot about the effort involved",
    "the attention to detail was especially noteworthy",
    "the level of effort was clearly substantial",
    "the effort seemed clearly insufficient",
    "the situation was rather unfortunate",
    "there was a clear sense of dedication behind it",
    "it far exceeded what i had anticipated",
    "it's not often you encounter something that stands out like that",
    "and i think that speaks volumes",
    "in my assessment",
    "it's worth noting that",
    "it should be acknowledged that",
    "the kind of thing that stays with you for a while",
    "it genuinely struck me that",
    "which was honestly quite remarkable",
]

DEFINITION_SUBSTITUTION_PHRASES = [
    "this happens after someone",
    "my two cents worth",
    "a woman i deeply admire",
    "young man with internet-influenced alternative style",
    "someone who embarrassed themselves",
    "someone without independent thought",
    "someone with outdated views",
    "someone seeking attention by claiming uniqueness",
    "throw forcefully",
    "crying your eyes out",
]

VALID_SHORT_SLANG_TERMS = {
    "aura",
    "based",
    "bet",
    "bffr",
    "bussin",
    "cap",
    "cook",
    "cooked",
    "delulu",
    "finna",
    "gas",
    "goated",
    "gyatt",
    "joever",
    "l",
    "mid",
    "mog",
    "moots",
    "npc",
    "opp",
    "rizz",
    "sigma",
    "slay",
    "sus",
    "tuff",
    "w",
}

DOUBLE_DETERMINER_RE = re.compile(
    r"\b(?:a|an|the|my|your|his|her|our|their)\s+"
    r"(?:a|an|the|my|your|his|her|our|their)\b",
    flags=re.IGNORECASE,
)
A_SOMEONE_RE = re.compile(r"\b(?:a|an)\s+someone\b", flags=re.IGNORECASE)
MALFORMED_INFLECTION_PATTERNS = [
    re.compile(r"\b\w+lyed\b", flags=re.IGNORECASE),
    re.compile(r"\b\w+(?:ize|ise)ged\b", flags=re.IGNORECASE),
]
MULTI_SENSE_GLOSSARY_RE = re.compile(r"\(\s*[1-9]\s*\)")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
WRAPPED_QUOTE_RE = re.compile(r'^\s*["\'](.+?)["\']\s*$')

TRAINING_META_DEFINITION_PHRASES = [
    "used to express",
    "used to describe",
    "used in reference to",
    "used as an insult",
    "portmanteau of",
    "coined and popularized",
    "originated from",
    "originating from",
    "derived from",
    "short hand of",
    "shorthand of",
    "the term is used",
    "the phrase could have a variety",
    "often associated with",
    "also a replacement for",
    "alternative forms include",
    "inspired multiple",
]

NO_FIXED_MEANING_GLOSSARY_PHRASES = [
    "nonsense word",
    "imaginary place",
    "multiple numerical meme variants",
]


@dataclass
class FileSummary:
    path: Path
    file_kind: str
    rows_loaded: int = 0
    pairs_extracted: int = 0
    extraction_note: str = ""


@dataclass
class PreparationStats:
    raw_supported_files_processed: int = 0
    supplemental_seed_files_processed: int = 0
    rows_before_cleaning: int = 0
    rows_after_basic_cleaning: int = 0
    rows_after_cleaning: int = 0
    flagged_bad_rows: int = 0
    duplicates_removed: int = 0
    missing_value_count: int = 0
    identical_rows_removed: int = 0
    url_only_rows_removed: int = 0
    symbol_only_rows_removed: int = 0
    too_short_rows_removed: int = 0
    too_long_rows_removed: int = 0
    broken_fragment_removed: int = 0
    hallucination_phrase_removed: int = 0
    definition_substitution_removed: int = 0
    length_ratio_removed: int = 0
    low_overlap_removed: int = 0
    low_quality_score_removed: int = 0
    rows_after_training_ready: int = 0
    training_ready_rows_rewritten: int = 0
    training_ready_rows_dropped: int = 0
    training_ready_glossary_rows_rewritten: int = 0
    training_ready_glossary_rows_dropped: int = 0
    training_ready_definition_rows_dropped: int = 0
    unreadable_files: list[str] = field(default_factory=list)
    unsupported_files: list[str] = field(default_factory=list)
    no_pair_files: list[str] = field(default_factory=list)
    processed_files: list[FileSummary] = field(default_factory=list)
    top_terms: Counter[str] = field(default_factory=Counter)


@dataclass
class QualityAssessment:
    score: int
    reasons: list[str] = field(default_factory=list)
    brainrot_word_count: int = 0
    normal_word_count: int = 0
    overlap_ratio: float | None = None
    overlap_count: int = 0
    hallucination_matches: list[str] = field(default_factory=list)
    definition_substitution_matches: list[str] = field(default_factory=list)


@dataclass
class TrainingReadyDecision:
    action: str
    training_normal: str
    reason: str


def normalize_column_name(name: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower())
    return text.strip("_")


def clean_text(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, float) and pd.isna(value):
        return ""

    text = str(value)
    if text.strip().lower() in {"", "nan", "none", "null"}:
        return ""

    text = text.replace("ⓘ", " ")
    text = unicodedata.normalize("NFKC", text).translate(QUOTE_TRANSLATION_TABLE)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n+", " ", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text.strip()


def count_words(text: str) -> int:
    return len(WORD_RE.findall(text))


def normalize_keyword(token: str) -> str:
    normalized = token.casefold().strip("'")
    if not normalized:
        return ""

    normalized = IRREGULAR_KEYWORD_NORMALIZATION.get(normalized, normalized)

    if normalized.endswith("'s") and len(normalized) > 3:
        normalized = normalized[:-2]
    elif normalized.endswith("ies") and len(normalized) > 4:
        normalized = normalized[:-3] + "y"
    elif normalized.endswith("ing") and len(normalized) > 5:
        normalized = normalized[:-3]
        if len(normalized) >= 2 and normalized[-1] == normalized[-2]:
            normalized = normalized[:-1]
    elif normalized.endswith("ed") and len(normalized) > 4:
        normalized = normalized[:-2]
        if len(normalized) >= 2 and normalized[-1] == normalized[-2]:
            normalized = normalized[:-1]
    elif normalized.endswith("es") and len(normalized) > 4:
        normalized = normalized[:-2]
    elif normalized.endswith("s") and len(normalized) > 4:
        normalized = normalized[:-1]

    return normalized.strip("'")


def extract_content_keywords(text: str) -> set[str]:
    keywords: set[str] = set()
    for raw_token in WORD_RE.findall(text.casefold()):
        normalized = normalize_keyword(raw_token)
        if not normalized or normalized in QUALITY_STOPWORDS:
            continue
        if len(normalized) <= 1 and normalized not in {"ai", "ac"}:
            continue
        keywords.add(normalized)
    return keywords


def find_hallucination_phrases(text: str) -> list[str]:
    lowered = text.casefold()
    return [phrase for phrase in HALLUCINATION_FILLER_PHRASES if phrase in lowered]


def is_noisy_definition_source(source_dataset: str) -> bool:
    return "projolx/genz_brainrot_dataset" in source_dataset.casefold()


def find_definition_substitution_artifacts(
    brainrot: str,
    normal: str,
    source_dataset: str = "",
) -> list[str]:
    if not is_noisy_definition_source(source_dataset):
        return []
    if count_words(brainrot) < 4:
        return []

    lowered_normal = normal.casefold()
    reasons: list[str] = []

    if DOUBLE_DETERMINER_RE.search(normal):
        reasons.append("double_determiner")
    if A_SOMEONE_RE.search(normal):
        reasons.append("broken_noun_phrase")
    if any(pattern.search(normal) for pattern in MALFORMED_INFLECTION_PATTERNS):
        reasons.append("malformed_inflection")

    phrase_matches = [phrase for phrase in DEFINITION_SUBSTITUTION_PHRASES if phrase in lowered_normal]
    if phrase_matches:
        reasons.append("definition_phrase: " + ", ".join(sorted(dict.fromkeys(phrase_matches))))

    return reasons


def has_unbalanced_brackets(text: str) -> bool:
    bracket_pairs = {")": "(",
        "]": "[",
        "}": "{",
    }
    opening_brackets = set(bracket_pairs.values())
    stack: list[str] = []

    for character in text:
        if character in opening_brackets:
            stack.append(character)
        elif character in bracket_pairs:
            if not stack or stack[-1] != bracket_pairs[character]:
                return True
            stack.pop()

    return bool(stack)


def has_unbalanced_double_quotes(text: str) -> bool:
    return text.count('"') % 2 != 0


def is_valid_short_slang_term(text: str) -> bool:
    stripped = text.strip()
    tokens = WORD_RE.findall(stripped.casefold())
    if not tokens:
        return False

    normalized_tokens: list[str] = []
    for token in tokens:
        normalized = normalize_keyword(token)
        if normalized:
            normalized_tokens.append(normalized)
    normalized_text = " ".join(normalized_tokens)

    if normalized_text in VALID_SHORT_SLANG_TERMS:
        return True
    if len(normalized_tokens) == 1:
        token = normalized_tokens[0]
        if token in {"l", "w"}:
            return True
        return token.isalnum() and 2 <= len(token) <= 24
    if len(normalized_tokens) == 2:
        return all(token.isalnum() for token in normalized_tokens) and sum(len(token) >= 2 for token in normalized_tokens) >= 1
    if len(normalized_tokens) == 3:
        return (
            all(token.isalnum() for token in normalized_tokens)
            and sum(len(token) >= 2 for token in normalized_tokens) >= 2
            and len(normalized_text) <= 24
        )
    return False


def detect_broken_fragment(brainrot: str) -> list[str]:
    reasons: list[str] = []
    lowered = brainrot.casefold()
    word_count = count_words(brainrot)
    tokens = [token for token in WORD_RE.findall(brainrot) if re.search(r"[A-Za-z0-9]", token)]

    if re.match(r'^\s*[,.\)\]\}"\']', brainrot):
        reasons.append("starts_with_punctuation")

    if has_unbalanced_double_quotes(brainrot):
        reasons.append("unbalanced_quotes")

    if has_unbalanced_brackets(brainrot):
        reasons.append("unbalanced_brackets")

    fragment_patterns = {
        "fragment_pattern=)).": "))." in brainrot,
        "fragment_pattern=).": ")." in brainrot,
        'fragment_pattern=, """': bool(re.search(r',\s*"+', brainrot)),
        'fragment_pattern=meaning """': bool(re.search(r'\bmeaning\s*"+', lowered)),
        "fragment_pattern=e.g.": "e.g." in lowered,
        "fragment_pattern=for example": "for example" in lowered,
    }
    for label, matched in fragment_patterns.items():
        if matched:
            reasons.append(label)

    has_fragment_indicator = any(fragment_patterns.values())
    if has_fragment_indicator and (
        word_count <= 12
        or "starts_with_punctuation" in reasons
        or "unbalanced_quotes" in reasons
        or "unbalanced_brackets" in reasons
    ):
        reasons.append("example_fragment")

    meaningful_word_count = sum(1 for token in tokens if len(re.sub(r"[^A-Za-z0-9]+", "", token)) >= 2)
    if meaningful_word_count < 2 and not is_valid_short_slang_term(brainrot):
        reasons.append("too_few_meaningful_words")

    seen: set[str] = set()
    deduped_reasons: list[str] = []
    for reason in reasons:
        if reason not in seen:
            deduped_reasons.append(reason)
            seen.add(reason)
    return deduped_reasons


def ensure_directories() -> None:
    for folder in (RAW_DIR, PROCESSED_DIR, ANALYSIS_DIR, PROJECT_ROOT / "logs"):
        folder.mkdir(parents=True, exist_ok=True)


def get_supported_raw_files() -> list[Path]:
    supported_files: list[Path] = []
    if not RAW_DIR.exists():
        return supported_files

    for path in sorted(RAW_DIR.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() in SUPPORTED_EXTENSIONS:
            supported_files.append(path)
    return supported_files


def get_unsupported_raw_files() -> list[str]:
    unsupported: list[str] = []
    if not RAW_DIR.exists():
        return unsupported

    for path in sorted(RAW_DIR.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            unsupported.append(str(path.relative_to(PROJECT_ROOT)))
    return unsupported


def get_supplemental_seed_files() -> list[Path]:
    seed_files: list[Path] = []
    for file_group in SUPPLEMENTAL_SEED_FILE_GROUPS.values():
        for candidate in file_group:
            if candidate.exists():
                seed_files.append(candidate)
                break
    return seed_files


def read_supported_file(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()

    if suffix == ".csv":
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    if suffix == ".xlsx":
        return pd.read_excel(path, dtype=str)
    if suffix == ".json":
        return pd.DataFrame(load_json_records(path))
    if suffix in {".txt", ".md"}:
        return pd.DataFrame(parse_text_records(path))

    raise ValueError(f"Unsupported file type: {path.suffix}")


def load_json_records(path: Path) -> list[dict[str, Any]]:
    raw_text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not raw_text:
        return []

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        line_records: list[dict[str, Any]] = []
        for line in raw_text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                parsed_line = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed_line, dict):
                line_records.append(parsed_line)
        return line_records

    if isinstance(payload, list):
        records: list[dict[str, Any]] = []
        for item in payload:
            if isinstance(item, dict):
                records.append(item)
            elif isinstance(item, str):
                records.append({"text": item})
        return records

    if isinstance(payload, dict):
        for key in ("data", "records", "items", "rows", "examples", "dataset"):
            nested = payload.get(key)
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]

        if payload and all(isinstance(key, str) and isinstance(value, str) for key, value in payload.items()):
            return [{"term": key, "meaning": value} for key, value in payload.items()]

        return [payload]

    return []


def parse_text_records(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    pairs: list[dict[str, str]] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("```") or line.startswith("#"):
            continue
        if re.fullmatch(r"[|:\-\s]+", line):
            continue

        line = re.sub(r"^\s*[-*+]\s*", "", line)

        if "|" in line:
            columns = [part.strip() for part in line.strip("|").split("|")]
            if len(columns) >= 2 and not all(set(part) <= {"-", ":"} for part in columns[:2]):
                pairs.append({"brainrot": columns[0], "normal": columns[1]})
                continue

        separators = ["=>", "->", "\t", "::", " - ", " – ", " — "]
        split_pair = None
        for separator in separators:
            if separator in line:
                left, right = line.split(separator, 1)
                split_pair = (left, right)
                break

        if split_pair is None and ":" in line:
            left, right = line.split(":", 1)
            if len(left.strip()) <= 40:
                split_pair = (left, right)

        if split_pair is None:
            continue

        left, right = split_pair
        pairs.append({"brainrot": left.strip(), "normal": right.strip()})

    return pairs


def choose_column(column_lookup: dict[str, str], candidates: list[str], exclude: set[str] | None = None) -> str | None:
    exclude = exclude or set()
    for candidate in candidates:
        actual_name = column_lookup.get(candidate)
        if actual_name and actual_name not in exclude:
            return actual_name
    return None


def build_column_lookup(dataframe: pd.DataFrame) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for column in dataframe.columns:
        normalized_name = normalize_column_name(column)
        lookup.setdefault(normalized_name, column)
    return lookup


def collect_top_terms(stats: PreparationStats, dataframe: pd.DataFrame, term_column: str | None) -> None:
    if term_column:
        for value in dataframe[term_column].tolist():
            cleaned_value = clean_text(value)
            if cleaned_value:
                stats.top_terms[cleaned_value.lower()] += 1


def should_use_paired_columns(
    dataframe: pd.DataFrame,
    input_column: str | None,
    output_column: str | None,
    term_column: str | None,
    meaning_column: str | None,
) -> bool:
    if not input_column or not output_column:
        return False
    if term_column and meaning_column and input_column == term_column and output_column == meaning_column:
        return False

    normalized_input = normalize_column_name(input_column)
    normalized_output = normalize_column_name(output_column)

    if normalized_input in METADATA_LIKE_COLUMNS or normalized_output in METADATA_LIKE_COLUMNS:
        if term_column and meaning_column:
            return False

    row_count = len(dataframe)
    if row_count >= 5:
        input_values = {clean_text(value) for value in dataframe[input_column].tolist() if clean_text(value)}
        output_values = {clean_text(value) for value in dataframe[output_column].tolist() if clean_text(value)}
        if len(input_values) <= 1 or len(output_values) <= 1:
            return False

    return True


def extract_pairs_from_dataframe(
    dataframe: pd.DataFrame,
    source_path: Path,
    stats: PreparationStats,
) -> tuple[list[dict[str, str]], str]:
    if dataframe.empty:
        return [], "file was empty after loading"

    dataframe = dataframe.fillna("")
    column_lookup = build_column_lookup(dataframe)

    input_column = choose_column(column_lookup, INPUT_COLUMN_CANDIDATES)
    output_column = choose_column(column_lookup, OUTPUT_COLUMN_CANDIDATES, exclude={input_column} if input_column else None)
    term_column = choose_column(column_lookup, TERM_COLUMN_CANDIDATES)
    meaning_column = choose_column(column_lookup, MEANING_COLUMN_CANDIDATES, exclude={term_column} if term_column else None)
    used_paired_columns = should_use_paired_columns(
        dataframe,
        input_column,
        output_column,
        term_column,
        meaning_column,
    )

    collect_top_terms(stats, dataframe, term_column)

    extracted_pairs: list[dict[str, str]] = []

    if used_paired_columns:
        for row in dataframe.to_dict(orient="records"):
            extracted_pairs.append(
                {
                    "brainrot": row.get(input_column, ""),
                    "normal": row.get(output_column, ""),
                    "source_file": str(source_path.relative_to(PROJECT_ROOT)),
                    "source_dataset": row.get("source_dataset", ""),
                }
            )

    if term_column and meaning_column:
        for row in dataframe.to_dict(orient="records"):
            term_value = row.get(term_column, "")
            meaning_value = row.get(meaning_column, "")
            extracted_pairs.append(
                {
                    "brainrot": term_value,
                    "normal": meaning_value,
                    "source_file": str(source_path.relative_to(PROJECT_ROOT)),
                    "source_dataset": row.get("source_dataset", ""),
                }
            )

    if not extracted_pairs:
        return [], "no compatible input/output or term/meaning columns detected"

    if used_paired_columns and term_column and meaning_column:
        return extracted_pairs, f"used paired columns ({input_column} -> {output_column}) and glossary columns ({term_column} -> {meaning_column})"
    if used_paired_columns:
        return extracted_pairs, f"used paired columns ({input_column} -> {output_column})"
    return extracted_pairs, f"used glossary columns ({term_column} -> {meaning_column})"


def is_url_only(text: str) -> bool:
    return bool(re.fullmatch(r"(?:https?://|www\.)\S+", text, flags=re.IGNORECASE))


def is_symbols_only(text: str) -> bool:
    return not bool(re.search(r"[A-Za-z0-9]", text))


def has_meaningful_content(text: str) -> bool:
    alphanumeric = re.sub(r"[^A-Za-z0-9]+", "", text)
    return len(alphanumeric) >= 2


def is_glossary_seed_source(source_file: str) -> bool:
    normalized_source = source_file.replace("\\", "/").lower()
    return normalized_source.endswith("slang_terms.csv") or normalized_source.endswith("slang_terms.json")


def split_definition_sentences(text: str) -> list[str]:
    return [segment.strip() for segment in SENTENCE_SPLIT_RE.split(text.strip()) if segment.strip()]


def ensure_terminal_period(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return ""
    if stripped[-1] in ".!?":
        return stripped
    return stripped + "."


def unwrap_quoted_text(text: str) -> str:
    match = WRAPPED_QUOTE_RE.match(text.strip())
    return match.group(1).strip() if match else text.strip()


def score_glossary_sentence(sentence: str) -> int:
    lowered = sentence.casefold().strip()
    score = 0

    if any(phrase in lowered for phrase in TRAINING_META_DEFINITION_PHRASES):
        score -= 4

    preferred_prefixes = (
        "meaning ",
        "refers to ",
        "used to express ",
        "used to describe ",
        "used in reference to ",
        "abbreviation for ",
        "acronym for ",
        "shortened version of ",
        "a variant of ",
        "an algospeak form of ",
        "the state of ",
        "commonly used to mean ",
        "effectively ",
        "a ",
        "an ",
    )
    if lowered.startswith(preferred_prefixes):
        score += 4

    if "approval" in lowered or "charisma" in lowered or "confidence" in lowered:
        score += 1
    if "similar to " in lowered or "often associated" in lowered:
        score -= 2

    return score


def simplify_glossary_definition_for_training(brainrot: str, normal: str) -> TrainingReadyDecision:
    meaning = clean_text(normal)
    lowered_meaning = meaning.casefold()

    if MULTI_SENSE_GLOSSARY_RE.search(meaning):
        return TrainingReadyDecision(
            action="drop",
            training_normal="",
            reason="glossary_multi_sense_definition",
        )

    if any(phrase in lowered_meaning for phrase in NO_FIXED_MEANING_GLOSSARY_PHRASES):
        return TrainingReadyDecision(
            action="drop",
            training_normal="",
            reason="glossary_no_stable_translation",
        )

    shorthand_match = re.search(
        r'(?:short hand|shorthand)\s+of\s+the\s+usual\s+"([^"]+)"',
        meaning,
        flags=re.IGNORECASE,
    )
    if shorthand_match:
        training_normal = ensure_terminal_period(unwrap_quoted_text(shorthand_match.group(1)))
        return TrainingReadyDecision(
            action="rewrite" if training_normal != meaning else "keep",
            training_normal=training_normal,
            reason="glossary_shorthand_rewrite",
        )

    candidate_sentences = split_definition_sentences(meaning)
    if not candidate_sentences:
        return TrainingReadyDecision(action="drop", training_normal="", reason="glossary_empty_definition")

    candidate = max(candidate_sentences, key=score_glossary_sentence)
    lowered_candidate = candidate.casefold().strip()

    if score_glossary_sentence(candidate) <= 0 and any(
        phrase in lowered_meaning for phrase in TRAINING_META_DEFINITION_PHRASES
    ):
        return TrainingReadyDecision(
            action="drop",
            training_normal="",
            reason="glossary_meta_only_definition",
        )

    prefix_rewrites: list[tuple[re.Pattern[str], str]] = [
        (re.compile(r"^meaning\s+", flags=re.IGNORECASE), ""),
        (re.compile(r"^refers to\s+", flags=re.IGNORECASE), ""),
        (re.compile(r"^used to express\s+", flags=re.IGNORECASE), "an expression of "),
        (re.compile(r"^used to describe\s+", flags=re.IGNORECASE), ""),
        (re.compile(r"^used in reference to\s+", flags=re.IGNORECASE), ""),
        (re.compile(r"^used as an insult to\s+", flags=re.IGNORECASE), "an insult used to "),
        (re.compile(r"^shortened version of\s+", flags=re.IGNORECASE), ""),
        (re.compile(r"^a variant of the word\s+", flags=re.IGNORECASE), ""),
        (re.compile(r"^a variant of\s+", flags=re.IGNORECASE), ""),
        (re.compile(r"^pertaining to those who\s+", flags=re.IGNORECASE), "someone who "),
        (re.compile(r"^commonly used to mean\s+", flags=re.IGNORECASE), ""),
        (re.compile(r"^effectively\s+", flags=re.IGNORECASE), ""),
    ]

    rewritten = candidate
    for pattern, replacement in prefix_rewrites:
        rewritten = pattern.sub(replacement, rewritten, count=1)

    abbreviation_match = re.match(
        r'^abbreviation for\s+"([^"]+)"\s*:\s*(.+)$',
        candidate,
        flags=re.IGNORECASE,
    )
    if abbreviation_match:
        rewritten = abbreviation_match.group(2).strip()
    else:
        abbreviation_match = re.match(
            r'^abbreviation for\s+"([^"]+)"\.?$',
            candidate,
            flags=re.IGNORECASE,
        )
        if abbreviation_match:
            rewritten = abbreviation_match.group(1).strip()

    acronym_match = re.match(
        r'^acronym for\s+"([^"]+)"\.?$',
        candidate,
        flags=re.IGNORECASE,
    )
    if acronym_match:
        rewritten = acronym_match.group(1).strip()

    algospeak_match = re.match(
        r'^an algospeak form of the word\s+"([^"]+)"\.?$',
        candidate,
        flags=re.IGNORECASE,
    )
    if algospeak_match:
        rewritten = f'an altered spelling of "{algospeak_match.group(1).strip()}"'

    contemporary_use_match = re.search(
        r"more contemporary use has been to\s+(.+)$",
        candidate,
        flags=re.IGNORECASE,
    )
    if contemporary_use_match:
        rewritten = contemporary_use_match.group(1).strip()

    emoji_match = re.match(
        r"^also a replacement for .+?,\s*representing\s+(.+)$",
        candidate,
        flags=re.IGNORECASE,
    )
    if emoji_match:
        rewritten = f'an emoji representing {emoji_match.group(1).strip()}'

    rewritten = re.sub(r"\s+", " ", rewritten).strip(" ;,:-")
    rewritten = rewritten.replace('"', "")
    rewritten = re.sub(r"\bexpress approval of\b", "approval of", rewritten, flags=re.IGNORECASE)
    rewritten = re.sub(r"\bagreeing with\b", "agreement with", rewritten, flags=re.IGNORECASE)
    rewritten = unwrap_quoted_text(rewritten)
    rewritten = ensure_terminal_period(rewritten)
    lowered_rewritten = rewritten.casefold()

    if not rewritten or count_words(rewritten) < 2:
        return TrainingReadyDecision(
            action="drop",
            training_normal="",
            reason="glossary_definition_too_thin",
        )

    if any(phrase in lowered_rewritten for phrase in TRAINING_META_DEFINITION_PHRASES):
        return TrainingReadyDecision(
            action="drop",
            training_normal="",
            reason="glossary_definition_still_meta",
        )

    if any(phrase in lowered_rewritten for phrase in NO_FIXED_MEANING_GLOSSARY_PHRASES):
        return TrainingReadyDecision(
            action="drop",
            training_normal="",
            reason="glossary_definition_still_unstable",
        )

    if count_words(rewritten) > 18:
        return TrainingReadyDecision(
            action="drop",
            training_normal="",
            reason="glossary_definition_too_long",
        )

    action = "rewrite" if rewritten != meaning else "keep"
    reason = "glossary_rewritten_for_training" if action == "rewrite" else "glossary_kept_for_training"
    return TrainingReadyDecision(action=action, training_normal=rewritten, reason=reason)


def find_training_target_artifacts(brainrot: str, normal: str, source_file: str) -> list[str]:
    if is_glossary_seed_source(source_file):
        return []

    lowered_normal = normal.casefold()
    reasons: list[str] = []
    if any(phrase in lowered_normal for phrase in TRAINING_META_DEFINITION_PHRASES):
        reasons.append("definition_style_target")
    if re.match(r"^(meaning|refers to)\s+", lowered_normal):
        reasons.append("glossary_prefix_target")
    if lowered_normal.count('"') == 1:
        reasons.append("unbalanced_target_quote")
    if re.search(
        r"\bused to (?:say|describe|express|refer|indicate|call|mean)\b",
        lowered_normal,
    ):
        reasons.append("dictionary_explanation_in_sentence")
    return reasons


def build_training_ready_dataset(
    cleaned_dataframe: pd.DataFrame,
    stats: PreparationStats,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if cleaned_dataframe.empty:
        empty_training = pd.DataFrame(columns=["brainrot", "normal", "source_file", "source_dataset"])
        empty_review = pd.DataFrame(
            columns=[
                "brainrot",
                "original_normal",
                "training_normal",
                "action",
                "reason",
                "source_file",
                "source_dataset",
            ]
        )
        return empty_training, empty_review

    kept_rows: list[dict[str, str]] = []
    review_rows: list[dict[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()

    for row in cleaned_dataframe.to_dict(orient="records"):
        brainrot = str(row.get("brainrot", ""))
        original_normal = str(row.get("normal", ""))
        source_file = str(row.get("source_file", ""))
        source_dataset = str(row.get("source_dataset", ""))

        decision = TrainingReadyDecision(
            action="keep",
            training_normal=original_normal,
            reason="already_functional",
        )

        if is_glossary_seed_source(source_file):
            decision = simplify_glossary_definition_for_training(brainrot, original_normal)
            if decision.action == "rewrite":
                stats.training_ready_rows_rewritten += 1
                stats.training_ready_glossary_rows_rewritten += 1
            elif decision.action == "drop":
                stats.training_ready_rows_dropped += 1
                stats.training_ready_glossary_rows_dropped += 1
        else:
            target_artifacts = find_training_target_artifacts(brainrot, original_normal, source_file)
            if target_artifacts:
                decision = TrainingReadyDecision(
                    action="drop",
                    training_normal="",
                    reason="; ".join(target_artifacts),
                )
                stats.training_ready_rows_dropped += 1
                stats.training_ready_definition_rows_dropped += 1

        training_normal = clean_text(decision.training_normal)
        if decision.action != "drop":
            pair_key = (brainrot, training_normal)
            if pair_key in seen_pairs:
                decision = TrainingReadyDecision(
                    action="drop",
                    training_normal="",
                    reason="training_ready_duplicate_after_rewrite",
                )
                stats.training_ready_rows_dropped += 1
            else:
                seen_pairs.add(pair_key)
                kept_rows.append(
                    {
                        "brainrot": brainrot,
                        "normal": training_normal,
                        "source_file": source_file,
                        "source_dataset": source_dataset,
                    }
                )

        review_rows.append(
            {
                "brainrot": brainrot,
                "original_normal": original_normal,
                "training_normal": training_normal,
                "action": decision.action,
                "reason": decision.reason,
                "source_file": source_file,
                "source_dataset": source_dataset,
            }
        )

    kept_dataframe = pd.DataFrame(
        kept_rows,
        columns=["brainrot", "normal", "source_file", "source_dataset"],
    )
    if not kept_dataframe.empty:
        kept_dataframe = kept_dataframe.sort_values(by=["brainrot", "normal"], kind="stable").reset_index(drop=True)

    review_dataframe = pd.DataFrame(
        review_rows,
        columns=[
            "brainrot",
            "original_normal",
            "training_normal",
            "action",
            "reason",
            "source_file",
            "source_dataset",
        ],
    )
    if not review_dataframe.empty:
        review_dataframe = review_dataframe.sort_values(
            by=["action", "reason", "brainrot"],
            kind="stable",
        ).reset_index(drop=True)

    stats.rows_after_training_ready = len(kept_dataframe)
    return kept_dataframe, review_dataframe


def classify_invalid_pair(brainrot: str, normal: str, source_file: str = "") -> str | None:
    glossary_seed = is_glossary_seed_source(source_file)

    if not brainrot or not normal:
        return "missing"
    if brainrot.casefold() == normal.casefold():
        return "same_text"
    if is_url_only(brainrot) or is_url_only(normal):
        return "url_only"
    if is_symbols_only(brainrot) or is_symbols_only(normal):
        return "symbols_only"
    normal_length_limit = MAX_GLOSSARY_NORMAL_LENGTH if glossary_seed else MAX_NORMAL_LENGTH
    if len(brainrot) > MAX_BRAINROT_LENGTH or len(normal) > normal_length_limit:
        return "too_long"
    if glossary_seed:
        if not re.search(r"[A-Za-z0-9]", brainrot) or not has_meaningful_content(normal):
            return "too_short"
        return None
    if not has_meaningful_content(brainrot) or not has_meaningful_content(normal):
        return "too_short"
    return None


def quality_score_pair(
    brainrot: str,
    normal: str,
    source_file: str = "",
    source_dataset: str = "",
    strict: bool = False,
) -> QualityAssessment:
    glossary_seed = is_glossary_seed_source(source_file)
    brainrot_word_count = count_words(brainrot)
    normal_word_count = count_words(normal)
    score = 100
    reasons: list[str] = []

    broken_fragment_reasons = detect_broken_fragment(brainrot)
    if broken_fragment_reasons:
        reasons.append("broken_fragment: " + ", ".join(broken_fragment_reasons))
        score -= 70 if strict else 55

    hallucination_matches = find_hallucination_phrases(normal)
    if hallucination_matches:
        reasons.append(
            "hallucination_phrase: " + ", ".join(sorted(dict.fromkeys(hallucination_matches)))
        )
        score -= 65 if strict else 55

    definition_substitution_matches = find_definition_substitution_artifacts(
        brainrot=brainrot,
        normal=normal,
        source_dataset=source_dataset,
    )
    if definition_substitution_matches:
        reasons.append("definition_substitution: " + ", ".join(definition_substitution_matches))
        score -= 70 if strict else 60

    overlap_ratio: float | None = None
    overlap_count = 0

    if not glossary_seed:
        length_ratio_limit = STRICT_LENGTH_RATIO_LIMIT if strict else DEFAULT_LENGTH_RATIO_LIMIT
        max_normal_words = STRICT_MAX_NORMAL_WORDS if strict else DEFAULT_MAX_NORMAL_WORDS
        normal_to_brainrot_ratio = normal_word_count / max(brainrot_word_count, 1)

        if brainrot_word_count >= 4 and normal_to_brainrot_ratio > length_ratio_limit and normal_word_count >= brainrot_word_count + 8:
            reasons.append(
                f"length_ratio: normal words {normal_word_count} vs brainrot {brainrot_word_count} ({normal_to_brainrot_ratio:.2f}x)"
            )
            score -= 25
        elif normal_word_count > max_normal_words and brainrot_word_count < max_normal_words - 10:
            reasons.append(
                f"length_ratio: normal has {normal_word_count} words while brainrot has {brainrot_word_count}"
            )
            score -= 20

        brainrot_keywords = extract_content_keywords(brainrot)
        normal_keywords = extract_content_keywords(normal)
        overlap_count = len(brainrot_keywords & normal_keywords)
        if brainrot_keywords:
            overlap_ratio = overlap_count / len(brainrot_keywords)

        overlap_word_threshold = 8 if strict else 10
        enough_keywords = len(brainrot_keywords) >= 4 and len(normal_keywords) >= 4
        if brainrot_word_count >= overlap_word_threshold and normal_word_count >= overlap_word_threshold and enough_keywords:
            if overlap_count == 0:
                reasons.append(
                    f"low_overlap: no shared content keywords between brainrot {sorted(brainrot_keywords)[:6]} and normal {sorted(normal_keywords)[:6]}"
                )
                score -= 30 if strict else 25
            elif strict and overlap_count <= 1 and len(normal_keywords - brainrot_keywords) >= 5 and normal_word_count >= brainrot_word_count + 4:
                reasons.append(
                    f"low_overlap: only {overlap_count} shared content keyword while normal adds many new topics {sorted(normal_keywords - brainrot_keywords)[:6]}"
                )
                score -= 20
            elif overlap_ratio is not None and overlap_ratio < (0.12 if strict else 0.08) and normal_word_count >= brainrot_word_count + 5:
                reasons.append(
                    f"low_overlap: overlap ratio {overlap_ratio:.2f} with brainrot keywords {sorted(brainrot_keywords)[:6]}"
                )
                score -= 20

    return QualityAssessment(
        score=max(score, 0),
        reasons=reasons,
        brainrot_word_count=brainrot_word_count,
        normal_word_count=normal_word_count,
        overlap_ratio=overlap_ratio,
        overlap_count=overlap_count,
        hallucination_matches=hallucination_matches,
        definition_substitution_matches=definition_substitution_matches,
    )


def clean_and_filter_pairs(raw_pairs: list[dict[str, str]], stats: PreparationStats) -> pd.DataFrame:
    cleaned_pairs: list[dict[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()

    for pair in raw_pairs:
        brainrot = clean_text(pair.get("brainrot", ""))
        normal = clean_text(pair.get("normal", ""))
        source_file = str(pair.get("source_file", ""))
        source_dataset = clean_text(pair.get("source_dataset", ""))

        invalid_reason = classify_invalid_pair(brainrot, normal, source_file=source_file)
        if invalid_reason == "missing":
            stats.missing_value_count += 1
            continue
        if invalid_reason == "same_text":
            stats.identical_rows_removed += 1
            continue
        if invalid_reason == "url_only":
            stats.url_only_rows_removed += 1
            continue
        if invalid_reason == "symbols_only":
            stats.symbol_only_rows_removed += 1
            continue
        if invalid_reason == "too_short":
            stats.too_short_rows_removed += 1
            continue
        if invalid_reason == "too_long":
            stats.too_long_rows_removed += 1
            continue

        pair_key = (brainrot, normal)
        if pair_key in seen_pairs:
            stats.duplicates_removed += 1
            continue

        seen_pairs.add(pair_key)
        cleaned_pairs.append(
            {
                "brainrot": brainrot,
                "normal": normal,
                "source_file": source_file,
                "source_dataset": source_dataset,
            }
        )

    cleaned_dataframe = pd.DataFrame(
        cleaned_pairs,
        columns=["brainrot", "normal", "source_file", "source_dataset"],
    )
    if not cleaned_dataframe.empty:
        cleaned_dataframe = cleaned_dataframe.sort_values(by=["brainrot", "normal"], kind="stable").reset_index(drop=True)
    return cleaned_dataframe


def apply_quality_filters(
    dataframe: pd.DataFrame,
    stats: PreparationStats,
    strict: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if dataframe.empty:
        flagged_dataframe = pd.DataFrame(columns=["brainrot", "normal", "reason_flagged"])
        return dataframe.copy(), flagged_dataframe

    kept_rows: list[dict[str, str]] = []
    flagged_rows: list[dict[str, str]] = []
    score_threshold = 80 if strict else 65

    for row in dataframe.to_dict(orient="records"):
        assessment = quality_score_pair(
            brainrot=str(row.get("brainrot", "")),
            normal=str(row.get("normal", "")),
            source_file=str(row.get("source_file", "")),
            source_dataset=str(row.get("source_dataset", "")),
            strict=strict,
        )

        if assessment.reasons or assessment.score < score_threshold:
            if any(reason.startswith("broken_fragment:") for reason in assessment.reasons):
                stats.broken_fragment_removed += 1
            if any(reason.startswith("hallucination_phrase:") for reason in assessment.reasons):
                stats.hallucination_phrase_removed += 1
            if any(reason.startswith("definition_substitution:") for reason in assessment.reasons):
                stats.definition_substitution_removed += 1
            if any(reason.startswith("length_ratio:") for reason in assessment.reasons):
                stats.length_ratio_removed += 1
            if any(reason.startswith("low_overlap:") for reason in assessment.reasons):
                stats.low_overlap_removed += 1
            if not assessment.reasons and assessment.score < score_threshold:
                stats.low_quality_score_removed += 1

            flagged_rows.append(
                {
                    "brainrot": str(row.get("brainrot", "")),
                    "normal": str(row.get("normal", "")),
                    "reason_flagged": "; ".join(assessment.reasons) if assessment.reasons else f"quality_score_below_threshold: {assessment.score}",
                }
            )
            continue

        kept_rows.append(
            {
                "brainrot": str(row.get("brainrot", "")),
                "normal": str(row.get("normal", "")),
                "source_file": str(row.get("source_file", "")),
                "source_dataset": str(row.get("source_dataset", "")),
            }
        )

    flagged_dataframe = pd.DataFrame(flagged_rows, columns=["brainrot", "normal", "reason_flagged"])
    if not flagged_dataframe.empty:
        flagged_dataframe = flagged_dataframe.sort_values(
            by=["reason_flagged", "brainrot", "normal"],
            kind="stable",
        ).reset_index(drop=True)

    kept_dataframe = pd.DataFrame(
        kept_rows,
        columns=["brainrot", "normal", "source_file", "source_dataset"],
    )
    if not kept_dataframe.empty:
        kept_dataframe = kept_dataframe.sort_values(by=["brainrot", "normal"], kind="stable").reset_index(drop=True)

    stats.flagged_bad_rows = len(flagged_dataframe)
    return kept_dataframe, flagged_dataframe


def write_dataset_csv(dataframe: pd.DataFrame, output_path: Path) -> None:
    dataframe.loc[:, ["brainrot", "normal"]].to_csv(output_path, index=False, encoding="utf-8")


def write_flagged_pairs_csv(dataframe: pd.DataFrame, output_path: Path) -> None:
    dataframe.to_csv(output_path, index=False, encoding="utf-8")


def write_training_ready_review_csv(dataframe: pd.DataFrame, output_path: Path) -> None:
    dataframe.to_csv(output_path, index=False, encoding="utf-8")


def build_sample_table(dataframe: pd.DataFrame, limit: int = 20) -> str:
    if dataframe.empty:
        return "_No cleaned pairs available._"

    sample_size = min(limit, len(dataframe))
    sample_frame = dataframe.sample(n=sample_size, random_state=RANDOM_SEED) if len(dataframe) > sample_size else dataframe
    sample_frame = sample_frame.reset_index(drop=True)

    lines = ["| brainrot | normal |", "|---|---|"]
    for _, row in sample_frame.iterrows():
        brainrot = str(row["brainrot"]).replace("|", "\\|")
        normal = str(row["normal"]).replace("|", "\\|")
        lines.append(f"| {brainrot} | {normal} |")
    return "\n".join(lines)


def build_top_terms_table(top_terms: Counter[str], limit: int = 20) -> str:
    if not top_terms:
        return "_No reusable slang terms were detected from explicit term-like columns._"

    lines = ["| term | count |", "|---|---|"]
    for term, count in top_terms.most_common(limit):
        lines.append(f"| {term.replace('|', '\\|')} | {count} |")
    return "\n".join(lines)


def build_flagged_pairs_table(dataframe: pd.DataFrame, limit: int = 20) -> str:
    if dataframe.empty:
        return "_No bad pairs were flagged._"

    sample_frame = dataframe.head(limit).reset_index(drop=True)
    lines = ["| brainrot | normal | reason_flagged |", "|---|---|---|"]
    for _, row in sample_frame.iterrows():
        brainrot = str(row["brainrot"]).replace("|", "\\|")
        normal = str(row["normal"]).replace("|", "\\|")
        reason = str(row["reason_flagged"]).replace("|", "\\|")
        lines.append(f"| {brainrot} | {normal} | {reason} |")
    return "\n".join(lines)


def build_training_ready_review_table(dataframe: pd.DataFrame, limit: int = 20) -> str:
    if dataframe.empty:
        return "_No training-readiness review rows are available._"

    sample_frame = dataframe[dataframe["action"] != "keep"].head(limit).reset_index(drop=True)
    if sample_frame.empty:
        sample_frame = dataframe.head(limit).reset_index(drop=True)

    lines = ["| brainrot | original_normal | training_normal | action | reason |", "|---|---|---|---|---|"]
    for _, row in sample_frame.iterrows():
        brainrot = str(row["brainrot"]).replace("|", "\\|")
        original_normal = str(row["original_normal"]).replace("|", "\\|")
        training_normal = str(row["training_normal"]).replace("|", "\\|")
        action = str(row["action"]).replace("|", "\\|")
        reason = str(row["reason"]).replace("|", "\\|")
        lines.append(f"| {brainrot} | {original_normal} | {training_normal} | {action} | {reason} |")
    return "\n".join(lines)


def build_dataset_report(
    stats: PreparationStats,
    generated_dataframe: pd.DataFrame,
    cleaned_dataframe: pd.DataFrame,
    flagged_dataframe: pd.DataFrame,
    training_ready_dataframe: pd.DataFrame,
    training_ready_review_dataframe: pd.DataFrame,
    strict: bool,
) -> str:
    processed_file_lines = []
    for item in stats.processed_files:
        processed_file_lines.append(
            f"- `{item.path.relative_to(PROJECT_ROOT)}` ({item.file_kind}) - loaded {item.rows_loaded} rows, extracted {item.pairs_extracted} pairs"
        )
        if item.extraction_note:
            processed_file_lines.append(f"  - note: {item.extraction_note}")

    warnings: list[str] = []
    if stats.rows_after_cleaning < 100:
        warnings.append("- Warning: dataset has fewer than 100 rows.")
    if stats.rows_after_cleaning < 500:
        warnings.append("- Warning: dataset has fewer than 500 rows.")

    similarity_ratio = 1.0
    if stats.rows_after_cleaning > 0:
        similarity_ratio = cleaned_dataframe["brainrot"].nunique() / stats.rows_after_cleaning
        if similarity_ratio < 0.75:
            warnings.append(
                f"- Warning: many rows are too similar. Unique brainrot ratio is {similarity_ratio:.2%}."
            )

    if not warnings:
        warnings.append("- No high-priority dataset-size or similarity warnings were triggered.")

    processed_files_section = "\n".join(processed_file_lines) if processed_file_lines else "- No files were processed."
    unreadable_section = (
        "\n".join(f"- `{name}`" for name in stats.unreadable_files) if stats.unreadable_files else "- None"
    )
    unsupported_section = (
        "\n".join(f"- `{name}`" for name in stats.unsupported_files) if stats.unsupported_files else "- None"
    )
    no_pair_section = "\n".join(f"- `{name}`" for name in stats.no_pair_files) if stats.no_pair_files else "- None"

    return f"""# Dataset Report

Generated at: `{datetime.now().isoformat(timespec="seconds")}`
Quality mode: `{'strict' if strict else 'standard'}`

## Files Processed

- Supported raw files processed from `data/raw/`: {stats.raw_supported_files_processed}
- Compatible seed files processed from `data/processed/`: {stats.supplemental_seed_files_processed}

### File Names Processed

{processed_files_section}

### Unsupported Raw Files Skipped

{unsupported_section}

### Unreadable Files

{unreadable_section}

### Files With No Usable Pair Columns

{no_pair_section}

## Dataset Counts

- Rows before cleaning: {stats.rows_before_cleaning}
- Rows after baseline cleaning (`brainrot_dataset.csv`): {stats.rows_after_basic_cleaning}
- Final cleaned row count (`brainrot_dataset_cleaned.csv`): {stats.rows_after_cleaning}
- Training-ready row count (`brainrot_dataset_training_ready.csv`): {stats.rows_after_training_ready}
- Rows flagged as bad: {stats.flagged_bad_rows}
- Duplicates removed: {stats.duplicates_removed}
- Missing value count: {stats.missing_value_count}
- Identical brainrot/normal rows removed: {stats.identical_rows_removed}
- URL-only rows removed: {stats.url_only_rows_removed}
- Symbol-only rows removed: {stats.symbol_only_rows_removed}
- Too short rows removed: {stats.too_short_rows_removed}
- Too long rows removed: {stats.too_long_rows_removed}
- Rows removed by broken-fragment filter: {stats.broken_fragment_removed}
- Rows removed by hallucination phrase filter: {stats.hallucination_phrase_removed}
- Rows removed by definition-substitution filter: {stats.definition_substitution_removed}
- Rows removed by length-ratio filter: {stats.length_ratio_removed}
- Rows removed by low-overlap filter: {stats.low_overlap_removed}
- Rows removed by score-only fallback: {stats.low_quality_score_removed}
- Training-ready rows rewritten: {stats.training_ready_rows_rewritten}
- Training-ready rows dropped: {stats.training_ready_rows_dropped}
- Training-ready glossary rows rewritten: {stats.training_ready_glossary_rows_rewritten}
- Training-ready glossary rows dropped: {stats.training_ready_glossary_rows_dropped}
- Training-ready sentence rows dropped: {stats.training_ready_definition_rows_dropped}

_Quality filter counts can overlap when one row triggers multiple checks._

## Warnings

{chr(10).join(warnings)}

## Top 20 Most Common Slang Or Brainrot Terms

{build_top_terms_table(stats.top_terms)}

## Sample 20 Flagged Bad Pairs

{build_flagged_pairs_table(flagged_dataframe, limit=20)}

## Sample 20 Cleaned Pairs

{build_sample_table(cleaned_dataframe, limit=20)}

## Sample 20 Training-Readiness Decisions

{build_training_ready_review_table(training_ready_review_dataframe, limit=20)}

## Sample 20 Training-Ready Pairs

{build_sample_table(training_ready_dataframe, limit=20)}
"""


def print_terminal_summary(stats: PreparationStats, strict: bool) -> None:
    print("Dataset preparation complete.")
    print(f"Quality mode: {'strict' if strict else 'standard'}")
    print(f"Supported raw files processed: {stats.raw_supported_files_processed}")
    print(f"Supplemental seed files processed: {stats.supplemental_seed_files_processed}")
    print(f"Rows before cleaning: {stats.rows_before_cleaning}")
    print(f"Rows after baseline cleaning: {stats.rows_after_basic_cleaning}")
    print(f"Rows after final cleaning: {stats.rows_after_cleaning}")
    print(f"Rows after training-ready filtering: {stats.rows_after_training_ready}")
    print(f"Flagged bad pairs: {stats.flagged_bad_rows}")
    print(f"Duplicates removed: {stats.duplicates_removed}")
    print(f"Missing values removed: {stats.missing_value_count}")
    print(f"Broken-fragment removals: {stats.broken_fragment_removed}")
    print(f"Hallucination phrase removals: {stats.hallucination_phrase_removed}")
    print(f"Definition-substitution removals: {stats.definition_substitution_removed}")
    print(f"Length-ratio removals: {stats.length_ratio_removed}")
    print(f"Low-overlap removals: {stats.low_overlap_removed}")
    print(f"Training-ready rewrites: {stats.training_ready_rows_rewritten}")
    print(f"Training-ready drops: {stats.training_ready_rows_dropped}")
    print(f"Unreadable files: {len(stats.unreadable_files)}")
    print(f"Output dataset: {TRAINING_DATASET_PATH}")
    print(f"Cleaned dataset: {TRAINING_DATASET_CLEAN_PATH}")
    print(f"Training-ready dataset: {TRAINING_READY_DATASET_PATH}")
    print(f"Flagged bad pairs: {FLAGGED_BAD_PAIRS_PATH}")
    print(f"Training-ready review: {TRAINING_READY_REVIEW_PATH}")
    print(f"Report: {REPORT_PATH}")


def prepare_dataset(strict: bool = False) -> PreparationStats:
    ensure_directories()

    stats = PreparationStats()
    stats.unsupported_files = get_unsupported_raw_files()

    input_files: list[tuple[Path, str]] = []
    input_files.extend((path, "raw") for path in get_supported_raw_files())
    input_files.extend((path, "supplemental") for path in get_supplemental_seed_files())

    raw_pairs: list[dict[str, str]] = []

    for input_path, file_kind in input_files:
        try:
            dataframe = read_supported_file(input_path)
        except Exception as error:
            stats.unreadable_files.append(f"{input_path.relative_to(PROJECT_ROOT)} ({error})")
            continue

        extracted_pairs, extraction_note = extract_pairs_from_dataframe(dataframe, input_path, stats)
        if not extracted_pairs:
            stats.no_pair_files.append(str(input_path.relative_to(PROJECT_ROOT)))
            stats.processed_files.append(
                FileSummary(
                    path=input_path,
                    file_kind=file_kind,
                    rows_loaded=len(dataframe),
                    pairs_extracted=0,
                    extraction_note=extraction_note,
                )
            )
            if file_kind == "raw":
                stats.raw_supported_files_processed += 1
            else:
                stats.supplemental_seed_files_processed += 1
            continue

        raw_pairs.extend(extracted_pairs)
        stats.processed_files.append(
            FileSummary(
                path=input_path,
                file_kind=file_kind,
                rows_loaded=len(dataframe),
                pairs_extracted=len(extracted_pairs),
                extraction_note=extraction_note,
            )
        )

        if file_kind == "raw":
            stats.raw_supported_files_processed += 1
        else:
            stats.supplemental_seed_files_processed += 1

    stats.rows_before_cleaning = len(raw_pairs)
    generated_dataframe = clean_and_filter_pairs(raw_pairs, stats)
    stats.rows_after_basic_cleaning = len(generated_dataframe)
    cleaned_dataframe, flagged_dataframe = apply_quality_filters(generated_dataframe, stats, strict=strict)
    stats.rows_after_cleaning = len(cleaned_dataframe)
    training_ready_dataframe, training_ready_review_dataframe = build_training_ready_dataset(cleaned_dataframe, stats)

    write_dataset_csv(generated_dataframe, TRAINING_DATASET_PATH)
    write_dataset_csv(cleaned_dataframe, TRAINING_DATASET_CLEAN_PATH)
    write_dataset_csv(training_ready_dataframe, TRAINING_READY_DATASET_PATH)
    write_flagged_pairs_csv(flagged_dataframe, FLAGGED_BAD_PAIRS_PATH)
    write_training_ready_review_csv(training_ready_review_dataframe, TRAINING_READY_REVIEW_PATH)
    REPORT_PATH.write_text(
        build_dataset_report(
            stats=stats,
            generated_dataframe=generated_dataframe,
            cleaned_dataframe=cleaned_dataframe,
            flagged_dataframe=flagged_dataframe,
            training_ready_dataframe=training_ready_dataframe,
            training_ready_review_dataframe=training_ready_review_dataframe,
            strict=strict,
        ),
        encoding="utf-8",
    )

    print_terminal_summary(stats, strict=strict)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare training datasets for the brainrot translator.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Apply stronger quality filters and flag suspicious translation pairs.",
    )
    args = parser.parse_args()
    prepare_dataset(strict=args.strict)


if __name__ == "__main__":
    main()
