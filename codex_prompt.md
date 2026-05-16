# Codex Prompt - Gen-Z Slang Semantic Drift Pipeline

This file is the active project roadmap and execution guide. Future Codex runs should use it to understand what is already done, what should happen next, and which work is intentionally out of scope for now.

## Project Goal

Build a realistic, legal, reproducible data pipeline for linguistic analysis of:

- Gen-Z slang
- Internet slang
- Meme language
- Short-form platform language
- Emerging usage patterns and semantic drift

The project should support the full data lifecycle:

- Data collection
- Cleaning and filtering
- Dataset normalization
- Unified storage
- Slang matching
- Basic analysis
- Later visualization and semantic drift analysis

Prioritize maintainability, reproducibility, ethical data handling, and platform compliance over maximum data volume.

## Ethical And Legal Rules

All future work must follow these rules:

- Only collect public data.
- Do not collect private messages.
- Do not collect deleted, removed, restricted, or access-controlled content.
- Do not store unnecessary personal information.
- Remove or anonymize usernames where possible.
- Respect each platform's terms of service.
- Use official APIs whenever possible.
- Add rate limiting to every live data collector.
- Preserve enough provenance for reproducibility without keeping unnecessary identifiers.
- Keep live API work separate from offline transformation and analysis.
- Make the pipeline testable without live API credentials.
- Reddit scraping is out of scope unless official Reddit API approval is granted.

## Current Completed Work

Do not restart Wikipedia or Hugging Face work from scratch unless the user explicitly asks.

### Phase 1: Wikipedia Seed Extraction - Completed

Implemented files:

- `src/extract_wikipedia_slang.py`
- `src/db/` — database integration helpers (do not modify unless explicitly asked)

The extractor parses the Wikipedia Glossary of 2020s slang from a local HTML source and extracts:

```text
term, meaning, example, source, source_url, category, collected_at
```

Generated outputs:

- `data/processed/slang_terms.csv`
- `data/processed/slang_terms.json`

The Wikipedia glossary is a seed slang dictionary and reference source. Future Wikipedia work should be parser maintenance, schema changes, or bug fixes only.

### Phase 2: Hugging Face Dataset Normalization - Completed

Implemented in:

- `notebooks/dataset_huggingface.ipynb`

Completed behavior:

- Normalizes public Hugging Face slang / Gen-Z / informal language datasets.
- Removes the useless `record_id` field.
- Keeps `standard_text` only when truly provided by paired datasets.
- Does not generate or invent standard translations.

Generated outputs:

- `data/processed/huggingface_slang_dataset.csv`
- `data/processed/huggingface_slang_dataset.json`
- `data/processed/huggingface_parallel_dataset.csv`
- `data/processed/huggingface_parallel_dataset.json`



## Unified Dataset Schema

Use this schema for the Phase 3 unified dataset:

```text
text
standard_text
term
meaning
example
matched_terms
category
record_type
source
source_dataset
source_url
source_file
split
role
context
collected_at
```

Field guidance:

- `text`: main analyzable text. For Wikipedia rows, use the term and/or meaning. For Hugging Face rows, use the slang, Gen-Z, or informal text provided by the dataset.
- `standard_text`: use only when the source dataset provides a real paired plain-English text. Do not generate or invent it.
- `term`: Wikipedia glossary term when available.
- `meaning`: Wikipedia definition when available.
- `example`: example sentence when available.
- `matched_terms`: slang terms detected in `text`; Phase 3 may leave this empty, Phase 4 should populate it.
- `category`: source category such as `Gen-Z slang`, `parallel_translation`, `conversation_message`, or another clear dataset category.
- `record_type`: use values such as `glossary_entry`, `hf_text`, `hf_parallel`, or `live_comment`.
- `source`: human-readable source name.
- `source_dataset`: Hugging Face dataset ID or future API source dataset when applicable.
- `source_url`: source page, dataset URL, or public API source URL when applicable.
- `source_file`: source file loaded from disk when applicable.
- `split`: dataset split such as `train`, `validation`, `test`, or `full`.
- `role`: conversation role such as `user` or `assistant`, if applicable.
- `context`: optional title, metadata, prompt, conversation turn, video topic, or other non-sensitive context.
- `collected_at`: source collection date or processing date.

### Null Handling Contract

- CSV output: represent all missing values as empty strings (`""`). Do not write `NaN` or `None`.
- JSON output: represent all missing values as `null`. Do not write empty strings for missing optional fields.
- `standard_text` must always be `null` / `""` when not provided by the source. Never fabricate a value.

## Remaining Work By Phase

### Phase 3: Unified Dataset Builder - Next

Create `src/build_unified_dataset.py`.

The script must run from the repository root and read the existing processed files:

- `data/processed/slang_terms.csv`
- `data/processed/slang_terms.json`
- `data/processed/huggingface_slang_dataset.csv`
- `data/processed/huggingface_slang_dataset.json`
- `data/processed/huggingface_parallel_dataset.csv`
- `data/processed/huggingface_parallel_dataset.json`

It should normalize all records into the unified schema defined in §"Unified Dataset Schema" and save:

- `data/processed/unified_slang_dataset.csv`
- `data/processed/unified_slang_dataset.json`

Goals:

- Read Wikipedia and Hugging Face processed outputs.
- Normalize all available records into the unified schema.
- Preserve source provenance.
- Apply the null-handling contract — empty strings in CSV, null in JSON.
- Keep `standard_text` only when the source provides it. Never fabricate a value.
- Save unified CSV and JSON outputs.
- Log the source name and record count per source file, plus the total final record count.
- Create `tests/test_build_unified_dataset.py` with at least the following tests:
  - The script loads all six processed input files without error.
  - The output schema matches the unified schema fields exactly.
  - `standard_text` is never fabricated (remains null/empty when the source has none).

Acceptance criteria:

- The script runs from the repo root without error.
- It generates both CSV and JSON outputs.
- It preserves source provenance fields.
- It keeps `standard_text` optional and never fabricates it.
- It can be tested without live APIs.
- It deduplicates within each source file by `(text, source_file)` to avoid loading the same row twice. It does NOT deduplicate across sources — records from Wikipedia and Hugging Face with the same term are kept separately.
- The unified dataset contains at least 1,000 records.
- The final record count and per-source breakdown are logged to stdout.

### Phase 4: Slang Matching And Basic Analysis

Use the Wikipedia glossary terms as a seed slang dictionary.

Goals:

- Tag Hugging Face rows with `matched_terms`.
- Generate term frequency outputs.
- Generate source comparison summaries.
- Generate co-occurrence summaries.
- Support example retrieval for qualitative review.
- Save analysis outputs under `data/analysis/` or `data/processed/`.

Do this before adding YouTube.

### Phase 5: YouTube Comments API

Implement only after Phase 3 and Phase 4 are stable.

Use the official YouTube Data API.

Goals:

- Collect public comments only.
- Use environment variables for credentials.
- Respect quotas, rate limits, and YouTube API terms.
- Store minimal source metadata needed for analysis.
- Avoid unnecessary personal identifiers.
- Feed YouTube records into the same unified schema.

YouTube should wait until unified dataset generation and basic offline analysis are working.

### Phase 6: Optional Twitch Live Chat

Add only after YouTube or the core offline analysis pipeline is stable.

Treat Twitch as real-time public chat collection, not historical chat scraping.

Goals:

- Use official Twitch developer tools such as IRC, EventSub, or Twitch APIs.
- Collect messages only while public streams are live.
- Respect authentication requirements and rate limits.
- Feed records into the unified schema.

### Phase 7: Advanced Analysis And Visualization

Add after the core dataset and basic analysis are reliable.

Possible features:

- Semantic drift tracking
- Trend detection
- Slang frequency over time
- Term co-occurrence
- Creator, topic, or community-level comparisons
- Streamlit or matplotlib visualizations
- Qualitative example review tools

## Final Target Pipeline Architecture

Use a staged ETL-style pipeline:

```text
Data Source
  -> Extract
  -> Raw Storage
  -> Clean / Filter
  -> Normalize
  -> Slang Matching
  -> Unified Processed Dataset
  -> Analysis
  -> Visualization
```

Responsibilities:

- `Extract`: collect public source records from local files, public datasets, or official APIs.
- `Raw Storage`: preserve raw records when appropriate, subject to privacy and retention rules.
- `Clean / Filter`: remove URLs if needed, normalize whitespace, drop empty records, and remove unusable text.
- `Normalize`: convert every source into the unified schema.
- `Slang Matching`: identify known slang terms and candidate new slang terms.
- `Unified Processed Dataset`: provide the single analysis-ready CSV/JSON layer.
- `Analysis`: measure frequency, source distribution, co-occurrence, and examples.
- `Visualization`: show stable analysis outputs only after the data layer works.

## Source Strategy

### Wikipedia

Status: completed as Phase 1.

Purpose:

- Seed dictionary
- Reference list
- Slang matching vocabulary

Future work:

- Maintain parser if Wikipedia page structure changes.
- Adjust output schema only when downstream unified schema changes.
- Do not redo the extraction task from scratch.

### Hugging Face

Status: completed as Phase 2.

Purpose:

- Offline test datasets
- Slang and informal language examples
- Paired slang-to-standard examples when available

Future work:

- Use current processed outputs for unification.
- Move notebook logic into scripts only if repeatability becomes a priority.
- Never invent missing `standard_text`.

### YouTube

Status: future Phase 5.

Purpose:

- Real usage examples from public comments

Rules:

- Use official YouTube Data API.
- Collect public comments only.
- Wait until Phase 3 and Phase 4 are working.

### Twitch

Status: optional future Phase 6.

Purpose:

- Real-time public chat examples

Rules:

- Use official developer tools.
- Do not attempt historical chat scraping.
- Add only after the core analysis pipeline is stable.

### Reddit

Status: out of scope by default.

Rules:

- Do not scrape Reddit.
- Use Reddit only if official API approval is granted.
- Follow Reddit API terms, rate limits, and research rules.

## Development Guidelines

- Build offline unification and analysis before live API collectors.
- Keep live collectors separate from cleaning, transformation, and analysis logic.
- Make every pipeline stage testable with local files.
- Use environment variables for API keys and credentials.
- Do not hardcode secrets.
- Log source names, record counts, skipped records, and errors.
- Preserve provenance for every record.
- Keep schemas clear and stable.
- Prefer small reproducible outputs over large unverified data dumps.

## Next Agent Instruction

**Task:** Implement Phase 3 — Unified Dataset Builder.

**Execution order:**

1. Create `src/build_unified_dataset.py`.
2. Load all six processed files from `data/processed/`.
3. Normalize each file's records into the unified schema (see §"Unified Dataset Schema").
4. Apply the null-handling contract — empty strings in CSV, null in JSON.
5. Deduplicate within each source file by `(text, source_file)` only. Do not deduplicate across sources.
6. Save `data/processed/unified_slang_dataset.csv` and `data/processed/unified_slang_dataset.json`.
7. Log source name and record count per source file, and total final count.
8. Create `tests/test_build_unified_dataset.py` with schema and null-safety tests.
9. Run the script from the repo root and confirm both output files are generated and contain at least 1,000 records.

**Do not:**

- Restart the Wikipedia extractor.
- Restart the Hugging Face notebook.
- Start YouTube collection.
- Scrape Reddit.
- Fabricate `standard_text` values.
