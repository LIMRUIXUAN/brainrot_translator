from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_PATH = PROJECT_ROOT / "data" / "processed" / "brainrot_dataset.csv"
DEFAULT_CLEANED_PATH = PROJECT_ROOT / "data" / "processed" / "brainrot_dataset_cleaned.csv"
DEFAULT_REPAIRED_PATH = PROJECT_ROOT / "data" / "processed" / "brainrot_dataset_repaired.csv"
DEFAULT_REJECTED_PATH = PROJECT_ROOT / "data" / "processed" / "brainrot_dataset_rejected.csv"

SENTENCE_TRANSLATION_PREFIX = "Convert brainrot English to normal English: "
TERM_DEFINITION_PREFIX = "Define this brainrot term in normal English: "

OUTPUT_COLUMNS = ["input_text", "target_text", "task_type", "quality_label", "reason"]

INPUT_COLUMN_CANDIDATES = [
    "input_text",
    "brainrot",
    "slang",
    "text",
    "source",
    "sentence",
    "phrase",
    "term",
    "comment",
    "content",
]

TARGET_COLUMN_CANDIDATES = [
    "target_text",
    "normal",
    "meaning",
    "definition",
    "translation",
    "explanation",
    "standard_text",
    "output",
    "target",
]

TERM_COLUMN_CANDIDATES = ["term", "phrase", "slang", "brainrot"]
DEFINITION_COLUMN_CANDIDATES = ["definition", "meaning", "normal", "explanation", "translation"]
METADATA_LIKE_COLUMNS = {"source", "source_url", "source_file", "category", "context", "split", "role"}

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
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
WRAPPED_QUOTE_RE = re.compile(r'^\s*["\'](.+?)["\']\s*$')

HALLUCINATION_FILLER_PHRASES = [
    "without exaggeration",
    "i was genuinely pleased to see that",
    "i was struck by the fact that",
    "i couldn't help but notice that",
    "looking at the situation",
    "it struck me that",
    "it's remarkable how",
    "overall quality",
    "i found myself genuinely impressed by the result",
    "genuinely quite memorable",
    "everything came together remarkably well",
    "that level of quality is hard to come by",
    "what really stood out was",
    "to be perfectly honest",
    "in all honesty",
    "i think it's fair to say that",
    "frankly speaking",
    "from what i can tell",
    "i must admit",
    "i have to give credit where it's due",
    "the attention to detail was especially noteworthy",
    "the level of effort was clearly substantial",
    "the situation was rather unfortunate",
    "there was a clear sense of dedication behind it",
    "it far exceeded what i had anticipated",
    "and i think that speaks volumes",
    "in my assessment",
    "it's worth noting that",
    "it should be acknowledged that",
    "it genuinely struck me that",
    "which was honestly quite remarkable",
]

DEFINITION_STYLE_PATTERNS = [
    re.compile(r"\bused to express\b", flags=re.IGNORECASE),
    re.compile(r"\bused to describe\b", flags=re.IGNORECASE),
    re.compile(r"\bused in reference to\b", flags=re.IGNORECASE),
    re.compile(r"\bused as an insult\b", flags=re.IGNORECASE),
    re.compile(r"\bmeaning\b", flags=re.IGNORECASE),
    re.compile(r"\bmeans\b", flags=re.IGNORECASE),
    re.compile(r"\brefers to\b", flags=re.IGNORECASE),
    re.compile(r"\bderived from\b", flags=re.IGNORECASE),
    re.compile(r"\boriginated from\b", flags=re.IGNORECASE),
    re.compile(r"\boriginating from\b", flags=re.IGNORECASE),
    re.compile(r"\bpopularized by\b", flags=re.IGNORECASE),
    re.compile(r"\babbreviation for\b", flags=re.IGNORECASE),
    re.compile(r"\bacronym for\b", flags=re.IGNORECASE),
    re.compile(r"\bshort(?:\s|-)?hand of\b", flags=re.IGNORECASE),
    re.compile(r"\bshortened version of\b", flags=re.IGNORECASE),
    re.compile(r"\bvariant of\b", flags=re.IGNORECASE),
    re.compile(r"\bthe state of\b", flags=re.IGNORECASE),
    re.compile(r"\bthe term is used\b", flags=re.IGNORECASE),
    re.compile(r"\boften associated with\b", flags=re.IGNORECASE),
    re.compile(r"\binspired multiple\b", flags=re.IGNORECASE),
]

DEFINITION_SUBSTITUTION_PATTERNS = [
    re.compile(r"\bused to say\b", flags=re.IGNORECASE),
    re.compile(r"\bused to describe\b", flags=re.IGNORECASE),
    re.compile(r"\bused in reference to\b", flags=re.IGNORECASE),
    re.compile(r"\bshort(?:\s|-)?hand of\b", flags=re.IGNORECASE),
    re.compile(r"\bprimarily used to describe\b", flags=re.IGNORECASE),
]

ORIGIN_CUES = [
    "originated from",
    "originating from",
    "derived from",
    "popularized by",
    "from aave",
    "from tiktok",
    "tiktok",
    "from the meme",
    "associated with",
    "inspired by",
    "song",
]

MEANING_CUES = [
    "means",
    "refers to",
    "used to express",
    "used to describe",
    "used in reference to",
    "abbreviation for",
    "acronym for",
    "shortened version of",
    "variant of",
    "state of",
    "relationship",
    "slang term",
    "meme",
]

COMMON_BRAINROT_TERMS = {
    "67",
    "6-7",
    "6",
    "7",
    "acoustic",
    "ate",
    "aura",
    "based",
    "beige",
    "bestie",
    "bet",
    "bffr",
    "boujee",
    "brainrot",
    "bro",
    "bruh",
    "bussin",
    "cap",
    "clanker",
    "clout",
    "cooked",
    "copium",
    "cringe",
    "delulu",
    "delusionship",
    "fanum",
    "finna",
    "fire",
    "flicks",
    "fr",
    "frfr",
    "gagged",
    "gas",
    "glaze",
    "glazing",
    "goated",
    "gyatt",
    "hyped",
    "hits",
    "highkey",
    "ick",
    "imma",
    "iykyk",
    "joever",
    "lowkey",
    "lore",
    "mid",
    "npc",
    "opp",
    "periodt",
    "pulling",
    "rizz",
    "rizzed",
    "rizzing",
    "slide",
    "sigma",
    "six",
    "skibidi",
    "slaps",
    "slay",
    "slop",
    "sturdy",
    "sus",
    "tax",
    "vibe",
    "vibing",
    "yeet",
    "chillin",
    "crib",
}

COMMON_BRAINROT_PHRASES = [
    "404: sanity not found",
    "aura points",
    "beige flag",
    "fanum tax",
    "glow up",
    "green flag",
    "hits different",
    "iykyk",
    "mad busy",
    "no cap",
    "on god",
    "pulling up",
    "roman empire",
    "shoot his shot",
    "slide to",
    "six-seven",
    "skibidi toilet",
    "straight fire",
    "that girl",
    "doot doot",
]

QUESTION_WORDS = {
    "are",
    "can",
    "could",
    "did",
    "do",
    "does",
    "don't",
    "dont",
    "how",
    "is",
    "should",
    "what",
    "when",
    "where",
    "why",
    "will",
    "would",
    "you",
}

SENTENCE_STARTERS = {
    "bro",
    "bruh",
    "can",
    "did",
    "do",
    "does",
    "everyone",
    "he",
    "her",
    "his",
    "i",
    "i'm",
    "im",
    "it",
    "let",
    "my",
    "nah",
    "our",
    "she",
    "someone",
    "that",
    "the",
    "they",
    "this",
    "we",
    "when",
    "why",
    "yo",
    "you",
    "your",
}


@dataclass
class ColumnSelection:
    input_column: str
    target_column: str


@dataclass
class RowDecision:
    input_text: str
    target_text: str
    task_type: str
    quality_label: str
    reason: str
    raw_input: str
    raw_target: str
    row_index: int
    score: int


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


def normalize_for_compare(text: str) -> str:
    normalized = clean_text(text).casefold()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def count_words(text: str) -> int:
    return len(WORD_RE.findall(text))


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for token in WORD_RE.findall(text):
        normalized = token.casefold().strip("'")
        if normalized:
            tokens.append(normalized)
    return tokens


def split_sentences(text: str) -> list[str]:
    cleaned = clean_text(text)
    if not cleaned:
        return []
    chunks = SENTENCE_SPLIT_RE.split(cleaned)
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def unwrap_quotes(text: str) -> str:
    match = WRAPPED_QUOTE_RE.match(clean_text(text))
    return match.group(1).strip() if match else clean_text(text)


def ensure_terminal_punctuation(text: str) -> str:
    cleaned = clean_text(text)
    if not cleaned:
        return ""
    if cleaned[-1] in ".!?":
        return cleaned
    if cleaned.endswith('"'):
        return cleaned + "."
    return cleaned + "."


def normalize_sentence_capitalization(text: str) -> str:
    cleaned = ensure_terminal_punctuation(text)
    if not cleaned:
        return ""

    cleaned = re.sub(r"\bi\b", "I", cleaned)
    cleaned = re.sub(r"\bi'", "I'", cleaned)

    first_alpha = re.search(r"[A-Za-z]", cleaned)
    if first_alpha:
        index = first_alpha.start()
        cleaned = cleaned[:index] + cleaned[index].upper() + cleaned[index + 1 :]
    return cleaned


def build_column_lookup(dataframe: pd.DataFrame) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for column in dataframe.columns:
        normalized = re.sub(r"[^a-z0-9]+", "_", str(column).strip().lower()).strip("_")
        lookup.setdefault(normalized, column)
    return lookup


def choose_column(lookup: dict[str, str], candidates: list[str], exclude: set[str] | None = None) -> str | None:
    exclude = exclude or set()
    for candidate in candidates:
        actual = lookup.get(candidate)
        if actual and actual not in exclude:
            return actual
    return None


def detect_text_columns(dataframe: pd.DataFrame) -> ColumnSelection:
    lookup = build_column_lookup(dataframe)

    if lookup.get("input_text") and lookup.get("target_text"):
        return ColumnSelection(lookup["input_text"], lookup["target_text"])

    term_column = choose_column(lookup, TERM_COLUMN_CANDIDATES)
    definition_column = choose_column(lookup, DEFINITION_COLUMN_CANDIDATES, exclude={term_column} if term_column else None)

    input_column = choose_column(lookup, INPUT_COLUMN_CANDIDATES)
    target_column = choose_column(lookup, TARGET_COLUMN_CANDIDATES, exclude={input_column} if input_column else None)

    if (
        input_column
        and target_column
        and input_column != target_column
        and input_column.casefold() not in METADATA_LIKE_COLUMNS
        and target_column.casefold() not in METADATA_LIKE_COLUMNS
    ):
        return ColumnSelection(input_column, target_column)

    if term_column and definition_column:
        return ColumnSelection(term_column, definition_column)

    raise ValueError(
        "Could not detect usable input and target columns. "
        "Expected columns like brainrot/normal or term/definition."
    )


def is_url_only(text: str) -> bool:
    return bool(re.fullmatch(r"(?:https?://|www\.)\S+", clean_text(text), flags=re.IGNORECASE))


def has_meaningful_content(text: str) -> bool:
    return len(re.sub(r"[^A-Za-z0-9]+", "", clean_text(text))) >= 2


def looks_corrupted(text: str) -> bool:
    cleaned = clean_text(text)
    if not cleaned:
        return True
    if cleaned.startswith('",') or cleaned.startswith("',") or cleaned.endswith(',"') or cleaned.endswith(",'"):
        return True
    if "�" in cleaned:
        return True
    if cleaned.count('"') == 1:
        return True
    if not re.search(r"[A-Za-z0-9]", cleaned):
        return True
    return False


def contains_hallucination_filler(text: str) -> bool:
    lowered = clean_text(text).casefold()
    return any(phrase in lowered for phrase in HALLUCINATION_FILLER_PHRASES)


def looks_like_definition_text(text: str) -> bool:
    cleaned = clean_text(text)
    lowered = cleaned.casefold()

    if len(split_sentences(cleaned)) > 1 and any(cue in lowered for cue in ORIGIN_CUES):
        return True

    return any(pattern.search(cleaned) for pattern in DEFINITION_STYLE_PATTERNS)


def looks_like_bare_definition(text: str) -> bool:
    cleaned = clean_text(text)
    stripped = re.sub(r"^\s*\d+[.)]+\s*", "", cleaned)
    lowered = stripped.casefold()

    starters = (
        "a ",
        "an ",
        "the ",
        "to ",
        "one's ",
        "someone's ",
        "someone ",
        "something ",
        "theft ",
        "approval ",
        "charisma ",
        "confidence ",
        "a relationship ",
        "the state ",
        "niche ",
        "extremely ",
        "short for ",
    )

    if lowered.startswith(starters):
        return True
    if len(split_sentences(cleaned)) > 1 and count_words(cleaned) <= 70:
        return True
    return False


def contains_definition_substitution(text: str) -> bool:
    cleaned = clean_text(text)
    return any(pattern.search(cleaned) for pattern in DEFINITION_SUBSTITUTION_PATTERNS)


def has_emoji_or_internet_symbols(text: str) -> bool:
    cleaned = clean_text(text)
    return bool(re.search(r"[\U0001F300-\U0001FAFF💀😭✨🔥🤔😩🫠👀🙏🤌]", cleaned))


def looks_like_brainrot_or_internet_text(text: str) -> bool:
    cleaned = clean_text(text)
    lowered = cleaned.casefold()
    tokens = set(tokenize(cleaned))

    if has_emoji_or_internet_symbols(cleaned):
        return True
    if any(term in tokens for term in COMMON_BRAINROT_TERMS):
        return True
    if any(phrase in lowered for phrase in COMMON_BRAINROT_PHRASES):
        return True
    if re.search(r"\b(?:fr|frfr|ngl|rn|tbh|idk|lmao|lmfao|pls|iykyk|af)\b", lowered):
        return True
    if re.search(r"[!?]{2,}|\.{2,}|[A-Z]{3,}", cleaned):
        return True
    if re.search(r"\b(?:404|500|1000|2000|5000|10000)\b", lowered):
        return True
    if ":" in cleaned and re.search(r"\b404\b", lowered):
        return True
    return False


def looks_like_sentence_input(text: str) -> bool:
    cleaned = clean_text(text)
    lowered = cleaned.casefold()
    words = tokenize(cleaned)

    if not words:
        return False

    if len(words) >= 5:
        return True
    if any(mark in cleaned for mark in "?!,") and len(words) >= 2:
        return True
    if has_emoji_or_internet_symbols(cleaned) and len(words) >= 2:
        return True
    if words[0] in SENTENCE_STARTERS and len(words) >= 2:
        return True
    if words[0] in QUESTION_WORDS and cleaned.endswith("?"):
        return True
    if re.search(r"\b(?:is|are|am|was|were|got|gets|keep|keeps|went|goes|go|saying|say|said|tried|trying|walked|walking|forgot|forget|stayed|stay|moved|moving)\b", lowered):
        return True
    if len(cleaned) >= 35 and len(words) >= 4:
        return True
    return False


def looks_like_term_input(text: str) -> bool:
    cleaned = clean_text(text)
    words = tokenize(cleaned)

    if not words:
        return False
    if looks_like_sentence_input(cleaned):
        return False
    if len(words) <= 8:
        return True
    return False


def input_is_too_plain_for_training(text: str) -> bool:
    cleaned = clean_text(text)
    if looks_like_term_input(cleaned):
        return False
    if looks_like_brainrot_or_internet_text(cleaned):
        return False
    if count_words(cleaned) <= 6:
        return True
    return False


def classify_task_type(source_text: str, target_text: str) -> str:
    sentence_like = looks_like_sentence_input(source_text)
    term_like = looks_like_term_input(source_text)
    definition_like = looks_like_definition_text(target_text)
    bare_definition_like = looks_like_bare_definition(target_text)

    if (definition_like or bare_definition_like) and term_like and not sentence_like:
        return "term_definition"
    return "sentence_translation"


def extract_quoted_translation(definition_text: str) -> str | None:
    cleaned = clean_text(definition_text)

    shorthand_match = re.search(
        r'short(?:\s|-)?hand of the usual\s+"([^"]+)"',
        cleaned,
        flags=re.IGNORECASE,
    )
    if shorthand_match:
        return normalize_sentence_capitalization(shorthand_match.group(1))

    quoted_question = re.search(r'"([^"]+\?)"', cleaned)
    if quoted_question:
        return normalize_sentence_capitalization(quoted_question.group(1))

    return None


def repair_simple_definition_substitution(target_text: str) -> str | None:
    cleaned = clean_text(target_text)

    used_to_say_match = re.match(
        r"^(.+?\bis)\s+used to say(?: something)?\s+is\s+([^.!?]+)",
        cleaned,
        flags=re.IGNORECASE,
    )
    if used_to_say_match:
        subject = used_to_say_match.group(1).strip()
        gloss = used_to_say_match.group(2).strip().strip('"')
        return normalize_sentence_capitalization(f"{subject} {gloss}")

    return None


def repair_sentence_translation(source_text: str, target_text: str) -> tuple[str, str, str]:
    cleaned_target = clean_text(target_text)

    if contains_hallucination_filler(cleaned_target):
        return "", "rejected", "hallucinated_target"

    direct_translation = extract_quoted_translation(cleaned_target)
    if direct_translation:
        return direct_translation, "repaired", "repaired_phrase_definition_into_translation"

    substitution_repair = repair_simple_definition_substitution(cleaned_target)
    if substitution_repair:
        return substitution_repair, "repaired", "repaired_definition_substitution_sentence"

    if contains_definition_substitution(cleaned_target):
        return "", "rejected", "definition_substitution_in_sentence_target"

    if looks_like_definition_text(cleaned_target):
        return "", "rejected", "definition_style_target_for_sentence"

    return normalize_sentence_capitalization(cleaned_target), "keep", "kept_sentence_translation"


def score_definition_sentence(sentence: str) -> int:
    lowered = clean_text(sentence).casefold()
    score = 0

    if any(cue in lowered for cue in MEANING_CUES):
        score += 4
    if lowered.startswith(("a ", "an ", "the ", "someone ", "something ", "one's ", "to ")):
        score += 3
    if any(cue in lowered for cue in ORIGIN_CUES):
        score -= 2
    if "the term is used" in lowered:
        score -= 3
    if "similar to" in lowered or "alternative forms include" in lowered:
        score -= 1
    if count_words(sentence) > 30:
        score -= 1
    return score


def sentence_to_meaning_fragment(sentence: str) -> str:
    cleaned = clean_text(sentence).strip()
    lowered = cleaned.casefold()

    replacements: list[tuple[re.Pattern[str], str]] = [
        (re.compile(r"^meaning\s+", flags=re.IGNORECASE), ""),
        (re.compile(r"^refers to\s+", flags=re.IGNORECASE), ""),
        (re.compile(r"^used to express\s+", flags=re.IGNORECASE), "an expression of "),
        (re.compile(r"^used to describe\s+", flags=re.IGNORECASE), ""),
        (re.compile(r"^used in reference to\s+", flags=re.IGNORECASE), ""),
        (re.compile(r"^used as an insult to\s+", flags=re.IGNORECASE), "an insult used to describe "),
        (re.compile(r"^shortened version of\s+", flags=re.IGNORECASE), 'a shortened form of '),
        (re.compile(r"^a variant of the word\s+", flags=re.IGNORECASE), "a variant of "),
        (re.compile(r"^a variant of\s+", flags=re.IGNORECASE), "a variant of "),
        (re.compile(r"^commonly used to mean\s+", flags=re.IGNORECASE), ""),
        (re.compile(r"^effectively\s+", flags=re.IGNORECASE), ""),
    ]

    for pattern, replacement in replacements:
        cleaned = pattern.sub(replacement, cleaned, count=1)

    if re.match(r"^\s*1[.)]+\s*", cleaned):
        cleaned = re.sub(r"^\s*1[.)]+\s*", "", cleaned)
        cleaned = re.split(r"\s+\d+[.)]+\s*", cleaned, maxsplit=1)[0]

    cleaned = re.sub(r"^\s*one's\s+", "someone's ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*/\s*", " or ", cleaned)
    cleaned = cleaned.strip().strip(".")
    if re.match(r"^(A|An|The|To|Pejorative|Combined)\b", cleaned):
        cleaned = cleaned[0].lower() + cleaned[1:]
    elif re.match(r"^[A-Z][a-z]", cleaned):
        cleaned = cleaned[0].lower() + cleaned[1:]
    if cleaned.startswith("pejorative term"):
        cleaned = "a " + cleaned
    if cleaned.startswith("combined form of"):
        cleaned = "a " + cleaned
    cleaned = re.sub(
        r"^someone's charm(?:\s+or\s+|\s*/\s*)seduction skills$",
        "charisma or flirting ability",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r'^to\s+"?be\s+[^"]+"?\s+is\s+to\s+be\s+(.+)$',
        r"to be \1",
        cleaned,
        flags=re.IGNORECASE,
    )

    if cleaned.casefold().startswith("derived from "):
        cleaned = "a term derived from " + cleaned[13:].strip()
    if cleaned.casefold().startswith("originated from "):
        cleaned = "a term that originated from " + cleaned[16:].strip()

    if lowered.startswith("abbreviation for "):
        match = re.match(r'^abbreviation for\s+"?([^":]+)"?(?::\s*(.+))?$', cleaned, flags=re.IGNORECASE)
        if match:
            expanded = unwrap_quotes(match.group(1))
            detail = clean_text(match.group(2) or "")
            if detail:
                return f'an abbreviation for "{expanded}" meaning {detail.strip(".")}'
            return f'an abbreviation for "{expanded}"'

    if lowered.startswith("acronym for "):
        match = re.match(r'^acronym for\s+"?([^":]+)"?(?::\s*(.+))?$', cleaned, flags=re.IGNORECASE)
        if match:
            expanded = unwrap_quotes(match.group(1))
            detail = clean_text(match.group(2) or "")
            if detail:
                return f'an acronym for "{expanded}" meaning {detail.strip(".")}'
            return f'an acronym for "{expanded}"'

    return cleaned


def format_term_for_sentence(term: str) -> str:
    cleaned = unwrap_quotes(term)
    if not cleaned:
        return ""
    if re.search(r"[A-Za-z]", cleaned):
        return cleaned[0].upper() + cleaned[1:]
    return cleaned


def build_origin_sentence(term: str, definition_text: str) -> str:
    cleaned = clean_text(definition_text)
    lowered = cleaned.casefold()
    display_term = format_term_for_sentence(term)

    song_match = re.search(
        r'song\s+"?([^"]+?)"?\s+by\s+([A-Za-z0-9 &\'-]+)',
        cleaned,
        flags=re.IGNORECASE,
    )
    song_phrase = ""
    if song_match:
        song_title = clean_text(song_match.group(1))
        artist = clean_text(song_match.group(2))
        if song_title and artist:
            song_phrase = f'the song "{song_title}" by {artist}'

    if "nonsense word" in lowered or "no real meaning" in lowered or "no fixed meaning" in lowered:
        if song_phrase and "tiktok" in lowered:
            return (
                f"{display_term} is a viral meme term associated with {song_phrase} and TikTok meme culture, "
                "and it usually does not have a fixed literal meaning."
            )
        if "skibidi toilet" in lowered:
            return (
                f"{display_term} is a meme-based slang term derived from the Skibidi Toilet meme, "
                "and it usually does not have a fixed literal meaning."
            )
        if "tiktok" in lowered:
            return (
                f"{display_term} is a viral meme term from TikTok culture that usually does not have a fixed literal meaning."
            )
        return f"{display_term} is a meme-based slang term that usually does not have a fixed literal meaning."

    origin_bits: list[str] = []
    if song_phrase:
        origin_bits.append(f"the term is associated with {song_phrase}")
    if "tiktok" in lowered:
        origin_bits.append("it spread through TikTok meme culture")
    if "from aave" in lowered:
        origin_bits.append("it comes from AAVE")
    if "popularized by" in lowered:
        popularized_match = re.search(r"popularized by\s+([^.;]+)", cleaned, flags=re.IGNORECASE)
        if popularized_match:
            origin_bits.append(f'it was popularized by {clean_text(popularized_match.group(1)).strip(".")}')
    if "derived from charisma" in lowered:
        origin_bits.append('the term comes from the word "charisma"')
    if "originated from rapper lil b" in lowered:
        origin_bits.append("the modern slang use grew after rapper Lil B popularized it")

    if not origin_bits:
        return ""

    origin_text = "; ".join(origin_bits)
    origin_text = origin_text[0].upper() + origin_text[1:]
    return ensure_terminal_punctuation(origin_text)


def repair_term_definition(term: str, definition_text: str) -> tuple[str, str, str]:
    cleaned_definition = clean_text(definition_text)
    cleaned_definition = cleaned_definition.replace("beleaguerment", "being worn out or exhausted")
    cleaned_definition = cleaned_definition.replace("short hand", "shorthand")

    if contains_hallucination_filler(cleaned_definition):
        return "", "rejected", "hallucinated_term_definition"

    special_origin_sentence = build_origin_sentence(term, cleaned_definition)
    if special_origin_sentence and (
        "does not have a fixed literal meaning" in special_origin_sentence
        or 'associated with the song "' in special_origin_sentence
    ):
        return special_origin_sentence, "repaired", "repaired_term_definition_from_origin_notes"

    candidate_sentences = split_sentences(cleaned_definition)
    if not candidate_sentences:
        return "", "rejected", "empty_definition"

    meaning_sentence = max(candidate_sentences, key=score_definition_sentence)
    meaning_fragment = sentence_to_meaning_fragment(meaning_sentence)
    meaning_fragment = clean_text(meaning_fragment).strip().strip(".")

    if not meaning_fragment:
        return "", "rejected", "empty_repaired_definition"

    display_term = format_term_for_sentence(term)
    lowered_fragment = meaning_fragment.casefold()

    noun_like_starts = (
        "a ",
        "an ",
        "the ",
        "someone ",
        "something ",
        "a slang ",
        "an expression ",
        "a phrase ",
        "a meme ",
        "a pejorative ",
        "a combined ",
        "the state ",
        "someone's ",
        "an acronym ",
        "an abbreviation ",
        "a shortened form ",
        "a variant ",
    )

    if lowered_fragment.startswith(noun_like_starts):
        target_text = f"{display_term} is {meaning_fragment}"
    else:
        target_text = f"{display_term} means {meaning_fragment}"

    origin_sentence = special_origin_sentence if special_origin_sentence else build_origin_sentence(term, cleaned_definition)
    if origin_sentence and origin_sentence.casefold() not in target_text.casefold():
        target_text = ensure_terminal_punctuation(target_text) + " " + origin_sentence
    else:
        target_text = ensure_terminal_punctuation(target_text)

    normalized_original = normalize_for_compare(cleaned_definition)
    normalized_repaired = normalize_for_compare(target_text)
    quality_label = "keep" if normalized_original == normalized_repaired else "repaired"
    reason = "kept_term_definition" if quality_label == "keep" else "repaired_term_definition"
    return target_text, quality_label, reason


def build_prompt(task_type: str, source_text: str) -> str:
    if task_type == "sentence_translation":
        return SENTENCE_TRANSLATION_PREFIX + clean_text(source_text)
    return TERM_DEFINITION_PREFIX + clean_text(source_text)


def score_row(decision: RowDecision) -> int:
    score = 100
    if decision.quality_label == "keep":
        score += 5
    if decision.task_type == "sentence_translation":
        score += min(count_words(decision.target_text), 25)
    else:
        score += 10
        if any(cue in decision.target_text.casefold() for cue in ORIGIN_CUES):
            score += 2
    if contains_hallucination_filler(decision.target_text):
        score -= 50
    score -= max(count_words(decision.target_text) - 55, 0)
    return score


def reject_row(source_text: str, target_text: str, reason: str, row_index: int) -> RowDecision:
    return RowDecision(
        input_text="",
        target_text="",
        task_type="rejected",
        quality_label="rejected",
        reason=reason,
        raw_input=clean_text(source_text),
        raw_target=clean_text(target_text),
        row_index=row_index,
        score=0,
    )


def classify_and_repair_row(source_text: Any, target_text: Any, row_index: int) -> RowDecision:
    source = clean_text(source_text)
    target = clean_text(target_text)

    if not source or not target:
        return reject_row(source, target, "empty_input_or_target", row_index)
    if is_url_only(source) or is_url_only(target):
        return reject_row(source, target, "url_only_row", row_index)
    if not has_meaningful_content(source) or not has_meaningful_content(target):
        return reject_row(source, target, "missing_meaningful_text", row_index)
    if looks_corrupted(source) or looks_corrupted(target):
        return reject_row(source, target, "corrupted_text", row_index)
    if contains_hallucination_filler(target):
        return reject_row(source, target, "hallucinated_target", row_index)

    task_type = classify_task_type(source, target)

    if task_type == "sentence_translation":
        repaired_target, quality_label, reason = repair_sentence_translation(source, target)
        if not repaired_target:
            return reject_row(source, target, reason, row_index)
        if quality_label == "keep" and input_is_too_plain_for_training(source):
            return reject_row(source, target, "input_not_brainrot_or_internet_style", row_index)
    else:
        repaired_target, quality_label, reason = repair_term_definition(source, target)
        if not repaired_target:
            return reject_row(source, target, reason, row_index)

    decision = RowDecision(
        input_text=build_prompt(task_type, source),
        target_text=repaired_target,
        task_type=task_type,
        quality_label=quality_label,
        reason=reason,
        raw_input=source,
        raw_target=target,
        row_index=row_index,
        score=0,
    )
    decision.score = score_row(decision)
    return decision


def rows_are_near_duplicates(left: RowDecision, right: RowDecision) -> bool:
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


def deduplicate_decisions(decisions: list[RowDecision]) -> tuple[list[RowDecision], list[RowDecision], int]:
    useful = [decision for decision in decisions if decision.quality_label != "rejected"]
    rejected = [decision for decision in decisions if decision.quality_label == "rejected"]

    duplicate_rows: list[RowDecision] = []

    exact_lookup: dict[tuple[str, str], RowDecision] = {}
    for decision in useful:
        key = (normalize_for_compare(decision.input_text), normalize_for_compare(decision.target_text))
        existing = exact_lookup.get(key)
        if existing is None:
            exact_lookup[key] = decision
            continue
        preferred, duplicate = sorted([existing, decision], key=lambda item: item.score, reverse=True)
        exact_lookup[key] = preferred
        duplicate_rows.append(reject_row(duplicate.raw_input, duplicate.raw_target, "duplicate_exact_pair", duplicate.row_index))

    final_rows: list[RowDecision] = []
    grouped_by_input: dict[str, list[RowDecision]] = {}
    for decision in exact_lookup.values():
        grouped_by_input.setdefault(normalize_for_compare(decision.input_text), []).append(decision)

    for _, group in sorted(grouped_by_input.items(), key=lambda item: item[0]):
        local_kept: list[RowDecision] = []
        for decision in sorted(group, key=lambda item: (-item.score, item.row_index)):
            match_index = next(
                (index for index, existing in enumerate(local_kept) if rows_are_near_duplicates(existing, decision)),
                None,
            )
            if match_index is None:
                local_kept.append(decision)
                continue

            existing = local_kept[match_index]
            preferred, duplicate = sorted([existing, decision], key=lambda item: item.score, reverse=True)
            local_kept[match_index] = preferred
            duplicate_rows.append(reject_row(duplicate.raw_input, duplicate.raw_target, "duplicate_near_pair", duplicate.row_index))
        final_rows.extend(sorted(local_kept, key=lambda item: item.row_index))

    return final_rows, rejected + duplicate_rows, len(duplicate_rows)


def decisions_to_dataframe(decisions: list[RowDecision], include_raw_for_rejected: bool = False) -> pd.DataFrame:
    rows: list[dict[str, str]] = []
    for decision in decisions:
        if decision.quality_label == "rejected":
            input_text = decision.raw_input if include_raw_for_rejected else ""
            target_text = decision.raw_target if include_raw_for_rejected else ""
            task_type = "rejected"
        else:
            input_text = decision.input_text
            target_text = decision.target_text
            task_type = decision.task_type

        rows.append(
            {
                "input_text": input_text,
                "target_text": target_text,
                "task_type": task_type,
                "quality_label": decision.quality_label,
                "reason": decision.reason,
            }
        )
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS)


def filter_training_dataframe(dataframe: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, int]]:
    if dataframe.empty:
        empty = pd.DataFrame(columns=OUTPUT_COLUMNS)
        return empty, empty.copy(), empty.copy(), {
            "original_row_count": 0,
            "cleaned_row_count": 0,
            "repaired_row_count": 0,
            "rejected_row_count": 0,
            "duplicate_count": 0,
            "sentence_translation_count": 0,
            "term_definition_count": 0,
        }

    column_selection = detect_text_columns(dataframe.fillna(""))

    decisions = [
        classify_and_repair_row(row[column_selection.input_column], row[column_selection.target_column], row_index=index)
        for index, row in dataframe.fillna("").iterrows()
    ]

    cleaned_decisions, rejected_decisions, duplicate_count = deduplicate_decisions(decisions)

    cleaned_dataframe = decisions_to_dataframe(cleaned_decisions)
    cleaned_dataframe = cleaned_dataframe.sort_values(["task_type", "quality_label", "input_text"]).reset_index(drop=True)

    repaired_dataframe = cleaned_dataframe[cleaned_dataframe["quality_label"] == "repaired"].reset_index(drop=True)
    rejected_dataframe = decisions_to_dataframe(rejected_decisions, include_raw_for_rejected=True).reset_index(drop=True)

    summary = {
        "original_row_count": len(dataframe),
        "cleaned_row_count": len(cleaned_dataframe),
        "repaired_row_count": len(repaired_dataframe),
        "rejected_row_count": len(rejected_dataframe),
        "duplicate_count": duplicate_count,
        "sentence_translation_count": int((cleaned_dataframe["task_type"] == "sentence_translation").sum()),
        "term_definition_count": int((cleaned_dataframe["task_type"] == "term_definition").sum()),
    }

    return cleaned_dataframe, repaired_dataframe, rejected_dataframe, summary


def write_output_csv(dataframe: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_csv(output_path, index=False, encoding="utf-8")


def format_examples(dataframe: pd.DataFrame, title: str, limit: int = 10) -> list[str]:
    lines = [title]
    sample = dataframe.head(limit)
    if sample.empty:
        lines.append("- none")
        return lines

    for _, row in sample.iterrows():
        lines.append(f"- {row['input_text']} -> {row['target_text']}")
    return lines


def format_rejected_examples(dataframe: pd.DataFrame, title: str, limit: int = 10) -> list[str]:
    lines = [title]
    sample = dataframe.head(limit)
    if sample.empty:
        lines.append("- none")
        return lines

    for _, row in sample.iterrows():
        lines.append(f"- {row['input_text']} -> {row['target_text']} [{row['reason']}]")
    return lines


def safe_print(text: str = "") -> None:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    display_text = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
    print(display_text)


def print_summary(
    summary: dict[str, int],
    cleaned_dataframe: pd.DataFrame,
    repaired_dataframe: pd.DataFrame,
    rejected_dataframe: pd.DataFrame,
    input_path: Path,
    cleaned_path: Path,
    repaired_path: Path,
    rejected_path: Path,
) -> None:
    rejection_counts = Counter(rejected_dataframe["reason"].tolist())

    safe_print(f"Input dataset: {input_path}")
    safe_print(f"Cleaned dataset: {cleaned_path}")
    safe_print(f"Repaired dataset: {repaired_path}")
    safe_print(f"Rejected dataset: {rejected_path}")
    safe_print()
    safe_print("Summary report")
    safe_print(f"- Original row count: {summary['original_row_count']}")
    safe_print(f"- Cleaned row count: {summary['cleaned_row_count']}")
    safe_print(f"- Repaired row count: {summary['repaired_row_count']}")
    safe_print(f"- Rejected row count: {summary['rejected_row_count']}")
    safe_print(f"- Duplicate count: {summary['duplicate_count']}")
    safe_print(f"- Sentence translation count: {summary['sentence_translation_count']}")
    safe_print(f"- Term definition count: {summary['term_definition_count']}")
    safe_print()
    safe_print("Top rejection reasons")
    if rejection_counts:
        for reason, count in rejection_counts.most_common(10):
            safe_print(f"- {reason}: {count}")
    else:
        safe_print("- none")
    safe_print()

    sentence_rows = cleaned_dataframe[cleaned_dataframe["task_type"] == "sentence_translation"].reset_index(drop=True)
    term_rows = cleaned_dataframe[cleaned_dataframe["task_type"] == "term_definition"].reset_index(drop=True)

    for line in format_examples(sentence_rows, "10 sentence_translation examples"):
        safe_print(line)
    safe_print()
    for line in format_examples(term_rows, "10 term_definition examples"):
        safe_print(line)
    safe_print()
    for line in format_rejected_examples(rejected_dataframe, "10 rejected examples"):
        safe_print(line)
    safe_print()
    if not repaired_dataframe.empty:
        safe_print("10 repaired examples")
        for _, row in repaired_dataframe.head(10).iterrows():
            safe_print(f"- {row['input_text']} -> {row['target_text']} [{row['reason']}]")


def run_pipeline(
    input_path: Path,
    cleaned_path: Path,
    repaired_path: Path,
    rejected_path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, int]]:
    dataframe = pd.read_csv(input_path).fillna("")
    cleaned_dataframe, repaired_dataframe, rejected_dataframe, summary = filter_training_dataframe(dataframe)

    write_output_csv(cleaned_dataframe, cleaned_path)
    write_output_csv(repaired_dataframe, repaired_path)
    write_output_csv(rejected_dataframe, rejected_path)

    print_summary(
        summary=summary,
        cleaned_dataframe=cleaned_dataframe,
        repaired_dataframe=repaired_dataframe,
        rejected_dataframe=rejected_dataframe,
        input_path=input_path,
        cleaned_path=cleaned_path,
        repaired_path=repaired_path,
        rejected_path=rejected_path,
    )

    return cleaned_dataframe, repaired_dataframe, rejected_dataframe, summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Filter the brainrot translator dataset into FLAN-T5-ready sentence translation and "
            "term definition tasks."
        )
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH, help="Input CSV to inspect.")
    parser.add_argument("--cleaned-output", type=Path, default=DEFAULT_CLEANED_PATH, help="Output CSV for kept and repaired rows.")
    parser.add_argument("--repaired-output", type=Path, default=DEFAULT_REPAIRED_PATH, help="Output CSV for repaired rows only.")
    parser.add_argument("--rejected-output", type=Path, default=DEFAULT_REJECTED_PATH, help="Output CSV for rejected rows.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_pipeline(
        input_path=args.input,
        cleaned_path=args.cleaned_output,
        repaired_path=args.repaired_output,
        rejected_path=args.rejected_output,
    )


if __name__ == "__main__":
    main()
