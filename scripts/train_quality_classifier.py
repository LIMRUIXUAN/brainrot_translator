from __future__ import annotations

import argparse
import csv
import json
import os
import random
from pathlib import Path

os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_TORCH", "1")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

import torch
from torch.utils.data import DataLoader, Dataset
from tqdm.auto import tqdm
from transformers import AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "processed" / "translation_quality_classifier_dataset.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "models" / "brainrot-quality-classifier-v1"


class QualityDataset(Dataset):
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> dict[str, object]:
        return self.rows[index]


def read_rows(path: Path) -> list[dict[str, object]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = {"source_text", "candidate_translation", "label"} - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing required columns in {path}: {sorted(missing)}")

        rows: list[dict[str, object]] = []
        for row in reader:
            source_text = " ".join((row.get("source_text") or "").strip().split())
            candidate = " ".join((row.get("candidate_translation") or "").strip().split())
            if not source_text or not candidate:
                continue
            label = int(row.get("label") or 0)
            if label not in {0, 1}:
                raise ValueError(f"Invalid label {label}; expected 0 or 1")
            rows.append(
                {
                    "text": (
                        f"Source brainrot text: {source_text}\n"
                        f"Candidate normal English translation: {candidate}"
                    ),
                    "label": label,
                    "source_row_id": row.get("source_row_id") or source_text,
                }
            )
    if len(rows) < 100:
        raise ValueError(f"Need at least 100 classifier rows, found {len(rows)}")
    return rows


def split_rows(rows: list[dict[str, object]], eval_ratio: float, seed: int) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    rng = random.Random(seed)
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault(str(row["source_row_id"]), []).append(row)

    groups = list(grouped.values())
    rng.shuffle(groups)
    eval_target = max(1, int(len(rows) * eval_ratio))
    train_rows: list[dict[str, object]] = []
    eval_rows: list[dict[str, object]] = []
    for group in groups:
        if len(eval_rows) < eval_target:
            eval_rows.extend(group)
        else:
            train_rows.extend(group)

    rng.shuffle(train_rows)
    rng.shuffle(eval_rows)
    return train_rows, eval_rows


def make_collate_fn(tokenizer, max_length: int, device: torch.device):
    def collate(rows: list[dict[str, object]]) -> dict[str, torch.Tensor]:
        encoded = tokenizer(
            [str(row["text"]) for row in rows],
            padding=True,
            truncation=True,
            max_length=max_length,
            return_tensors="pt",
        )
        encoded["labels"] = torch.tensor([int(row["label"]) for row in rows], dtype=torch.long)
        return {key: value.to(device) for key, value in encoded.items()}

    return collate


def evaluate(model, loader: DataLoader) -> dict[str, float]:
    model.eval()
    total_loss = 0.0
    correct = 0
    total = 0
    with torch.no_grad():
        for batch in loader:
            outputs = model(**batch)
            total_loss += float(outputs.loss.detach().cpu().item())
            predictions = outputs.logits.argmax(dim=-1)
            correct += int((predictions == batch["labels"]).sum().detach().cpu().item())
            total += int(batch["labels"].numel())
    model.train()
    return {
        "eval_loss": total_loss / max(1, len(loader)),
        "eval_accuracy": correct / max(1, total),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train the local good/bad translation quality classifier.",
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--base-model", default="distilbert-base-uncased")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--max-length", type=int, default=192)
    parser.add_argument("--eval-ratio", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    torch.manual_seed(args.seed)
    random.seed(args.seed)

    rows = read_rows(args.input)
    train_rows, eval_rows = split_rows(rows, args.eval_ratio, args.seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device: {device}")
    print(f"train rows: {len(train_rows)}")
    print(f"eval rows: {len(eval_rows)}")

    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    model = AutoModelForSequenceClassification.from_pretrained(
        args.base_model,
        num_labels=2,
        id2label={0: "bad_translation", 1: "good_translation"},
        label2id={"bad_translation": 0, "good_translation": 1},
    )
    model.to(device)

    collate_fn = make_collate_fn(tokenizer, args.max_length, device)
    train_loader = DataLoader(QualityDataset(train_rows), batch_size=args.batch_size, shuffle=True, collate_fn=collate_fn)
    eval_loader = DataLoader(QualityDataset(eval_rows), batch_size=args.batch_size, shuffle=False, collate_fn=collate_fn)

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate)
    total_steps = len(train_loader) * args.epochs
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=max(1, total_steps // 10),
        num_training_steps=total_steps,
    )

    history = []
    model.train()
    for epoch in range(1, args.epochs + 1):
        running_loss = 0.0
        progress = tqdm(train_loader, desc=f"Epoch {epoch}/{args.epochs}")
        for step, batch in enumerate(progress, start=1):
            outputs = model(**batch)
            loss = outputs.loss
            if not torch.isfinite(loss):
                raise RuntimeError(f"Non-finite loss at epoch {epoch}, step {step}: {loss.item()}")

            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad(set_to_none=True)

            running_loss += float(loss.detach().cpu().item())
            if step % 25 == 0:
                progress.set_postfix(train_loss=running_loss / step)

        metrics = evaluate(model, eval_loader)
        metrics["epoch"] = epoch
        metrics["train_loss"] = running_loss / max(1, len(train_loader))
        history.append(metrics)
        print(
            f"epoch={epoch} train_loss={metrics['train_loss']:.4f} "
            f"eval_loss={metrics['eval_loss']:.4f} eval_accuracy={metrics['eval_accuracy']:.4f}"
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)
    report = {
        "base_model": args.base_model,
        "train_rows": len(train_rows),
        "eval_rows": len(eval_rows),
        "history": history,
    }
    (args.output_dir / "quality_classifier_report.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    print(f"saved classifier: {args.output_dir}")


if __name__ == "__main__":
    main()
