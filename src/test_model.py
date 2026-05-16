from __future__ import annotations

from pathlib import Path

from transformers import AutoModelForSeq2SeqLM, AutoTokenizer


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = PROJECT_ROOT / "models" / "brainrot-translator-v1"
PROMPT_PREFIX = "Convert brainrot English to normal English: "
EXIT_COMMANDS = {"exit", "quit", "q"}


def load_local_model() -> tuple[AutoTokenizer, AutoModelForSeq2SeqLM]:
    if not MODEL_DIR.exists():
        raise FileNotFoundError(
            "Model folder not found. Place your trained model inside "
            f"{MODEL_DIR} and try again."
        )

    try:
        tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
        model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_DIR)
    except Exception as error:
        raise RuntimeError(
            "The model folder exists, but it could not be loaded as a Hugging Face model. "
            f"Make sure the trained files are inside {MODEL_DIR}. Original error: {error}"
        ) from error

    return tokenizer, model


def translate_text(
    text: str,
    tokenizer: AutoTokenizer,
    model: AutoModelForSeq2SeqLM,
    max_new_tokens: int = 128,
) -> str:
    prompt = f"{PROMPT_PREFIX}{text.strip()}"
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=128)
    outputs = model.generate(**inputs, max_new_tokens=max_new_tokens)
    return tokenizer.decode(outputs[0], skip_special_tokens=True).strip()


def main() -> None:
    try:
        tokenizer, model = load_local_model()
    except (FileNotFoundError, RuntimeError) as error:
        print(error)
        return

    print(f"Loaded model from: {MODEL_DIR}")
    print("Type 'exit', 'quit', or 'q' to stop.")

    while True:
        user_text = input("Enter brainrot text: ").strip()
        if user_text.lower() in EXIT_COMMANDS:
            print("Exiting model tester.")
            break
        if not user_text:
            print("Please enter some text to translate.")
            continue

        try:
            normal_text = translate_text(user_text, tokenizer, model)
        except Exception as error:
            print(f"Generation failed: {error}")
            continue

        print(f"Normal English: {normal_text}")


if __name__ == "__main__":
    main()
