# Brainrot Translator

This repository is cleaned down to the files required for the current multimodal Brainrot Translator workflow: a FastAPI backend, a Chrome extension content script layer, the Wikipedia slang reference extractor, tests, and supporting docs/config.

## Required Files

### Root
- `.env.example`
- `.gitignore`
- `README.md`
- `guideline_prompt.md`
- `requirements.txt`
- `fetch_wiki.py`

### Backend
- `api/__init__.py`
- `api/app.py`
- `api/config.py`
- `api/local_translator.py`
- `api/main.py`
- `api/agent.py`
- `api/database.py`
- `api/schemas.py`
- `db/schema.sql`

### Extension
- `extension/background.js`
- `extension/manifest.json`
- `extension/content_script.js`
- `extension/pet_bubble.js`
- `extension/pet_shell.css`
- `extension/popup.css`
- `extension/popup.js`
- `extension/sidepanel.html`
- `extension/sidepanel.css`

### Data Utilities
- `scripts/prepare_training_dataset.py`
- `scripts/prepare_quality_classifier_dataset.py`
- `scripts/train_quality_classifier.py`
- `src/__init__.py`
- `src/extract_wikipedia_slang.py`

### Tests
- `tests/test_api_main.py`
- `tests/test_agent.py`
- `tests/test_local_translator.py`

### Supporting Docs and Runtime Artifacts
- `docs/PROJECT_STRUCTURE.md`
- `notebooks/train_flan_t5_colab.ipynb`
- `notebooks/train_quality_classifier_colab.ipynb`
- `logs/.gitkeep`
- `data/raw/wikipedia_glossary.html`
- `data/processed/slang_terms.json`
- `data/processed/slang_terms.csv`

## Final File Structure

```text
brainrot_translator/
|-- .env.example
|-- .gitignore
|-- README.md
|-- guideline_prompt.md
|-- requirements.txt
|-- fetch_wiki.py
|-- api/
|   |-- __init__.py
|   |-- agent.py
|   |-- app.py
|   |-- config.py
|   |-- database.py
|   |-- local_translator.py
|   |-- main.py
|   `-- schemas.py
|-- db/
|   `-- schema.sql
|-- docs/
|   `-- PROJECT_STRUCTURE.md
|-- extension/
|   |-- background.js
|   |-- content_script.js
|   |-- manifest.json
|   |-- pet_bubble.js
|   |-- pet_shell.css
|   |-- popup.css
|   |-- popup.js
|   |-- sidepanel.css
|   `-- sidepanel.html
|-- logs/
|   `-- .gitkeep
|-- notebooks/
|   |-- train_flan_t5_colab.ipynb
|   `-- train_quality_classifier_colab.ipynb
|-- scripts/
|   |-- prepare_quality_classifier_dataset.py
|   |-- prepare_training_dataset.py
|   `-- train_quality_classifier.py
|-- src/
|   |-- __init__.py
|   |-- extract_wikipedia_slang.py
|-- tests/
|   |-- test_agent.py
|   |-- test_api_main.py
|   `-- test_local_translator.py
`-- data/
    |-- raw/
    |   `-- wikipedia_glossary.html
    `-- processed/
        |-- slang_terms.csv
        `-- slang_terms.json
```

## Notes

- `data/` is intentionally gitignored, but the current reference files are part of the expected local workspace.
- Build the local FLAN-T5 training CSV with `python scripts/prepare_training_dataset.py`.
- Train in Google Colab with `notebooks/train_flan_t5_colab.ipynb`, then place the downloaded model folder at `models/brainrot-translator-v1`.
- `/translate` uses `models/brainrot-translator-v1` when present and falls back to the local glossary mock when the model folder is missing.
- `/api/v1/analyze-highlighted-text` also prefers the local model when installed; OpenRouter is only a fallback for text cache misses without a local model.
- Build the local good/bad translation classifier dataset with `python scripts/prepare_quality_classifier_dataset.py`.
- Train the local quality classifier with `python scripts/train_quality_classifier.py`, or use `notebooks/train_quality_classifier_colab.ipynb` on Colab GPU, then place the saved folder at `models/brainrot-quality-classifier-v1`.
- When `models/brainrot-quality-classifier-v1` exists, highlighted-text confidence comes from that local classifier. Without it, the backend uses a deterministic heuristic confidence score.
- `slang_terms.json` is not updated automatically by app usage; database cache/review rows are separate from the fixed vocabulary file.
- `.env` stays local; copy from `.env.example` and fill in real credentials when needed.
- `OPENROUTER_API_KEY` is required only for text fallback without a local model and for image/GIF analysis, not for the local text model path.
- `DATABASE_URL` is optional for cache/review persistence.
- The extension defaults to `http://127.0.0.1:8000` and can be overridden with `BRAINROT_API_BASE_URL`.
- The extension action now opens a persistent side panel for testing; the floating pet still replies on the webpage itself while the side panel stays open for settings and `/health`.
