import copy
import json
import socket

import pytest
from PIL import Image
from typer.testing import CliRunner

from bgremove.cli import app
from bgremove.evaluation import compare_reports, evaluate_manifest


def test_cli_quality_timing_gate_roundtrip_offline(model, tmp_path, monkeypatch):
    """Exercise real ONNX, CLI reports and release decisions with a tiny local fixture."""

    def blocked(*args, **kwargs):
        raise AssertionError("Report commands must not use the network")

    monkeypatch.setattr(socket, "socket", blocked)
    registry, directory = model
    runner = CliRunner()
    source = tmp_path / "source.png"
    Image.new("RGB", (12, 8), "white").save(source)
    output = tmp_path / "removed"
    common = ["--registry", str(registry), "--model-dir", str(directory), "--device", "cpu"]
    removed = runner.invoke(
        app, [str(source), "-o", str(output), "--save-mask", *common], catch_exceptions=False
    )
    assert removed.exit_code == 0, removed.output
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "profile": "balanced",
                "samples": [
                    {
                        "id": "white",
                        "image": source.name,
                        "prediction": "removed/source_mask.png",
                        "ground_truth": "removed/source_mask.png",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    timings = tmp_path / "timings.json"
    benchmarked = runner.invoke(
        app,
        [
            "bench",
            str(source),
            "-o",
            str(timings),
            "--sizes",
            "0.0002",
            "--runs",
            "2",
            "--warmups",
            "1",
            *common,
        ],
        catch_exceptions=False,
    )
    assert benchmarked.exit_code == 0, benchmarked.output
    timing_report = json.loads(timings.read_text())
    stages = timing_report["sizes"]["0.0002mp"]["stages"]
    assert {
        "load",
        "session",
        "preprocess",
        "inference",
        "postprocess",
        "refine",
        "compose",
        "export",
        "total",
    } <= stages.keys()
    assert timing_report["sizes"]["0.0002mp"]["provider"] == "CPUExecutionProvider"
    candidate = tmp_path / "candidate.json"
    evaluated = runner.invoke(
        app,
        ["evaluate", str(manifest), "-o", str(candidate), "--benchmark", str(timings)],
        catch_exceptions=False,
    )
    assert evaluated.exit_code == 0, evaluated.output
    report = json.loads(candidate.read_text())
    assert report["metrics"]["iou"] == 1
    assert report["sample_count"] == 1
    assert report["sizes"] == timing_report["sizes"]
    baseline = tmp_path / "baseline.json"
    baseline.write_text(candidate.read_text(), encoding="utf-8")
    gate_path = tmp_path / "gate.json"
    passed = runner.invoke(
        app,
        ["gate", str(baseline), str(candidate), "--output", str(gate_path)],
        catch_exceptions=False,
    )
    assert passed.exit_code == 0, passed.output
    assert json.loads(gate_path.read_text())["passed"]
    report["sizes"]["0.0002mp"]["stages"]["export"]["p95"] *= 1.2
    candidate.write_text(json.dumps(report), encoding="utf-8")
    failed = runner.invoke(app, ["gate", str(baseline), str(candidate)], catch_exceptions=False)
    assert failed.exit_code == 1
    assert "export.p95 regressed" in failed.output


def test_evaluate_bad_benchmark_schema_is_readable_error(tmp_path):
    Image.new("L", (2, 2), 255).save(tmp_path / "mask.png")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "profile": "balanced",
                "samples": [
                    {
                        "prediction": "mask.png",
                        "ground_truth": "mask.png",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    benchmark = tmp_path / "benchmark.json"
    benchmark.write_text("[]", encoding="utf-8")
    result = CliRunner().invoke(
        app,
        [
            "evaluate",
            str(manifest),
            "-o",
            str(tmp_path / "report.json"),
            "--benchmark",
            str(benchmark),
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 2
    assert "object" in result.output.lower()
    assert not (tmp_path / "report.json").exists()


def test_benchmark_invalid_arguments_are_readable_errors(model, tmp_path):
    registry, directory = model
    source = tmp_path / "image.png"
    Image.new("RGB", (2, 2)).save(source)
    result = CliRunner().invoke(
        app,
        [
            "bench",
            str(source),
            "-o",
            str(tmp_path / "report.json"),
            "--registry",
            str(registry),
            "--model-dir",
            str(directory),
            "--sizes",
            "0.0002",
            "--runs",
            "0",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 2
    assert "runs must be a positive integer" in result.output
    assert not (tmp_path / "report.json").exists()


def test_dataset_fingerprint_ignores_predictions_but_detects_changed_truth(tmp_path):
    Image.new("L", (2, 2), 255).save(tmp_path / "truth.png")
    Image.new("L", (2, 2), 255).save(tmp_path / "predicted.png")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"samples": [{"prediction": "predicted.png", "ground_truth": "truth.png"}]})
    )
    original = evaluate_manifest(manifest)
    Image.new("L", (2, 2), 0).save(tmp_path / "predicted.png")
    assert evaluate_manifest(manifest)["dataset"] == original["dataset"]
    Image.new("L", (2, 2), 0).save(tmp_path / "truth.png")
    assert evaluate_manifest(manifest)["dataset"] != original["dataset"]


@pytest.mark.parametrize("field", ["dataset", "settings", "sample_count", "runtime_options"])
def test_gate_rejects_changed_evaluation_conditions(field):
    report = {
        "metrics": {"iou": 1, "boundary_f_score": 1},
        "stages": {"export": {"median": 0.1, "p95": 0.2}},
        "dataset": {"sha256": "a" * 64},
        "settings": {"threshold": 0.5},
        "sample_count": 2,
        "runtime_options": {"requested_threads": 2},
    }
    candidate = copy.deepcopy(report)
    candidate[field] = None
    gate = compare_reports(report, candidate)
    assert not gate["passed"]
    assert field in gate["failures"][0]


@pytest.mark.parametrize(
    "field, changed",
    [("width", 4), ("height", 4), ("pixels", 16), ("provider", "CUDAExecutionProvider")],
)
def test_gate_rejects_changed_benchmark_conditions(field, changed):
    report = {
        "metrics": {"iou": 1, "boundary_f_score": 1},
        "sizes": {
            "1mp": {
                "width": 2,
                "height": 2,
                "pixels": 4,
                "provider": "CPUExecutionProvider",
                "stages": {"export": {"median": 0.1, "p95": 0.2}},
            }
        },
    }
    candidate = copy.deepcopy(report)
    candidate["sizes"]["1mp"][field] = changed
    gate = compare_reports(report, candidate)
    assert not gate["passed"]
    assert field in gate["failures"][0]
