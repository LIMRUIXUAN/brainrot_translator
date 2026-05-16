from __future__ import annotations

import argparse
import csv
import json
import re
import time
from datetime import date
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup, Tag

if __package__:
    from .db.mongodb_insert import insert_records
else:
    from db.mongodb_insert import insert_records


SOURCE_NAME = "Wikipedia - Glossary of 2020s slang"
SOURCE_URL = "https://en.wikipedia.org/wiki/Glossary_of_2020s_slang"
CATEGORY = "Gen-Z slang"
DEFAULT_JSON_OUTPUT = Path("data/processed/slang_terms.json")
DEFAULT_CSV_OUTPUT = Path("data/processed/slang_terms.csv")
REQUEST_DELAY_SECONDS = 1.5


def load_html(input_path: Path, fetch_latest: bool = False) -> str:
    """Load HTML from a local file, or fetch Wikipedia only when requested."""
    if input_path.exists() and not fetch_latest:
        print(f"Loaded local HTML file: {input_path}")
        return input_path.read_text(encoding="utf-8", errors="replace")

    if not fetch_latest and not input_path.exists():
        raise FileNotFoundError(
            f"Input file not found: {input_path}. Provide a local Wikipedia HTML file "
            "or rerun with --fetch-latest."
        )

    print("Fetching latest Wikipedia HTML with a conservative one-request delay...")
    time.sleep(REQUEST_DELAY_SECONDS)
    response = requests.get(
        SOURCE_URL,
        headers={"User-Agent": "GenZSlangResearchProject/1.0 (academic data pipeline)"},
        timeout=10,
    )
    response.raise_for_status()

    input_path.parent.mkdir(parents=True, exist_ok=True)
    input_path.write_text(response.text, encoding="utf-8")
    print(f"Saved fetched HTML to: {input_path}")
    return response.text


def clean_text(value: str) -> str:
    """Normalize Wikipedia text while removing citation markers and boilerplate labels."""
    value = re.sub(r"\[\s*(?:\d+|[a-z]|citation needed|unreliable source\?|better source needed)\s*\]", "", value, flags=re.I)
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"\s+([,.;:!?%)\]])", r"\1", value)

    def clean_quoted(match: re.Match[str]) -> str:
        quote = match.group(1)
        inner = re.sub(r"\s+", " ", match.group(2)).strip()
        inner = re.sub(r"\s+([,.;:!?])", r"\1", inner)
        closing_quote = "”" if quote == "“" else quote
        return f"{quote}{inner}{closing_quote}"

    value = re.sub(r"([\"'])(.*?)\1", clean_quoted, value)
    value = re.sub(r"(“)(.*?)”", clean_quoted, value)
    return value.strip()


def clean_term(value: str) -> str:
    """Clean a glossary term without changing its meaningful spelling."""
    value = clean_text(value)
    value = re.sub(r"\s*\([^)]*ⓘ[^)]*\)", "", value)
    value = re.sub(r"\s*\([^)]*/[^)]*\)", "", value)
    return value.strip(" :;-")


def prepare_soup(html: str) -> BeautifulSoup:
    """Create a soup object and remove Wikipedia elements that are not glossary data."""
    soup = BeautifulSoup(html, "html.parser")
    for selector in [
        "script",
        "style",
        "sup.reference",
        "span.mw-editsection",
        "table.navbox",
        "table.metadata",
        "div.reflist",
        "div.mw-references-wrap",
        ".noprint",
    ]:
        for element in soup.select(selector):
            element.decompose()
    return soup


def get_content_root(soup: BeautifulSoup) -> Tag:
    """Find the most likely article body across common Wikipedia HTML variants."""
    for selector in ["main", "div.mw-parser-output", "div#bodyContent", "body"]:
        root = soup.select_one(selector)
        if root is not None:
            return root
    return soup


def is_glossary_section_heading(text: str) -> bool:
    """Return True for A-Z glossary headings and False for notes/references."""
    return bool(re.fullmatch(r"[A-Z]", text.strip()))


def is_inside_glossary_section(tag: Tag) -> bool:
    """Check whether a tag belongs to one of the A-Z glossary sections."""
    for previous in tag.find_all_previous(["h2", "h3"]):
        heading_text = clean_text(previous.get_text(" ", strip=True))
        if is_glossary_section_heading(heading_text):
            return True
        if heading_text.lower() in {"notes", "references", "further reading"}:
            return False
    return False


def extract_example(meaning: str) -> str:
    """Extract a simple example sentence when the definition explicitly provides one."""
    patterns = [
        r"(?:e\.g\.|ex:|example:)\s*([^.;]+[.;]?)",
        r"often used in phrases? like\s+[\"'“”]?([^.;\"'“”]+)[\"'“”]?",
    ]
    for pattern in patterns:
        match = re.search(pattern, meaning, flags=re.I)
        if match:
            return clean_text(match.group(1))
    return ""


def build_record(term: str, meaning: str, collected_at: str) -> dict[str, str]:
    """Build the normalized record used by JSON, CSV, and optional database inserts."""
    return {
        "term": term,
        "meaning": meaning,
        "example": extract_example(meaning),
        "source": SOURCE_NAME,
        "source_url": SOURCE_URL,
        "category": CATEGORY,
        "collected_at": collected_at,
    }


def parse_definition_lists(root: Tag, collected_at: str) -> list[dict[str, str]]:
    """Parse glossary entries from dt/dd structures when present."""
    records: list[dict[str, str]] = []

    for term_tag in root.find_all("dt"):
        if not is_inside_glossary_section(term_tag):
            continue

        term = clean_term(term_tag.get_text(" ", strip=True))
        if not term or term.lower() == "edit":
            continue

        definitions: list[str] = []
        for sibling in term_tag.find_next_siblings():
            if not isinstance(sibling, Tag):
                continue
            if sibling.name == "dt":
                break
            if sibling.name == "dd":
                text = clean_text(sibling.get_text(" ", strip=True))
                if text:
                    definitions.append(text)

        meaning = clean_text(" ".join(definitions))
        if meaning:
            records.append(build_record(term, meaning, collected_at))

    return records


def parse_plain_text_fallback(root: Tag, collected_at: str) -> list[dict[str, str]]:
    """Fallback parser for source HTML variants where dt/dd tags are unavailable."""
    records: list[dict[str, str]] = []
    lines = [clean_text(line) for line in root.get_text("\n", strip=True).splitlines()]
    lines = [line for line in lines if line and line.lower() not in {"edit", "contents:"}]

    in_glossary = False
    index = 0
    while index < len(lines) - 1:
        line = lines[index]
        next_line = lines[index + 1]

        if is_glossary_section_heading(line):
            in_glossary = True
            index += 1
            continue
        if line.lower() in {"notes", "references", "further reading"}:
            break
        if not in_glossary:
            index += 1
            continue

        looks_like_term = len(line) <= 80 and not line.endswith(".")
        looks_like_definition = len(next_line) > 20 and next_line.endswith((".", "]", ")"))
        if looks_like_term and looks_like_definition:
            records.append(build_record(clean_term(line), next_line, collected_at))
            index += 2
            continue

        index += 1

    return records


def deduplicate_records(records: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    """Keep one record per term, preferring the clearest available meaning."""
    by_term: dict[str, dict[str, str]] = {}
    for record in records:
        term_key = record["term"].casefold()
        if not term_key or not record["meaning"]:
            continue

        existing = by_term.get(term_key)
        if existing is None or len(record["meaning"]) > len(existing["meaning"]):
            by_term[term_key] = record

    return sorted(by_term.values(), key=lambda item: item["term"].casefold())


def extract_slang_terms(html: str, collected_at: str | None = None) -> list[dict[str, str]]:
    """Extract normalized slang records from Wikipedia HTML."""
    soup = prepare_soup(html)
    root = get_content_root(soup)
    collected_at = collected_at or date.today().isoformat()

    records = parse_definition_lists(root, collected_at)
    if not records:
        records = parse_plain_text_fallback(root, collected_at)

    return deduplicate_records(records)


def save_outputs(
    records: list[dict[str, str]],
    json_output: Path = DEFAULT_JSON_OUTPUT,
    csv_output: Path = DEFAULT_CSV_OUTPUT,
) -> None:
    """Save records as a JSON array and CSV table."""
    json_output.parent.mkdir(parents=True, exist_ok=True)
    csv_output.parent.mkdir(parents=True, exist_ok=True)

    json_output.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    fieldnames = ["term", "meaning", "example", "source", "source_url", "category", "collected_at"]
    with csv_output.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    print(f"Saved JSON to {json_output}")
    print(f"Saved CSV to {csv_output}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract slang terms from Wikipedia glossary HTML.")
    parser.add_argument("--input", required=True, help="Path to the local Wikipedia HTML source file.")
    parser.add_argument("--json-output", default=str(DEFAULT_JSON_OUTPUT), help="Output JSON file path.")
    parser.add_argument("--csv-output", default=str(DEFAULT_CSV_OUTPUT), help="Output CSV file path.")
    parser.add_argument(
        "--fetch-latest",
        action="store_true",
        help="Fetch the latest Wikipedia page and save it to --input before parsing.",
    )
    parser.add_argument(
        "--insert-mongodb",
        action="store_true",
        help="Optionally insert records into MongoDB when MONGODB_URI is configured.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)

    try:
        html = load_html(input_path, fetch_latest=args.fetch_latest)
        records = extract_slang_terms(html)
    except Exception as exc:
        raise SystemExit(f"Failed to extract Wikipedia slang data: {exc}") from exc

    if not records:
        raise SystemExit(
            "No slang terms were found. The parser may need adjustment for this "
            "Wikipedia HTML structure."
        )

    print(f"Extracted {len(records)} slang terms")
    save_outputs(records, Path(args.json_output), Path(args.csv_output))

    if args.insert_mongodb:
        inserted_count = insert_records(records)
        if inserted_count:
            print(f"Inserted or updated {inserted_count} records in MongoDB")


if __name__ == "__main__":
    main()
