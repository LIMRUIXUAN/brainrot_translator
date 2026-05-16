# Codex Agent Prompt — Brainrot Translator Pipeline (All Remaining Phases)

Read `codex_prompt.md` for full project context, schema definitions, and field guidance. This file is the execution guide. When they conflict, `codex_prompt.md` wins.

Execute phases in order. Do not skip a phase. Do not start a later phase until the current one is verified.

---

## Ethical And Legal Rules

These apply to every phase:

- Only collect public data. Never collect private messages, deleted, or restricted content.
- Remove or anonymize usernames wherever possible.
- Respect each platform's terms of service and official API rate limits.
- Use official APIs only. No scraping.
- Preserve provenance for every record without keeping unnecessary personal identifiers.
- Keep live API collectors separate from cleaning, transformation, and analysis logic.
- Make every stage testable with local files and no live credentials.

---

## Credential Gate Rule

If any phase requires a credential not already present in `.env`:

1. Stop that phase immediately.
2. Print which environment variable is missing, what it is for, and where to obtain it.
3. Do not mock, stub, or invent the credential.
4. Skip that phase and continue with the next available offline phase.

Required credentials by phase:

| Variable | Phase | How to get |
|---|---|---|
| `YOUTUBE_API_KEY` | 5 | console.cloud.google.com → APIs & Services → Enable YouTube Data API v3 → Credentials |
| `TWITCH_OAUTH_TOKEN` | 6 | dev.twitch.tv/console/apps → register app → generate token with `chat:read` scope |
| `TWITCH_BOT_USERNAME` | 6 | your Twitch account username used for the bot |
| `MONGODB_URI` | Optional | skip silently if not set |

---

## Pipeline Architecture

```
Data Source → Extract → Raw Storage → Clean/Filter → Normalize
  → Slang Matching → Unified Processed Dataset → Analysis → Visualization
```

Keep each stage in a separate script. Do not mix collection logic with transformation or analysis.

---

## Phase 3 — Unified Dataset Builder

**File to create:** `src/build_unified_dataset.py`
**Credentials required:** None — run immediately.

**Inputs** (all exist in `data/processed/`):
- `slang_terms.csv` / `.json` — Wikipedia seed glossary
- `huggingface_slang_dataset.csv` / `.json` — HF informal text
- `huggingface_parallel_dataset.csv` / `.json` — HF slang-to-standard pairs

**Outputs:**
- `data/processed/unified_slang_dataset.csv`
- `data/processed/unified_slang_dataset.json`

**Schema:** Use the 16-field unified schema defined in `codex_prompt.md §"Unified Dataset Schema"`. Apply the null-handling contract from the same section (CSV → `""`, JSON → `null`).

**Deduplication:** Deduplicate within each source file by `(text, source_file)`. Do NOT deduplicate across sources.

**Logging:** Print source file path, record count per source, and total final count. Warn (do not crash) on missing or empty files.

**Acceptance criteria:**
- Runs from repo root: `python src/build_unified_dataset.py`
- Both CSV and JSON output files generated
- Schema has exactly 16 fields in order
- `standard_text` populated only for `hf_parallel` records — never fabricated
- Deduplication is within-source only
- At least 1,000 total records logged

**Tests** — create `tests/test_build_unified_dataset.py`:
1. All six input files load without error and return non-empty data
2. Output schema matches all 16 unified fields exactly
3. `standard_text` is empty/null for `glossary_entry` and `hf_text` records
4. `standard_text` is populated for at least some `hf_parallel` records
5. Final record count exceeds 1,000

---

## Phase 4 — Slang Matching And Basic Analysis

**File to create:** `src/analyze_slang.py`
**Credentials required:** None — run after Phase 3 is verified.

**Inputs:**
- `data/processed/unified_slang_dataset.csv`
- `data/processed/slang_terms.csv` (seed slang dictionary)

**Outputs** (save to `data/analysis/`):
- `matched_unified_dataset.csv` / `.json` — unified dataset with `matched_terms` populated
- `term_frequency.csv` / `.json` — columns: `term`, `frequency`, `sources`
- `source_comparison.csv` / `.json` — per-source: total records, matched records, unique terms
- `co_occurrence.csv` / `.json` — top 500+ term pairs by co-occurrence count

**Behavior:**
- Scan `text` field for known slang terms (case-insensitive, whole-word preferred).
- Write matched terms as pipe-separated values in `matched_terms`, e.g. `"slay|no cap"`.
- Term frequency sorted descending. Source comparison grouped by `source`. Co-occurrence by pair count.

**Acceptance criteria:**
- Runs from repo root: `python src/analyze_slang.py`
- All output files generated under `data/analysis/`
- `matched_terms` populated in matched dataset
- No network or API calls

---

## Phase 5 — YouTube Comments Collector

**File to create:** `src/collect_youtube_comments.py`
**Credentials required:** `YOUTUBE_API_KEY` — check `.env` before writing any collection code.
**Run only after Phase 3 and Phase 4 are stable.**

**Credential gate:** At script startup, load `.env` with `python-dotenv`. If `YOUTUBE_API_KEY` is missing, print the variable name, explain it requires YouTube Data API v3, print the URL `https://console.cloud.google.com/apis/credentials`, and exit with a non-zero code. Do not proceed.

**Requirements:**
- Official YouTube Data API v3 only. No scraping.
- CLI args: `--video-ids` (comma-separated) or `--query` (search term).
- Collect public top-level comments only. No replies by default.
- Rate limit: add delay between paginated requests. Respect API quotas.
- Store minimal fields: `video_id`, `channel_id`, `published_at`, `text`. Anonymize or omit usernames.
- Map to unified schema: `record_type = "live_comment"`, `source = "YouTube"`, `source_url = video URL`, `context = video title`.
- Raw output: `data/raw/youtube_comments_raw.jsonl` (append mode, one object per line).
- Normalized output: `data/processed/youtube_comments.csv` / `.json`.
- Log: video ID, request count, comment count per video, quota errors.

**Acceptance criteria:**
- Fails gracefully with clear message if `YOUTUBE_API_KEY` is missing
- Output schema matches unified schema
- Rate limits respected; no hardcoded credentials

---

## Phase 6 — Twitch Live Chat Collector

**File to create:** `src/collect_twitch_chat.py`
**Credentials required:** `TWITCH_OAUTH_TOKEN` and `TWITCH_BOT_USERNAME` — check `.env` before writing any collection code.
**Optional. Run only after YouTube or core offline pipeline is stable.**

**Credential gate:** At script startup, check both variables. If either is missing, print both variable names, explain how to register a Twitch app at `https://dev.twitch.tv/console/apps` and generate a token with `chat:read` scope, then exit with a non-zero code. Do not proceed.

**Requirements:**
- Official Twitch IRC (`irc.chat.twitch.tv:6697`) or EventSub only.
- Collect messages only from active public live streams. No historical chat scraping.
- CLI arg: `--channels` (comma-separated channel names).
- Store: `channel`, `message_text`, `collected_at`. No usernames.
- Map to unified schema: `record_type = "live_comment"`, `source = "Twitch"`, `context = channel name`.
- Raw output: `data/raw/twitch_chat_raw.jsonl`. Normalized: `data/processed/twitch_chat.csv` / `.json`.

**Acceptance criteria:**
- Fails gracefully with clear message if either Twitch credential is missing
- Collects live messages only — no scraping
- Output schema matches unified schema

---

## Phase 7 — Advanced Analysis And Visualization

**File to create:** `src/visualize.py` (or `notebooks/visualization.ipynb` if scripts are impractical)
**Credentials required:** None — run after Phase 4 analysis outputs are stable.

**Features to implement** (choose based on data available):
1. Slang frequency bar chart — top 30 terms, colored by primary source
2. Source distribution chart — record count per `source` value
3. Term co-occurrence heatmap — top 20 terms
4. Slang over time — term frequency by month if `collected_at` varies
5. Qualitative example viewer — print 5 example records for a given term

**Requirements:**
- Use `matplotlib` and/or `pandas` only. No paid external services.
- Save all charts to `data/analysis/charts/`. Use `plt.savefig`, not `plt.show`.
- Output must be reproducible: same input → same output on every run.

---

## Execution Order

```
Phase 3 → verify → Phase 4 → verify
  → [YOUTUBE_API_KEY present?] → Phase 5
  → [TWITCH tokens present?]   → Phase 6
  → Phase 7
```

---

## Do Not Rules

- Do not restart `src/extract_wikipedia_slang.py` or `notebooks/dataset_huggingface.ipynb`.
- Do not scrape Reddit. Reddit is out of scope unless official API approval is granted.
- Do not hardcode any API key, token, or password anywhere in code.
- Do not fabricate `standard_text` values.
- Do not collect private, deleted, or restricted content.
- Do not store usernames unless strictly required for provenance.
- Do not modify `src/db/` unless explicitly asked.
- Log source names, record counts, skipped records, and errors in every script.
- Prefer small reproducible outputs over large unverified data dumps.
