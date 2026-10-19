"""Evaluate either the installed Fast baseline or a separate candidate on held-out data.

No training samples are evaluated and no model is promoted by this command.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import sys
from time import perf_counter

from training.common import add_guard_arguments, guarded_run, validate_candidate_lineage
from training.dataset import load_prepared, sha256


def worker(args) -> None:
    data = load_prepared(args.dataset)
    lineage = validate_candidate_lineage(args, data)
    import numpy as np
    import psutil

    # Read this repository's backend; no desktop UI or PyTorch is imported.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backgroundG" / "src"))
    from bgremove.evaluation import evaluate_manifest
    from bgremove.remover import Remover

    remover = Remover("fast", "cpu", registry=args.registry, model_dir=args.models_dir,
                      threads=2, strict_device=True, allow_noncommercial=bool(args.registry))
    samples, timings = [], {}
    for index, row in enumerate(data["splits"]["test"]):
        result = remover.remove(row["image"])
        prediction = args.output / f"mask-{index:06d}.png"
        start = perf_counter()
        result.save_mask(prediction)
        result.timings["export"] = perf_counter() - start
        for stage, value in result.timings.items():
            timings.setdefault(stage, []).append(value)
        samples.append({"id": row["id"], "image": row["image"],
                        "ground_truth": row["mask"], "prediction": str(prediction.resolve())})
    manifest = args.output / "evaluation_manifest.json"
    manifest.write_text(json.dumps({"profile": "fast", "samples": samples}, indent=2), encoding="utf-8")
    report = evaluate_manifest(manifest, matting=True)
    report.update({
        "model_sha256": sha256(remover.path), "provider": result.provider,
        "runtime_options": {"device": "cpu", "threads": 2, "refinement": "default"},
        "environment": {"cpu": platform.processor(), "machine": platform.machine(),
                        "logical_cpu_count": psutil.cpu_count()},
        "timing_unit": "seconds", "timing_protocol": "one full pipeline per held-out test image",
        "stages": {stage: {"median": float(np.median(values)), "p95": float(np.percentile(values, 95))}
                   for stage, values in timings.items()},
        "evaluation_prepared_dataset_sha256": data["dataset_sha256"],
        "training_lineage": lineage,
        "export_report_sha256": sha256(args.export_report) if args.export_report else None,
        "warning": "Small test sets give unstable p95 estimates; use representative release coverage",
    })
    (args.output / "evaluation_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"test_samples": len(samples), "metrics": report["metrics"]}, indent=2), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--registry", type=Path, help="Omit for installed Fast; use exported registry for candidate")
    parser.add_argument("--export-report", type=Path,
                        help="Required with candidate registry; binds training checkpoint and held-out split")
    parser.add_argument("--models-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True, help="New evaluation directory")
    add_guard_arguments(parser)
    args = parser.parse_args()
    try:
        if args._worker:
            worker(args)
        else:
            data = load_prepared(args.dataset)
            validate_candidate_lineage(args, data)
            raise SystemExit(guarded_run("training.evaluate_candidate", args))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(1, f"Evaluation stopped: {exc}\n")


if __name__ == "__main__":
    main()
