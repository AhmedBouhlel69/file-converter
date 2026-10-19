"""Synthetic metadata fixtures check lineage only; no model is loaded."""
import builtins
import json
from types import SimpleNamespace

import pytest

from training.common import validate_candidate_lineage
from training.dataset import prepare, sha256, training_lineage, write_new_json
from training.evaluate_candidate import worker as evaluation_worker
from training.export_u2netp import worker as export_worker
from training.tests.test_dataset import pairs  # reuse the explicit synthetic dataset fixture


@pytest.fixture
def candidate(pairs):
    source, _ = pairs
    data = prepare(source)
    prepared = source.parent / "prepared.json"
    write_new_json(prepared, data)
    directory = source.parent / "export"
    directory.mkdir()
    checkpoint = source.parent / "best.pth"
    checkpoint.write_bytes(b"synthetic checkpoint metadata fixture, never loaded")
    model = directory / "candidate.onnx"
    model.write_bytes(b"synthetic ONNX metadata fixture, never loaded")
    training_report = directory / "training_report.json"
    write_new_json(training_report, {
        "schema_version": 1, "architecture": "U2NETP", "status": "candidate_requires_test_evaluation",
        "test_samples_used_for_training_or_selection": 0,
        "dataset_sha256": data["dataset_sha256"],
        "best_checkpoint_sha256": sha256(checkpoint), "training_lineage": training_lineage(data),
    })
    export_report = directory / "export_report.json"
    write_new_json(export_report, {
        "schema_version": 1, "architecture": "U2NETP", "status": "candidate_requires_test_evaluation",
        "onnx_sha256": sha256(model), "checkpoint_sha256": sha256(checkpoint),
        "training_report_sha256": sha256(training_report), "training_lineage": training_lineage(data),
    })
    registry = directory / "registry.json"
    write_new_json(registry, {"fast": {"file": model.name, "sha256": sha256(model)}})
    args = SimpleNamespace(dataset=prepared, registry=registry, models_dir=directory,
                           export_report=export_report, output=source.parent / "evaluation")
    return source, data, args, checkpoint


def refuse_model_imports(monkeypatch):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.split(".")[0] in {"torch", "onnxruntime", "bgremove"}:
            pytest.fail(f"Rejected lineage must fail before importing model runtime: {name}")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)


def test_matching_candidate_lineage_is_accepted(candidate):
    _, data, args, _ = candidate
    assert validate_candidate_lineage(args, data) == training_lineage(data)


def test_candidate_seed_mismatch_rejected_before_model_import(candidate, monkeypatch):
    source, _, args, _ = candidate
    changed = source.parent / "different-split.json"
    write_new_json(changed, prepare(source, seed=43))
    args.dataset = changed
    refuse_model_imports(monkeypatch)
    with pytest.raises(ValueError, match="training lineage does not match"):
        evaluation_worker(args)
    assert not args.output.exists()


def test_candidate_requires_export_report(candidate):
    _, data, args, _ = candidate
    args.export_report = None
    with pytest.raises(ValueError, match="requires --export-report"):
        validate_candidate_lineage(args, data)


def test_installed_baseline_has_no_local_training_lineage(candidate):
    _, data, args, _ = candidate
    args.registry = args.export_report = None
    assert validate_candidate_lineage(args, data) is None


def test_changed_candidate_file_rejected_before_model_import(candidate, monkeypatch):
    _, _, args, _ = candidate
    (args.models_dir / "candidate.onnx").write_bytes(b"changed candidate")
    refuse_model_imports(monkeypatch)
    with pytest.raises(ValueError, match="ONNX does not match"):
        evaluation_worker(args)


def test_changed_training_report_is_rejected(candidate):
    _, data, args, _ = candidate
    training_path = args.export_report.parent / "training_report.json"
    report = json.loads(training_path.read_text(encoding="utf-8"))
    report["note"] = "changed after export"
    training_path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError, match="export/training report lineage is inconsistent"):
        validate_candidate_lineage(args, data)


def test_export_checkpoint_mismatch_rejected_before_torch_import(candidate, monkeypatch):
    _, _, args, checkpoint = candidate
    checkpoint.write_bytes(b"changed checkpoint")
    export_args = SimpleNamespace(checkpoint=checkpoint,
                                  training_report=args.export_report.parent / "training_report.json")
    refuse_model_imports(monkeypatch)
    with pytest.raises(ValueError, match="Checkpoint does not match"):
        export_worker(export_args)
