# Brainrot Translator

This repository is cleaned down to the files required for the current multimodal Brainrot Translator workflow: a FastAPI backend, a Chrome extension content script layer, the Wikipedia slang reference extractor, tests, and supporting docs/config.

## Setup and Run Guide

Use these steps when setting up the project on a new machine or after cloning a fresh copy.

### Requirements

- Python 3.11 or newer.
- Google Chrome or another Chromium browser that supports Manifest V3 extensions.
- PowerShell on Windows for the commands below.
- Optional: an OpenRouter API key for DeepSeek text recheck and image/GIF analysis.
- Optional: a database URL for cache, review staging, and the Brainrot Frequency dashboard.

### 1. Create and activate the virtual environment

```powershell
cd D:\brainrot_translator
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, run this once for the current terminal:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 2. Install backend dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If `python -m uvicorn ...` says `No module named uvicorn`, the dependencies were not installed into the active virtual environment. Run the install command again while `.venv` is active.

### 3. Create `.env`

Create `D:\brainrot_translator\.env`. Do not commit this file because it may contain real credentials.

Minimal local setup:

```env
BRAINROT_API_BASE_URL=http://127.0.0.1:8000
BRAINROT_LOW_CONFIDENCE_THRESHOLD=0.7
```

Recommended setup with DeepSeek recheck through OpenRouter:

```env
OPENROUTER_API_KEY=your_openrouter_key_here
OPENROUTER_TEXT_MODEL=deepseek/deepseek-v4-flash
BRAINROT_API_BASE_URL=http://127.0.0.1:8000
BRAINROT_LOW_CONFIDENCE_THRESHOLD=0.7
```

Add a database if you want cache, low-confidence review staging, and dashboard frequency counts:

```env
DATABASE_URL=sqlite:///./brainrot_translator.db
```

SQLite is the easiest local option. PostgreSQL also works if SQLAlchemy can load the driver for your URL.

### 4. Start the backend

```powershell
python -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

Keep this terminal open while testing the browser extension.

### 5. Check backend health

Open a second PowerShell terminal:

```powershell
cd D:\brainrot_translator
.\.venv\Scripts\Activate.ps1
Invoke-RestMethod http://127.0.0.1:8000/health
```

Expected result includes:

```json
{
  "status": "ok",
  "openrouter_configured": true,
  "text_recheck_configured": true,
  "api_base_url": "http://127.0.0.1:8000"
}
```

`openrouter_configured` is `false` when no `OPENROUTER_API_KEY` is present. Local text translation can still work without it, but forced DeepSeek recheck and image/GIF analysis need OpenRouter.

### 6. Load the Chrome extension

1. Open `chrome://extensions`.
2. Enable `Developer mode`.
3. Click `Load unpacked`.
4. Select `D:\brainrot_translator\extension`.
5. Open a normal `http` or `https` webpage.
6. Click the Brainrot Translator extension icon.
7. In the side panel, set API Base URL to `http://127.0.0.1:8000`.
8. Click `Check Health`.
9. Click `Check Active Page`.

If you reload the extension during development, refresh the webpage tab too. Old content scripts can otherwise show `Extension context invalidated` errors.

### 7. Basic manual test

Highlighted text:

1. Highlight text such as `he has rizz`.
2. Click `Translate` if confirmation mode is enabled.
3. The floating pet bubble should show a formal translation.
4. Click `Recheck` to force the DeepSeek/OpenRouter text recheck route.

Dashboard frequency:

1. Make sure `DATABASE_URL` is set.
2. Restart the backend after editing `.env`.
3. Highlight text containing slang, such as `he has rizz`.
4. Open the side panel.
5. Click `Refresh` under `Brainrot Frequency`.

Image/GIF:

1. Enable `Hover image or GIF analysis` in the side panel or floating launcher.
2. Hover likely meme media for at least 600ms.
3. The backend routes media analysis through the configured OpenRouter vision model.

### 8. API smoke tests

Analyze highlighted text:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/analyze-highlighted-text `
  -ContentType "application/json" `
  -Body '{"selected_text":"he has rizz","page_url":"https://example.com"}'
```

Force DeepSeek text recheck:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/recheck-highlighted-text `
  -ContentType "application/json" `
  -Body '{"selected_text":"he has rizz","page_url":"https://example.com"}'
```

Read dashboard frequency:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/dashboard/word-frequency?limit=20
```

### 9. Run tests

```powershell
python -m unittest discover -s tests
```

### Common Fixes

- `No module named uvicorn`: activate `.venv`, then run `python -m pip install -r requirements.txt`.
- `Database Unavailable`: add `DATABASE_URL=sqlite:///./brainrot_translator.db` to `.env`, then restart the backend.
- `Recheck Unavailable` or fallback response: confirm `/health` shows `openrouter_configured: true`, then retry. OpenRouter timeouts or invalid keys will cause fallback output.
- `Extension context invalidated`: reload the extension and refresh the webpage tab.
- Side panel cannot connect to page: use a normal `http` or `https` page. Chrome internal pages such as `chrome://extensions` cannot run the content script.

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
