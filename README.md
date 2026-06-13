# Brainrot Translator

This repository is cleaned down to the files required for the current multimodal Brainrot Translator workflow: a FastAPI backend, a Chrome extension content script layer, the Wikipedia slang reference extractor, tests, and supporting docs/config.

## Setup and Run Guide

Use these steps when setting up the project on a new machine or after cloning a fresh copy.

### Requirements

- Python 3.11 or newer.
- Google Chrome or another Chromium browser that supports Manifest V3 extensions.
- PowerShell on Windows for the commands below.
- Optional: each extension user needs their own OpenRouter API key for AI recheck, reverse translation, and image/GIF analysis.
- Optional for local testing, required for production: `DATABASE_URL` for the shared monthly Top Slang Frequency leaderboard.

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

Recommended setup with OpenRouter model tier choices:

```env
OPENROUTER_TEXT_FREE_MODEL=nvidia/nemotron-3-super-120b-a12b:free
OPENROUTER_TEXT_PREMIUM_MODEL=deepseek/deepseek-v4-flash
OPENROUTER_IMAGE_FREE_MODEL=nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free
OPENROUTER_IMAGE_PREMIUM_MODEL=google/gemini-3.1-flash-lite
BRAINROT_API_BASE_URL=http://127.0.0.1:8000
BRAINROT_LOW_CONFIDENCE_THRESHOLD=0.7
```

Do not put a shared OpenRouter API key in `.env`. Enter the user's OpenRouter API key in the extension side panel under `Settings / Status -> OpenRouter API Key`.

Add a database for shared monthly Top Slang Frequency:

```env
DATABASE_URL=sqlite:///./brainrot_translator.db
```

SQLite is the easiest local option. For a real public extension, use a hosted PostgreSQL database and install the matching SQLAlchemy driver for your deployment URL. The shared leaderboard stores detected slang terms and counts only; it does not store user OpenRouter API keys, raw page text, URLs, domains, or image payloads.

Admin moderation uses Google login:

```env
GOOGLE_ADMIN_CLIENT_ID=your-google-oauth-client-id.apps.googleusercontent.com
ADMIN_GOOGLE_EMAILS=you@example.com
```

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
  "user_openrouter_key_present": false,
  "openrouter_configured": false,
  "text_recheck_configured": false,
  "api_base_url": "http://127.0.0.1:8000"
}
```

`user_openrouter_key_present` remains `false` for normal extension traffic because the production extension does not send OpenRouter keys to the backend. The key is kept in the extension and used by the background service worker to call OpenRouter directly.

### 6. Load the Chrome extension

1. Open `chrome://extensions`.
2. Enable `Developer mode`.
3. Click `Load unpacked`.
4. Select `D:\brainrot_translator\extension`.
5. Open a normal `http` or `https` webpage.
6. Click the Brainrot Translator extension icon.
7. In the side panel, set API Base URL to `http://127.0.0.1:8000`.
8. Enter your OpenRouter API key if you want AI recheck, reverse translation, or image analysis.
9. Choose Free or Premium model tiers for text and image.
10. Choose whether to share anonymous slang frequency counts.
11. Click `Check Health`.
12. Click `Check Active Page`.

If you reload the extension during development, refresh the webpage tab too. Old content scripts can otherwise show `Extension context invalidated` errors.

### 7. Basic manual test

Highlighted text:

1. Highlight text such as `he has rizz`.
2. Click `Translate` if confirmation mode is enabled.
3. The floating pet bubble should show a formal translation.
4. Click `Recheck` to force the selected OpenRouter text model route.

Dashboard frequency:

1. Make sure `DATABASE_URL` is set.
2. Restart the backend after editing `.env`.
3. Enable `Share anonymous slang frequency` in Settings.
4. Highlight text containing slang, such as `he has rizz`.
5. Open the side panel.
6. Click `Refresh` under `Top Slang Frequency`.

The current-month chart resets automatically each month because counts are stored by calendar month. The yearly leaderboard is available from the public API.

Admin moderation:

1. Sign in with Google in your admin client and send the Google ID token as `Authorization: Bearer <id_token>`.
2. Use `GET /api/v1/admin/slang` to review terms.
3. Use `PATCH /api/v1/admin/slang/{normalized_term}` to set `visible`, `hidden`, or `banned`.
4. Public charts exclude `hidden` and `banned` terms but keep internal counts.

Image/GIF:

1. Enable `Hover image or GIF analysis` in the side panel or floating launcher.
2. Hover likely meme media for at least 600ms.
3. The extension background service worker routes media analysis directly to the configured OpenRouter vision model.

### 8. API smoke tests

Analyze highlighted text:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/analyze-highlighted-text `
  -ContentType "application/json" `
  -Body '{"selected_text":"he has rizz","page_url":"https://example.com"}'
```

Force selected-tier text recheck:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/recheck-highlighted-text `
  -ContentType "application/json" `
  -Body '{"selected_text":"he has rizz","page_url":"https://example.com"}'
```

Read dashboard frequency:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/public/top-slang?period=month&limit=20"
```

Read annual countdown:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/public/top-slang?period=year&year=2026&limit=50"
```

### 9. Run tests

```powershell
python -m unittest discover -s tests
```

### Common Fixes

- `No module named uvicorn`: activate `.venv`, then run `python -m pip install -r requirements.txt`.
- `Database Unavailable`: add `DATABASE_URL=sqlite:///./brainrot_translator.db` to `.env`, then restart the backend.
- `OpenRouter API key is missing or invalid`: enter a valid user OpenRouter API key in the extension settings, then retry. Local/offline glossary text may still work without it.
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
- `/api/v1/analyze-highlighted-text` still supports backend-local text analysis. The production extension calls OpenRouter directly from the background service worker when AI is required.
- Build the local good/bad translation classifier dataset with `python scripts/prepare_quality_classifier_dataset.py`.
- Train the local quality classifier with `python scripts/train_quality_classifier.py`, or use `notebooks/train_quality_classifier_colab.ipynb` on Colab GPU, then place the saved folder at `models/brainrot-quality-classifier-v1`.
- When `models/brainrot-quality-classifier-v1` exists, highlighted-text confidence comes from that local classifier. Without it, the backend uses a deterministic heuristic confidence score.
- `slang_terms.json` is not updated automatically by app usage; database cache/review rows are separate from the fixed vocabulary file.
- `.env` stays local; copy from `.env.example` and configure model names, database, thresholds, and API base URL as needed.
- OpenRouter API keys are user-owned and entered in the extension side panel. By default they are remembered in `chrome.storage.local` for the current Chrome browser profile; users can turn off "Remember OpenRouter key on this device" to keep the key only in `chrome.storage.session` until Chrome closes. Keys are sent directly to OpenRouter by the extension background service worker, not to your backend, telemetry routes, database, `.env`, or Chrome sync.
- `DATABASE_URL` is optional for cache/review persistence.
- The extension defaults to `http://127.0.0.1:8000` and can be overridden with `BRAINROT_API_BASE_URL`.
- The extension action now opens a persistent side panel for testing; the floating pet still replies on the webpage itself while the side panel stays open for settings and `/health`.
