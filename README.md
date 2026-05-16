# brainrot_translator

## Project Goal

This project prepares datasets and trains a text-to-text model that converts
brainrot or slang English into normal English.

Example:

- Input: `bro is cooked fr no cap`
- Output: `He is in serious trouble, honestly.`

The repository keeps the existing data-collection work, then adds a simple path
for:

- dataset preparation
- Google Colab model training
- local model testing
- Flask API inference

## Current Project Layout

See `docs/PROJECT_STRUCTURE.md` for the current repository structure and
placement rules.

For the dataset collection, cleaning, and source-extension workflow, see:

- `docs/DATASET_PIPELINE.md`

Important folders for the training pipeline:

- `data/raw/` - original messy input files
- `data/processed/` - final CSV datasets used for training
- `data/analysis/` - dataset reports and analysis outputs
- `notebooks/` - Google Colab notebooks
- `models/` - trained Hugging Face model files
- `scripts/` - reusable task-focused pipeline helpers
- `src/` - reusable Python scripts
- `api/` - backend API files
- `tests/` - simple unit tests

## Existing Data Sources Kept In This Repo

The original repo work is preserved.

### Wikipedia Slang Seed Extractor

`src/extract_wikipedia_slang.py` parses a local HTML copy of Wikipedia's
Glossary of 2020s slang and writes:

- `data/processed/slang_terms.csv`
- `data/processed/slang_terms.json`

Run it from the repository root:

```powershell
python src/extract_wikipedia_slang.py --input data/raw/wiki_2020s_slang.html
```

If the local file is missing and you need to refresh from Wikipedia:

```powershell
python src/extract_wikipedia_slang.py --input data/raw/wiki_2020s_slang.html --fetch-latest
```

Optional MongoDB insertion is still available:

```powershell
python src/extract_wikipedia_slang.py --input data/raw/wiki_2020s_slang.html --insert-mongodb
```

### Hugging Face Dataset Notebook

`notebooks/dataset_huggingface.ipynb` normalizes public Hugging Face slang and
parallel datasets into:

- `data/processed/huggingface_slang_dataset.csv`
- `data/processed/huggingface_slang_dataset.json`
- `data/processed/huggingface_parallel_dataset.csv`
- `data/processed/huggingface_parallel_dataset.json`

### Harvester ETL

`harvester.py` remains a separate CLI workflow for live/API-backed sources such
as Reddit, Pinecone, PostgreSQL, and optional Twitch support. It is not changed
or removed by the training pipeline.

Typical setup:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Typical commands:

```powershell
python harvester.py --dry-run --source urban --terms "rizz,no cap,slay"
python harvester.py --source urban
python harvester.py
```

## Dataset Preparation

The training dataset builder is:

- `src/prepare_dataset.py`

It does the following:

- scans all supported files in `data/raw/`
- supports `.csv`, `.xlsx`, `.json`, `.txt`, and `.md`
- tries to auto-detect useful input and output columns from messy datasets
- keeps slang style while doing light cleaning
- removes empty rows, duplicates, same-text pairs, URL-only rows, symbol-only rows, and noisy rows
- writes the final training CSV files
- writes a dataset report to `data/analysis/dataset_report.md`

To make this repo usable immediately, the script also uses the existing paired
seed datasets already present in `data/processed/` when they exist:

- `slang_terms.csv` or `slang_terms.json`
- `huggingface_parallel_dataset.csv` or `huggingface_parallel_dataset.json`

That means you can build a training dataset right away even if `data/raw/`
currently only contains HTML files.

### Raw Data Location

Place original messy files here:

- `data/raw/`

### Processed Dataset Location

The preparation script writes:

- `data/processed/brainrot_dataset.csv`
- `data/processed/brainrot_dataset_training_ready.csv`
- `data/analysis/training_ready_review.csv`
- `data/analysis/dataset_report.md`

`brainrot_dataset.csv` is the baseline normalized dataset.
`brainrot_dataset_training_ready.csv` is the reviewed file intended for model
training. `training_ready_review.csv` records which rows were kept, rewritten,
or dropped.

### How To Run Dataset Preparation

Run this from the repository root:

```powershell
python src/prepare_dataset.py
```

## FLAN-T5 Training Dataset Filter

The FLAN-T5 prompt-ready filter is:

- `scripts/filter_training_dataset.py`

This script reads the baseline dataset in:

- `data/processed/brainrot_dataset.csv`

It then judges whether each row is genuinely useful for training and rewrites
usable rows into two prompt styles:

- sentence translation
- term definition / origin explanation

Output schema:

```text
input_text,target_text,task_type,quality_label,reason
```

Output files:

- `data/processed/brainrot_dataset_cleaned.csv`
- `data/processed/brainrot_dataset_repaired.csv`
- `data/processed/brainrot_dataset_rejected.csv`

Task types:

- `sentence_translation`
- `term_definition`

Quality labels:

- `keep`
- `repaired`
- `rejected`

Typical command:

```powershell
python scripts/filter_training_dataset.py
```

The script keeps the original `brainrot_dataset.csv` unchanged. The cleaned file
contains both `keep` and `repaired` rows and is the FLAN-T5-ready prompt
dataset produced by this pipeline.

## How To Train The Model In Google Colab

Use:

- `notebooks/train_flan_t5.ipynb`

The notebook:

- trains `google/flan-t5-small`
- reads `data/processed/brainrot_dataset_training_ready.csv`
- uses the prompt format `Convert brainrot English to normal English: <text>`
- splits the dataset into train and validation sets
- trains with `Seq2SeqTrainer`
- saves the final model to `models/brainrot-translator-v1/`
- zips the model folder for download

### Open And Train In Colab

1. Upload or open `notebooks/train_flan_t5.ipynb` in Google Colab.
2. Run the install cell.
3. Upload `brainrot_dataset_training_ready.csv` when prompted, or mount Google Drive.
4. Run the remaining cells on a GPU runtime.

Recommended Colab setting:

- Runtime -> Change runtime type -> GPU

## How To Download The Trained Model

The notebook creates:

- `models/brainrot-translator-v1/`
- `models/brainrot-translator-v1.zip`

Download the zip file from Colab after training finishes.

## Where To Place The Trained Model Locally

Extract the trained model files into:

- `models/brainrot-translator-v1/`

The repo already includes that folder with a small placeholder README.

## How To Test The Model Locally

Use:

- `src/test_model.py`

Run from the repository root:

```powershell
python src/test_model.py
```

Expected behavior:

```text
Enter brainrot text: bro is cooked fr
Normal English: He is in serious trouble.
```

Type any of these to stop:

- `exit`
- `quit`
- `q`

## How To Run The Flask API

API files:

- `api/app.py`
- `api/requirements.txt`

Install API dependencies if needed:

```powershell
pip install -r api/requirements.txt
```

Start the API:

```powershell
cd api
python app.py
```

The API runs on:

- `http://localhost:5000`

## API Usage Example

### Health Check

```powershell
Invoke-RestMethod -Uri "http://localhost:5000/health"
```

### Windows curl Example

```powershell
curl -X POST http://localhost:5000/translate ^
  -H "Content-Type: application/json" ^
  -d "{\"text\":\"bro is cooked fr no cap\"}"
```

### PowerShell Example

```powershell
Invoke-RestMethod -Uri "http://localhost:5000/translate" `
  -Method POST `
  -Headers @{ "Content-Type" = "application/json" } `
  -Body '{"text":"bro is cooked fr no cap"}'
```

Expected JSON response:

```json
{
  "normal": "He is in serious trouble."
}
```

## Troubleshooting

### `brainrot_dataset_training_ready.csv` was not created

- Make sure you ran `python src/prepare_dataset.py` from the repository root.
- Check `data/analysis/dataset_report.md` for skipped files, unreadable files, and warnings.

### `data/raw/` only has HTML files

- That is okay for this repo's current state.
- `src/prepare_dataset.py` also uses the existing paired seed datasets already stored in `data/processed/`.

### `ModuleNotFoundError` or missing package errors

- Reinstall the project dependencies:

```powershell
pip install -r requirements.txt
```

- For API-only work:

```powershell
pip install -r api/requirements.txt
```

### `transformers` fails because of `huggingface-hub`

- Install the repo requirements again so the compatible Hugging Face versions are used:

```powershell
pip install -r requirements.txt
```

- The project now expects `huggingface-hub<1.0` for the local inference stack.

### Model folder not found

- Train the model in Colab first.
- Place the exported model files inside `models/brainrot-translator-v1/`.

### Flask API says the model could not be loaded

- Confirm the trained Hugging Face files are inside `models/brainrot-translator-v1/`.
- Make sure files such as `config.json`, tokenizer files, and model weights are present.

### Notebook cannot find the dataset in Colab

- Upload `brainrot_dataset_training_ready.csv` with the upload cell, or
- copy it from Google Drive into `data/processed/brainrot_dataset_training_ready.csv`

## Local Checks

```powershell
python src/prepare_dataset.py
python -m unittest tests.test_prepare_dataset
python -m unittest discover -s tests
```
