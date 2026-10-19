"""Export a local U2NETP checkpoint to a separate verified ONNX candidate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from training.common import add_guard_arguments, guarded_run, load_model, read_training_report
from training.dataset import sha256


def worker(args) -> None:
    training = read_training_report(args.training_report, args.checkpoint)
    import numpy as np
    import onnx
    import onnxruntime as ort
    import torch

    torch.manual_seed(42)
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    model, provenance = load_model(torch, args.upstream, args.checkpoint)
    if provenance["checkpoint_sha256"] != training["best_checkpoint_sha256"]:
        raise ValueError("Checkpoint changed while exporting its recorded training lineage")
    model.eval()

    class FusedMask(torch.nn.Module):
        def __init__(self, network):
            super().__init__()
            self.network = network

        def forward(self, pixels):
            return self.network(pixels)[0]

    fused = FusedMask(model)
    temporary = args.output / "candidate.onnx.new"
    destination = args.output / "candidate.onnx"
    with torch.inference_mode():
        torch.onnx.export(fused, torch.zeros(1, 3, 320, 320), temporary,
                          input_names=["input"], output_names=["mask"],
                          opset_version=17, dynamo=False, external_data=False)
    onnx.checker.check_model(str(temporary), full_check=True)
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    options.enable_cpu_mem_arena = False
    options.enable_mem_pattern = False
    session = ort.InferenceSession(str(temporary), options, providers=["CPUExecutionProvider"])
    maximum_error = 0.
    rng = np.random.default_rng(42)
    with torch.inference_mode():
        for _ in range(3):
            pixels = rng.uniform(-2.1, 2.6, (1, 3, 320, 320)).astype(np.float32)
            expected = fused(torch.from_numpy(pixels)).numpy()
            actual = session.run(["mask"], {"input": pixels})[0]
            if not np.isfinite(actual).all() or not np.allclose(actual, expected, rtol=1e-4, atol=1e-4):
                raise ValueError("ONNX output failed the PyTorch numerical equivalence check")
            maximum_error = max(maximum_error, float(np.max(np.abs(actual - expected))))
    del session
    temporary.replace(destination)
    # The app registry is untouched. Rights are deliberately unverified until
    # the checkpoint and dataset terms have been reviewed for distribution.
    config = {
        "name": "u2netp-local-candidate", "file": destination.name,
        "sha256": sha256(destination), "size_bytes": destination.stat().st_size,
        "input_size": [320, 320], "mean": [.485, .456, .406], "std": [.229, .224, .225],
        "normalize_max": True, "minmax": True, "output_index": 0,
        "output_activation": "none", "precision": "fp32", "licence": "unverified",
        "commercial_use": False, "source": "https://github.com/xuebinqin/U-2-Net",
        "provenance": "Local candidate; see export_report.json; not promoted to the app",
    }
    (args.output / "registry.json").write_text(json.dumps({"fast": config}, indent=2), encoding="utf-8")
    copied_training_report = args.output / "training_report.json"
    copied_training_report.write_bytes(args.training_report.read_bytes())
    report = {"schema_version": 1, "architecture": "U2NETP",
              "status": "candidate_requires_test_evaluation", "provenance": provenance,
              "training_lineage": training["training_lineage"],
              "training_report_sha256": sha256(copied_training_report),
              "checkpoint_sha256": training["best_checkpoint_sha256"],
              "onnx_sha256": config["sha256"], "onnx_bytes": config["size_bytes"],
              "maximum_absolute_error_on_three_random_tensors": maximum_error,
              "quality_assessed": False, "application_registry_modified": False}
    (args.output / "export_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--training-report", type=Path, required=True,
                        help="Completed fine-tuning report matching this checkpoint")
    parser.add_argument("--output", type=Path, required=True, help="New export directory")
    add_guard_arguments(parser)
    args = parser.parse_args()
    try:
        if args._worker:
            worker(args)
        else:
            read_training_report(args.training_report, args.checkpoint)
            if not args.checkpoint.is_file() or not (args.upstream / "model" / "u2net.py").is_file():
                raise ValueError("Explicit local U2NETP source and trainable checkpoint are required")
            raise SystemExit(guarded_run("training.export_u2netp", args))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(1, f"Export stopped: {exc}\n")


if __name__ == "__main__":
    main()
