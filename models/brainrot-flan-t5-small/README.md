# Local Model Folder

Place the trained Hugging Face model files from Google Colab in this folder.

Expected example files:

- `config.json`
- `generation_config.json`
- `model.safetensors`
- `special_tokens_map.json`
- `spiece.model`
- `tokenizer.json`
- `tokenizer_config.json`

The local tester at `src/test_model.py` and the Flask API at `api/app.py` both
load the model from this directory.
