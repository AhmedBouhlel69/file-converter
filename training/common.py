"""Resource guard and explicit local U2NETP source/checkpoint loading."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

import psutil

from training.dataset import SPLITS, sha256, training_lineage

UPSTREAM_REVISION = "ac7e1c817ecab7c7dff5ce6b1abba61cd213ff29"
GIB = 1024**3


def read_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def validate_lineage(lineage) -> dict:
    if not isinstance(lineage, dict) or lineage.get("schema_version") != 1:
        raise ValueError("A complete training split lineage is required")
    hashes = [lineage.get(key) for key in (
        "prepared_dataset_sha256", "content_sha256", "split_policy_sha256"
    )]
    split_hashes, counts = lineage.get("split_sha256"), lineage.get("sample_counts")
    if not isinstance(split_hashes, dict) or set(split_hashes) != set(SPLITS):
        raise ValueError("Training lineage requires all three split fingerprints")
    hashes.extend(split_hashes.values())
    if any(not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value) for value in hashes):
        raise ValueError("Invalid training lineage fingerprint")
    if not isinstance(counts, dict) or set(counts) != set(SPLITS) or any(
        isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in counts.values()
    ):
        raise ValueError("Training lineage requires positive sample counts for each split")
    return lineage


def read_training_report(path: Path, checkpoint: Path | None = None) -> dict:
    report = read_object(path)
    if (report.get("schema_version") != 1 or report.get("architecture") != "U2NETP"
            or report.get("status") != "candidate_requires_test_evaluation"
            or report.get("test_samples_used_for_training_or_selection") != 0):
        raise ValueError("A completed U2NETP training report with an unused test split is required")
    lineage = validate_lineage(report.get("training_lineage"))
    if report.get("dataset_sha256") != lineage["prepared_dataset_sha256"]:
        raise ValueError("Training report dataset fingerprint differs from its split lineage")
    expected = report.get("best_checkpoint_sha256")
    if not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{64}", expected):
        raise ValueError("Training report lacks its best checkpoint fingerprint")
    if checkpoint is not None and sha256(checkpoint) != expected:
        raise ValueError("Checkpoint does not match the completed training report")
    return report


def validate_candidate_lineage(args, data: dict) -> dict | None:
    """Reject changed candidate/test lineage before backend or Torch imports."""
    if args.registry is None:
        if args.export_report is not None:
            raise ValueError("An export report requires an explicit candidate registry")
        return None  # Installed upstream baseline has no local training lineage.
    if args.export_report is None:
        raise ValueError("Candidate evaluation requires --export-report with training lineage")
    report = read_object(args.export_report)
    if (report.get("schema_version") != 1 or report.get("architecture") != "U2NETP"
            or report.get("status") != "candidate_requires_test_evaluation"):
        raise ValueError("A verified U2NETP export report is required")
    lineage = validate_lineage(report.get("training_lineage"))
    if lineage != training_lineage(data):
        raise ValueError("Candidate training lineage does not match this prepared dataset and held-out split")
    training_report = args.export_report.parent / "training_report.json"
    training = read_training_report(training_report)
    if (sha256(training_report) != report.get("training_report_sha256")
            or training["training_lineage"] != lineage
            or training["best_checkpoint_sha256"] != report.get("checkpoint_sha256")):
        raise ValueError("Candidate export/training report lineage is inconsistent")
    registry = read_object(args.registry)
    config = registry.get("fast")
    if not isinstance(config, dict):
        raise ValueError("Candidate registry requires the exported Fast profile")
    filename = config.get("file")
    if not isinstance(filename, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.onnx", filename):
        raise ValueError("Candidate registry has an invalid model filename")
    if args.models_dir is None:
        raise ValueError("Candidate evaluation requires its explicit --models-dir")
    actual_hash = sha256(args.models_dir / filename)
    if actual_hash != report.get("onnx_sha256") or actual_hash != config.get("sha256"):
        raise ValueError("Candidate ONNX does not match the export report and registry")
    return lineage


def load_model(torch, upstream: Path, checkpoint: Path):
    source = upstream.resolve(strict=True) / "model" / "u2net.py"
    revision = subprocess.check_output(
        ["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != UPSTREAM_REVISION:
        raise ValueError(f"Use the documented U-2-Net revision {UPSTREAM_REVISION}")
    if subprocess.run(["git", "-C", str(upstream), "diff", "--quiet", "HEAD", "--",
                       "model/u2net.py"], check=False).returncode:
        raise ValueError("The pinned U2NETP source file has local modifications")
    spec = importlib.util.spec_from_file_location("training_u2net_architecture", source)
    if spec is None or spec.loader is None:
        raise ValueError("Cannot load the explicit local U2NETP source")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    model = module.U2NETP(3, 1)
    # No download, arbitrary pickle fallback, optimizer restore or ONNX-to-Torch conversion.
    state = torch.load(checkpoint, map_location="cpu", weights_only=True)
    model.load_state_dict(state, strict=True)
    return model, {"upstream_revision": revision, "source_sha256": sha256(source),
                   "checkpoint_sha256": sha256(checkpoint)}


def positive_integer(value: str) -> int:
    result = int(value)
    if result < 1:
        raise ValueError("Expected a positive integer")
    return result


def add_guard_arguments(parser) -> None:
    parser.add_argument("--max-rss-gib", type=float, default=2.5)
    parser.add_argument("--min-free-gib", type=float, default=1.5)
    parser.add_argument("--timeout-seconds", type=positive_integer, default=1800)
    parser.add_argument("--_worker", action="store_true", help=argparse.SUPPRESS)


def _stop_tree(owner) -> None:
    try:
        processes = [owner, *owner.children(recursive=True)]
    except psutil.NoSuchProcess:
        return
    for process in reversed(processes):
        try:
            process.kill()
        except psutil.NoSuchProcess:
            pass
    psutil.wait_procs(processes, timeout=5)


def guarded_run(module: str, args) -> int:
    """Run only this command's owned child; no unrelated application is touched."""
    import math

    for key in ("max_rss_gib", "min_free_gib"):
        if not math.isfinite(getattr(args, key)) or getattr(args, key) <= 0:
            raise ValueError(f"{key} must be finite and positive")
    if psutil.virtual_memory().available < args.min_free_gib * GIB:
        raise ValueError("Not enough free system memory for the requested training guard")
    args.output.mkdir(parents=True, exist_ok=False)
    environment = os.environ.copy()
    environment.update({"OMP_NUM_THREADS": "2", "MKL_NUM_THREADS": "2",
                        "OPENBLAS_NUM_THREADS": "2"})
    command = [sys.executable, "-m", module, *sys.argv[1:], "--_worker"]
    peak = 0
    free_minimum = psutil.virtual_memory().available
    reason = None
    start = time.monotonic()
    with (args.output / "worker.log").open("x", encoding="utf-8") as log:
        child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=environment)
        owner = None
        try:
            owner = psutil.Process(child.pid)
            while child.poll() is None:
                available = psutil.virtual_memory().available
                free_minimum = min(free_minimum, available)
                rss = 0
                try:
                    for process in [owner, *owner.children(recursive=True)]:
                        try:
                            rss += process.memory_info().rss
                        except psutil.NoSuchProcess:
                            pass
                except psutil.NoSuchProcess:
                    break
                peak = max(peak, rss)
                if available < args.min_free_gib * GIB:
                    reason = "system free memory limit"
                elif rss > args.max_rss_gib * GIB:
                    reason = "owned process tree RSS limit"
                elif time.monotonic() - start > args.timeout_seconds:
                    reason = "time limit"
                if reason:
                    _stop_tree(owner)
                    break
                time.sleep(.1)
            code = child.wait(timeout=10)
        except BaseException:
            if owner is not None:
                _stop_tree(owner)
            elif child.poll() is None:
                child.kill()
            child.wait(timeout=10)
            raise
    result = {"returncode": code, "guard_reason": reason, "peak_tree_rss_bytes": peak,
              "minimum_system_free_bytes": free_minimum,
              "elapsed_seconds": time.monotonic() - start,
              "sampling_interval_seconds": .1}
    (args.output / "resource_report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"Worker log: {args.output.resolve() / 'worker.log'}")
    return code if code and not reason else (1 if reason else 0)


def atomic_weights(torch, model, destination: Path) -> None:
    temporary = destination.with_suffix(".pth.new")
    torch.save({name: value.detach().cpu() for name, value in model.state_dict().items()}, temporary)
    temporary.replace(destination)
