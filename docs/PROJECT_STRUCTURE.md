# Project Structure

This repository is organized around an offline-first slang data pipeline. Keep
new work in the narrowest folder that matches its role.

## Current Layout

```text
.
├── codex_prompt.md              # Active roadmap for future Codex runs
├── README.md                    # Human-facing setup and usage notes
├── harvester.py                 # Standalone ETL CLI for live/API-backed sources
├── fetch_wiki.py                # Thin wrapper for the Wikipedia extractor
├── requirements.txt             # Python dependencies
├── package.json                 # Node dependencies, if frontend tooling is added
├── agent/                       # Placeholder for future agent logic
├── api/                         # Placeholder for future API routes and schemas
├── data/
│   ├── raw/                     # Local source files and raw downloaded inputs
│   └── processed/               # Generated normalized CSV/JSON outputs
├── db/
│   └── schema.sql               # PostgreSQL schema for harvester.py
├── docs/
│   └── prompts/                 # Archived or secondary task prompts
├── logs/                        # Runtime logs, ignored by git
├── models/                      # Placeholder for future model loading/inference
├── notebooks/                   # Exploratory notebooks and dataset experiments
├── src/
│   ├── extract_wikipedia_slang.py
│   └── db/                      # Helper database modules for source-specific scripts
└── tests/                       # Unit tests
```

## Placement Rules

- Put reusable Python pipeline code in `src/`.
- Keep root-level Python files only for stable CLI entry points such as
  `harvester.py` and compatibility wrappers such as `fetch_wiki.py`.
- Put notebooks in `notebooks/`.
- Put active project guidance in root `codex_prompt.md`.
- Put archived prompts in `docs/prompts/`.
- Put raw local source files in `data/raw/`.
- Put generated normalized datasets in `data/processed/`.
- Put analysis summaries in `data/analysis/` when Phase 4 begins.
- Put database schemas and migrations in `db/`.
- Keep runtime logs under `logs/`.

## Next Structure Step

The next code file should be:

```text
src/build_unified_dataset.py
```

It should read the existing files under `data/processed/` and write:

```text
data/processed/unified_slang_dataset.csv
data/processed/unified_slang_dataset.json
```
