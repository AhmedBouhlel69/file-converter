"""Bounded optional U2NETP fine-tuning; requires reviewed pairs and a local .pth.

This module imports PyTorch only inside the guarded worker. --help never loads it.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import random

from training.common import add_guard_arguments, atomic_weights, guarded_run, load_model, positive_integer
from training.dataset import load_prepared, read_alpha, read_rgb, sha256, training_lineage


def worker(args) -> None:
    data = load_prepared(args.dataset)
    import cv2
    import numpy as np
    import torch

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    if args.device == "cuda":
        if not torch.cuda.is_available():
            raise ValueError("CUDA was requested but is unavailable in this training environment")
        torch.cuda.set_per_process_memory_fraction(.5)
        torch.cuda.manual_seed_all(args.seed)
    device = torch.device(args.device)
    model, provenance = load_model(torch, args.upstream, args.checkpoint)
    model.to(device)

    class Pairs(torch.utils.data.Dataset):
        def __init__(self, rows, augment=False):
            self.rows, self.augment = rows, augment

        def __len__(self):
            return len(self.rows)

        def __getitem__(self, index):
            row = self.rows[index]
            rgb, alpha = read_rgb(Path(row["image"])), read_alpha(Path(row["mask"]))
            if rgb.shape[:2] != alpha.shape:
                raise ValueError(f"Image/mask dimensions changed: {row['id']}")
            if self.augment and random.random() < .5:
                rgb, alpha = rgb[:, ::-1], alpha[:, ::-1]
            # Match the registered Fast profile: OpenCV bilinear RGB, image-max
            # normalization, ImageNet channel normalization, 320x320 NCHW.
            pixels = cv2.resize(rgb, (320, 320), interpolation=cv2.INTER_LINEAR).astype(np.float32)
            pixels /= max(float(pixels.max()), 1.)
            pixels = (pixels - np.array([.485, .456, .406], dtype=np.float32)) / np.array(
                [.229, .224, .225], dtype=np.float32)
            target = cv2.resize(alpha, (320, 320), interpolation=cv2.INTER_LINEAR)
            return torch.from_numpy(np.ascontiguousarray(pixels.transpose(2, 0, 1))), \
                torch.from_numpy(np.ascontiguousarray(target[None]))

    generator = torch.Generator().manual_seed(args.seed)
    train = torch.utils.data.DataLoader(Pairs(data["splits"]["train"], True), batch_size=1,
                                        shuffle=True, num_workers=0, pin_memory=False, generator=generator)
    validation = torch.utils.data.DataLoader(Pairs(data["splits"]["validation"]), batch_size=1,
                                             shuffle=False, num_workers=0, pin_memory=False)
    # Test data remains unseen; it is reserved for independent release evaluation.
    optimizer = torch.optim.Adam(model.parameters(), lr=args.learning_rate)
    best, stale, steps = float("inf"), 0, 0
    history = []
    for epoch in range(args.epochs):
        model.train()
        optimizer.zero_grad(set_to_none=True)
        losses = []
        pending = 0
        for pixels, target in train:
            pixels, target = pixels.to(device), target.to(device)
            outputs = model(pixels)
            if len(outputs) != 7:
                raise ValueError("Expected seven U2NETP probability outputs")
            loss = sum(torch.nn.functional.binary_cross_entropy(output, target) for output in outputs) / 7
            if not torch.isfinite(loss):
                raise ValueError("Training loss became nonfinite")
            (loss / args.accumulate).backward()
            losses.append(float(loss.detach().cpu()))
            pending += 1
            steps += 1
            if pending == args.accumulate:
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.)
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)
                pending = 0
            del outputs, loss, pixels, target
            if steps >= args.max_steps:
                break
        if pending:
            # Renormalize a short final accumulation window to its actual size.
            for parameter in model.parameters():
                if parameter.grad is not None:
                    parameter.grad.mul_(args.accumulate / pending)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.)
            optimizer.step()
            optimizer.zero_grad(set_to_none=True)
        model.eval()
        error, count = 0., 0
        with torch.inference_mode():
            for pixels, target in validation:
                output = model(pixels.to(device))[0]
                error += float(torch.abs(output - target.to(device)).mean().cpu())
                count += 1
        mae = error / count
        record = {"epoch": epoch + 1, "steps": steps, "training_bce": sum(losses) / len(losses),
                  "validation_mae_at_320": mae}
        history.append(record)
        print(json.dumps(record), flush=True)
        if mae < best:
            best, stale = mae, 0
            atomic_weights(torch, model, args.output / "best.pth")
        else:
            stale += 1
        (args.output / "history.json").write_text(json.dumps(history, indent=2), encoding="utf-8")
        if stale >= args.patience or steps >= args.max_steps:
            break
    # Refuse to issue a completed lineage report if inputs or the prepared split
    # changed during this run. Training data is expected to remain immutable.
    if load_prepared(args.dataset)["dataset_sha256"] != data["dataset_sha256"]:
        raise ValueError("Prepared dataset changed during fine-tuning")
    report = {"schema_version": 1, "architecture": "U2NETP", "status": "candidate_requires_test_evaluation",
              "dataset_sha256": data["dataset_sha256"], "provenance": provenance,
              "training_lineage": training_lineage(data),
              "best_checkpoint_sha256": sha256(args.output / "best.pth"),
              "settings": {key: str(value) if isinstance(value, Path) else value
                           for key, value in vars(args).items() if not key.startswith("_")},
              "best_validation_mae_at_320": best, "training_steps": steps,
              "test_samples_used_for_training_or_selection": 0}
    (args.output / "training_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New run directory, must not exist")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--epochs", type=positive_integer, default=5)
    parser.add_argument("--max-steps", type=positive_integer, default=500)
    parser.add_argument("--accumulate", type=positive_integer, default=4)
    parser.add_argument("--patience", type=positive_integer, default=2)
    parser.add_argument("--learning-rate", type=float, default=1e-5)
    parser.add_argument("--seed", type=int, default=42)
    add_guard_arguments(parser)
    args = parser.parse_args()
    try:
        if not math.isfinite(args.learning_rate) or not 0 < args.learning_rate <= .01:
            raise ValueError("learning-rate must be finite and in (0, .01]")
        if args._worker:
            worker(args)
        else:
            load_prepared(args.dataset)
            if not args.checkpoint.is_file() or not (args.upstream / "model" / "u2net.py").is_file():
                raise ValueError("Explicit local U2NETP source and trainable checkpoint are required")
            raise SystemExit(guarded_run("training.finetune_u2netp", args))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(1, f"Fine-tuning stopped: {exc}\n")


if __name__ == "__main__":
    main()
