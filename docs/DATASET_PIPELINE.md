# Dataset Collection And Cleaning Guide

This file documents the current dataset pipeline in this repository:

- how data is collected
- how it is normalized and cleaned
- how the final training pairs are built
- how the FLAN-T5 prompt dataset is filtered and repaired
- how to add more sources without breaking the current workflow
- what dataset types should be used for future additions

## Scope

There are three related layers in this repo:

1. Source-specific collection or normalization
2. Training-pair preparation
3. FLAN-T5 prompt-dataset filtering
4. Future unified corpus building

The current model-training dataset is still based on the simple two-column
training format:

```text
brainrot, normal
```

The future broader corpus should follow the unified schema in
`codex_prompt.md`, but that is a separate downstream step.

There is now also a second training-oriented output for instruction-tuned
seq2seq models such as FLAN-T5. That output uses prompt-style columns:

```text
input_text, target_text, task_type, quality_label, reason
```

## Current Data Sources

### 1. Wikipedia glossary seed

Collected by:

- `src/extract_wikipedia_slang.py`

Input:

- `data/raw/wiki_2020s_slang.html`

Output:

- `data/processed/slang_terms.csv`
- `data/processed/slang_terms.json`

Current schema:

```text
term, meaning, example, source, source_url, category, collected_at
```

Use case:

- seed slang dictionary
- term definitions
- future slang matching
- limited contribution to model training through `term -> meaning`

### 2. Hugging Face parallel translation datasets

Normalized by:

- `notebooks/dataset_huggingface.ipynb`

Output:

- `data/processed/huggingface_parallel_dataset.csv`
- `data/processed/huggingface_parallel_dataset.json`

Current schema:

```text
text, standard_text, context, role, category, source_dataset, source_url, source_file, split, collected_at
```

Current source datasets inside this normalized file:

- `ethan00alphayehah/brainrot-dataset`
- `shvn22k/brainrot-dataset`
- `projolx/genz_brainrot_dataset`

Use case:

- primary direct training-pair source for the translator model

### 3. Hugging Face slang or conversation corpora

Normalized by:

- `notebooks/dataset_huggingface.ipynb`

Output:

- `data/processed/huggingface_slang_dataset.csv`
- `data/processed/huggingface_slang_dataset.json`

Current schema:

```text
text, standard_text, context, role, category, source_dataset, source_url, source_file, split, collected_at
```

Important rule:

- this file is broader and more mixed than `huggingface_parallel_dataset.*`
- some rows are conversation-style and have no usable target text
- some rows may still contain paired records, but the file is not currently the
  default direct input to the final training-pair builder
- it is mainly useful for slang analysis, corpus expansion, and future unified
  dataset work

Current source datasets inside this normalized file include:

- `grenishrai/brainrot-conversation`
- `ethan00alphayehah/brainrot-dataset`
- `shvn22k/brainrot-dataset`
- `projolx/genz_brainrot_dataset`
- `Andy-ML-And-AI/gen-alpha-brainrot`
- `Tralalabs/brainrot-smoll-corpus-jsonl`

## How Data Is Collected

### Wikipedia collection flow

The Wikipedia extractor is an offline-first parser.

Collection steps:

1. Read local HTML from `data/raw/wiki_2020s_slang.html`.
2. Optionally fetch the latest Wikipedia page only when `--fetch-latest` is
   used.
3. Remove non-data page elements such as scripts, references, navboxes, and
   edit links.
4. Parse glossary sections from `dt/dd` structures.
5. Fall back to plain-text section parsing if the HTML layout changes.
6. Clean citation markers, normalize spacing, and preserve term spelling.
7. Extract a lightweight example when the definition explicitly contains one.
8. Deduplicate by term, preferring the clearest or longest available meaning.
9. Save normalized CSV and JSON outputs.

Typical command:

```powershell
python src/extract_wikipedia_slang.py --input data/raw/wiki_2020s_slang.html
```

Optional refresh:

```powershell
python src/extract_wikipedia_slang.py --input data/raw/wiki_2020s_slang.html --fetch-latest
```

### Hugging Face normalization flow

The notebook-based normalization step converts public datasets into a stable
repo-local format.

Normalization rules already used in this repo:

- remove useless record IDs
- keep source provenance fields
- keep `standard_text` only when the dataset really provides it
- never invent a standard translation
- keep conversation metadata such as `role`, `split`, `context`, and
  `source_dataset`

This produces two different buckets:

- `huggingface_parallel_dataset.*` for real paired translation rows
- `huggingface_slang_dataset.*` for slang-only or conversation-style rows

### Training-pair preparation flow

The current training dataset is built by:

- `src/prepare_dataset.py`

It reads:

- supported raw files under `data/raw/`
- supplemental seed files already in `data/processed/`

Currently auto-loaded supplemental seeds:

- `slang_terms.csv` or `slang_terms.json`
- `huggingface_parallel_dataset.csv` or `huggingface_parallel_dataset.json`

Supported raw file extensions:

- `.csv`
- `.xlsx`
- `.json`
- `.txt`
- `.md`

The loader tries to auto-detect useful columns from messy files.

Recognized input-side column names include:

- `brainrot`
- `slang`
- `slang_text`
- `input`
- `original`
- `sentence`
- `phrase`
- `informal`
- `meme_text`
- `text`
- `comment`
- `content`

Recognized output-side column names include:

- `normal`
- `meaning`
- `translation`
- `target`
- `output`
- `explanation`
- `standard`
- `standard_text`
- `formal`
- `rewritten`
- `normalized`
- `definition`
- `clean`
- `response`

### FLAN-T5 filter and repair flow

The FLAN-T5-ready prompt dataset is built by:

- `scripts/filter_training_dataset.py`

This script reads:

- `data/processed/brainrot_dataset.csv`

Then it judges each row for actual training usefulness instead of only checking
format. The script supports two tasks:

1. `sentence_translation`
2. `term_definition`

Sentence translation rows become:

```text
input_text: Convert brainrot English to normal English: <brainrot sentence>
target_text: <natural normal English sentence>
```

Term definition rows become:

```text
input_text: Define this brainrot term in normal English: <term>
target_text: <clear normal English definition or origin explanation>
```

The filter only rejects rows that are unusable for model training, such as:

- empty rows
- URL-only rows
- corrupted rows
- hallucinated or meaning-breaking targets
- duplicates and near-duplicates
- rows that are not actually brainrot/slang/internet language

Useful glossary rows are not dropped just because they are not sentence
translations. Instead, the script rewrites them into the `term_definition`
format.

Outputs:

- `data/processed/brainrot_dataset_cleaned.csv`
- `data/processed/brainrot_dataset_repaired.csv`
- `data/processed/brainrot_dataset_rejected.csv`

Output schema:

```text
input_text,target_text,task_type,quality_label,reason
```

Typical command:

```powershell
python scripts/filter_training_dataset.py
```

Recognized glossary columns include:

- `term`
- `meaning`

Important current behavior:

- glossary records are converted only as `term -> meaning`
- glossary example sentences are no longer converted into direct training pairs
  because that created noisy definition-substitution rows

## How Data Is Cleaned

The cleaning process now has three stages.

### Stage 1: baseline normalization and filtering

Applied in `clean_and_filter_pairs()` after extraction.

What happens:

- normalize quotes and whitespace
- remove empty or null-like values
- remove identical `brainrot == normal` rows
- remove URL-only rows
- remove symbol-only rows
- remove too-short rows
- remove too-long rows
- exact-deduplicate `(brainrot, normal)` pairs

Output from this stage:

- `data/processed/brainrot_dataset.csv`

### Stage 2: strict quality filtering

Applied in `apply_quality_filters()` when running:

```powershell
python src/prepare_dataset.py --strict
```

The strict filter flags or removes:

- broken fragments
- hallucinated explanation templates
- definition-substitution artifacts
- suspicious length ratios
- low semantic overlap between source and target

Examples of bad rows that are now caught:

- dictionary-definition text pasted into a sentence
- malformed replacements such as `throw forcefullyed`
- templated filler such as `and I think that speaks volumes`
- semantically unrelated rewrites that add new topics not present in the source

There is also a targeted safeguard for the noisier
`projolx/genz_brainrot_dataset` slice, because that source produced several
definition-substitution artifacts in sentence form.

Outputs from strict cleaning:

- `data/processed/brainrot_dataset_cleaned.csv`
- `data/analysis/flagged_bad_pairs.csv`
- `data/analysis/dataset_report.md`

Recommended command:

```powershell
python src/prepare_dataset.py --strict
```

### Stage 3: training-readiness review

Applied in `build_training_ready_dataset()` after strict cleaning.

Purpose:

- keep only rows that can realistically teach a translator model
- rewrite glossary entries when the meaning can be simplified safely
- drop glossary rows that are only etymology, meme history, or unstable
  multi-sense trivia
- drop sentence rows whose `normal` field is still a dictionary explanation
  instead of a plain-English translation

Examples:

- `Gucci`:
  - from `Meaning good, cool, fashionable, or excellent. Used to express approval...`
  - to `good, cool, fashionable, or excellent.`
- `You good?`:
  - from an AAVE origin explanation
  - to `Are you okay?`
- `six-seven (6-7)`:
  - dropped because it is a nonsense meme term without a stable translation target

Outputs from the training-readiness pass:

- `data/processed/brainrot_dataset_training_ready.csv`
- `data/analysis/training_ready_review.csv`

## Final Training Output

The current intermediate normalized file is:

- `data/processed/brainrot_dataset.csv`

The strict-cleaned file is:

- `data/processed/brainrot_dataset_cleaned.csv`

The recommended file for model training is:

- `data/processed/brainrot_dataset_training_ready.csv`

The row-by-row judgment log is:

- `data/analysis/training_ready_review.csv`

Both use the same training schema:

```text
brainrot, normal
```

Use this format only for rows where the target is a real plain-English rewrite
or explanation of the source text.

## What Dataset Type Future Additions Should Follow

Not every new resource should follow the same shape. Use the dataset type that
matches the source.

### Best type for immediate model training: parallel translation pairs

Use this when the source already contains both:

- a slang, meme, or brainrot input
- a real normal-English target

Recommended normalized fields:

```text
text, standard_text, context, role, category, source_dataset, source_url, source_file, split, collected_at
```

Rules:

- `text` = slang or brainrot side
- `standard_text` = real provided plain-English target
- do not invent `standard_text`
- keep provenance fields

This is the best dataset type to expand the translator model right now.

### Good supporting type: glossary or dictionary entries

Use this when the source provides:

- a slang term
- its meaning or definition

Recommended normalized fields:

```text
term, meaning, example, source, source_url, category, collected_at
```

Rules:

- keep the glossary term intact
- keep the definition clean and factual
- keep example text separate from the training-pair layer

This type is useful for slang coverage and future term matching.

### Good future-analysis type: conversation or slang-only corpora

Use this when the source contains:

- slang-rich text
- conversation turns
- public comments
- chat logs

but does not contain reliable normal-English rewrites.

Recommended normalized fields:

```text
text, standard_text, context, role, category, source_dataset, source_url, source_file, split, collected_at
```

Rules:

- leave `standard_text` empty
- do not convert this into training pairs by guessing the target
- keep role and context if available

This type is valuable for:

- future unified datasets
- slang frequency analysis
- term matching
- downstream semantic drift work

### Future cross-source target: unified schema

For Phase 3 and later, new normalized sources should be easy to map into the
unified schema in `codex_prompt.md`:

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

If you are adding a new source now, it is good practice to keep enough
provenance so it can be mapped into this schema later.

## How To Add More Resources

### Option 1: add a new raw file for direct training-pair preparation

Use this when you already have a local file with usable pairs.

Steps:

1. Put the file in `data/raw/`.
2. Use one of the supported extensions:
   - `.csv`
   - `.xlsx`
   - `.json`
   - `.txt`
   - `.md`
3. Make sure the file exposes either:
   - a pair of input/output columns, or
   - `term` and `meaning`
4. Run:

```powershell
python src/prepare_dataset.py --strict
```

5. Review:
   - `data/processed/brainrot_dataset_training_ready.csv`
   - `data/analysis/training_ready_review.csv`
   - `data/analysis/flagged_bad_pairs.csv`
   - `data/analysis/dataset_report.md`

### Option 2: add a new normalized processed seed file

Use this when the source needs a custom normalization step first.

Recommended flow:

1. Write a dedicated normalizer script or notebook.
2. Save the normalized output under `data/processed/`.
3. Match one of the current source contracts:
   - glossary seed
   - parallel translation
   - conversation or slang-only corpus
4. If the file should be auto-included by `src/prepare_dataset.py`, add it to
   `SUPPLEMENTAL_SEED_FILE_GROUPS`.
5. Re-run strict preparation and inspect flagged rows.

This is the cleaner approach when the source is large, messy, or has its own
provider-specific schema.

### Option 3: add a source only for future unified analysis

Use this when the source does not have trustworthy target translations.

Examples:

- public comments
- chat transcripts
- forum-style slang conversations
- meme captions

Recommended rule:

- normalize it like `huggingface_slang_dataset.*`
- keep `standard_text` empty
- preserve metadata
- do not force it into the current `brainrot, normal` training set

## Minimum Quality Rules For New Sources

Any new source should follow these constraints:

- public and legally usable
- no private or deleted content
- no fabricated targets
- no unnecessary personal identifiers
- preserve source provenance
- keep missing optional fields empty in CSV and null in JSON where applicable
- do not merge glossary examples into direct training pairs unless they are real
  human-written rewrites

## Recommended Decision Rule

If the goal is to improve the translator model now:

- prioritize new parallel translation datasets

If the goal is to improve slang coverage and future analysis:

- add glossary or slang-only corpora

If the source has no reliable plain-English target:

- keep it out of the final training-pair CSV for now

## Recommended Verification After Each New Source

After adding a source:

1. Run `python src/prepare_dataset.py --strict`
2. Open `data/analysis/dataset_report.md`
3. Open `data/analysis/flagged_bad_pairs.csv`
4. Spot-check `data/processed/brainrot_dataset_training_ready.csv`
5. Inspect `data/analysis/training_ready_review.csv` for rewritten or dropped rows
6. Add or update tests in `tests/test_prepare_dataset.py` if the new source
   introduces a new edge case
