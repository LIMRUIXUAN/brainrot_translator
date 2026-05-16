# Archived Prompt - Wikipedia Slang Extraction

This prompt is archived and completed. It is kept as a status note so future agents do not redo completed Wikipedia work.

## Status

Wikipedia extraction has already been implemented.

Implemented file:

- `src/extract_wikipedia_slang.py`

Generated outputs:

- `data/processed/slang_terms.csv`
- `data/processed/slang_terms.json`

Extracted schema:

```text
term, meaning, example, source, source_url, category, collected_at
```

## Completed Behavior

The completed Wikipedia extractor:

- Reads the local Wikipedia HTML source for the Glossary of 2020s slang.
- Parses slang terms with BeautifulSoup.
- Extracts meanings and examples where available.
- Removes citation markers and excessive whitespace.
- Preserves original slang spelling.
- Avoids duplicate terms.
- Writes database-ready JSON and CSV outputs.
- Creates output folders when needed.
- Provides optional database insertion support through project database helpers.

## Future Wikipedia Work

Future agents should modify the Wikipedia extractor only for:

- Parser maintenance if the Wikipedia page structure changes.
- Output schema changes required by the unified dataset pipeline.
- Bug fixes.
- Small quality improvements that preserve the existing output contract.

Do not restart the Wikipedia extraction task from scratch unless the user explicitly asks.

## Active Roadmap

Active project planning now lives in:

- `codex_prompt.md`

The next active implementation phase is:

- `src/build_unified_dataset.py`

That phase should unify the completed Wikipedia outputs with the completed Hugging Face processed outputs before any YouTube API work begins.
