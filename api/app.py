from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = PROJECT_ROOT / "models" / "brainrot-translator-v1"
PROMPT_PREFIX = "Convert brainrot English to normal English: "

app = Flask(__name__)
CORS(app)


@lru_cache(maxsize=1)
def get_model_components() -> tuple[AutoTokenizer, AutoModelForSeq2SeqLM]:
    if not MODEL_DIR.exists():
        raise FileNotFoundError(
            "Model folder not found. Place the trained model inside "
            f"{MODEL_DIR} before starting the API."
        )

    tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
    model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_DIR)
    return tokenizer, model


def translate_text(text: str) -> str:
    tokenizer, model = get_model_components()
    prompt = f"{PROMPT_PREFIX}{text.strip()}"
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=128)
    outputs = model.generate(**inputs, max_new_tokens=128)
    return tokenizer.decode(outputs[0], skip_special_tokens=True).strip()


@app.get("/health")
def health() -> tuple[dict[str, str], int]:
    return {"status": "ok"}, 200


@app.post("/translate")
def translate() -> tuple[object, int]:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be valid JSON."}), 400

    text = str(payload.get("text", "")).strip()
    if "text" not in payload:
        return jsonify({"error": "Missing 'text' field."}), 400
    if not text:
        return jsonify({"error": "The 'text' field cannot be empty."}), 400

    try:
        normal_text = translate_text(text)
    except FileNotFoundError as error:
        return jsonify({"error": str(error)}), 500
    except Exception as error:
        return jsonify({"error": f"Generation failed: {error}"}), 500

    return jsonify({"normal": normal_text}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
