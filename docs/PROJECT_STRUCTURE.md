# Project Structure

This repo is intentionally split into three active areas:

- `api/`: FastAPI backend for text translation and image/GIF brainrot analysis.
- `extension/`: Chrome extension assets that call the backend, render the floating pet UI, and expose the persistent side-panel control surface.
- `src/`: Offline data utilities, currently the Wikipedia slang extractor.
- `scripts/`: Offline training-data utilities for the FLAN-T5 translator and local good/bad translation quality classifier.

Ignored runtime data lives under `data/` and local secrets live in `.env`.
