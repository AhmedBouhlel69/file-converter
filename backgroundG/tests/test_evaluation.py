import copy
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

from bgremove.benchmark import run_benchmark
from bgremove.evaluation import compare_reports, compute_metrics, evaluate_manifest, read_mask
from bgremove.remover import Result


def test_metrics_known_values():
    predicted = np.array([[1, 0.25], [1, 0]])
    truth = np.array([[1, 0], [0, 1]])
    metrics = compute_metrics(predicted, truth, matting=True, boundary_tolerance=0)
    assert metrics["iou"] == pytest.approx(1 / 3)
    assert metrics["f_measure"] == pytest.approx(0.5)
    assert metrics["mae"] == pytest.approx(2.25 / 4)
    assert metrics["sad"] == pytest.approx(2.25 / 1000)
    assert metrics["mse"] == pytest.approx(2.0625 / 4)
    assert math.isfinite(metrics["gradient"])


@pytest.mark.parametrize("value", [0, 1])
def test_perfect_and_empty_masks(value):
    alpha = np.full((7, 9), value, dtype=float)
    metrics = compute_metrics(alpha, alpha, matting=True)
    assert metrics == {
        "iou": 1,
        "mae": 0,
        "f_measure": 1,
        "boundary_f_score": 1,
        "sad": 0,
        "mse": 0,
        "gradient": 0,
    }
    opposite = compute_metrics(alpha, 1 - alpha)
    assert opposite["iou"] == opposite["f_measure"] == opposite["boundary_f_score"] == 0


def test_boundary_tolerance_is_euclidean_pixels():
    truth = np.zeros((12, 12))
    predicted = truth.copy()
    truth[3:8, 3:8], predicted[3:8, 4:9] = 1, 1
    assert compute_metrics(predicted, truth, boundary_tolerance=0)["boundary_f_score"] < 1
    assert compute_metrics(predicted, truth, boundary_tolerance=1)["boundary_f_score"] == 1


@pytest.mark.parametrize("bad", [np.array([]), np.zeros((2, 2, 1)), [[-1]], [[2]], [[np.nan]]])
def test_invalid_alpha_rejected(bad):
    with pytest.raises(ValueError):
        compute_metrics(bad, bad)


def test_metric_settings_and_shape_validation():
    with pytest.raises(ValueError, match="dimensions"):
        compute_metrics(np.zeros((1, 2)), np.zeros((2, 1)))
    for threshold in (0, 1, np.nan):
        with pytest.raises(ValueError, match="threshold"):
            compute_metrics([[0]], [[0]], threshold=threshold)
    with pytest.raises(ValueError, match="tolerance"):
        compute_metrics([[0]], [[0]], boundary_tolerance=-1)
    with pytest.raises(TypeError, match="tolerance"):
        compute_metrics([[0]], [[0]], boundary_tolerance=True)


def test_mask_alpha_and_16bit_precision(tmp_path):
    rgba = Image.new("RGBA", (2, 1), (255, 0, 0, 64))
    rgba.save(tmp_path / "rgba.png")
    assert np.allclose(read_mask(tmp_path / "rgba.png"), 64 / 255)
    Image.fromarray(np.array([[0, 32768, 65535]], dtype=np.uint16)).save(tmp_path / "16.png")
    assert np.allclose(read_mask(tmp_path / "16.png"), [[0, 32768 / 65535, 1]])


def test_manifest_relative_paths_and_macro_average(tmp_path):
    first = np.zeros((4, 4), dtype=np.uint8)
    first[1:3, 1:3] = 255
    Image.fromarray(first).save(tmp_path / "truth.png")
    Image.new("L", (4, 4), 0).save(tmp_path / "empty.png")
    Image.new("RGB", (4, 4), "red").save(tmp_path / "photo.png")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "profile": "balanced",
                "samples": [
                    {
                        "id": "perfect",
                        "image": "photo.png",
                        "prediction": "truth.png",
                        "ground_truth": "truth.png",
                    },
                    {"prediction": "empty.png", "ground_truth": "truth.png"},
                ],
            }
        )
    )
    report = evaluate_manifest(manifest, matting=True)
    assert report["profile"] == "balanced"
    assert report["sample_count"] == 2
    assert report["metrics"]["iou"] == 0.5
    assert report["metrics"]["mae"] == 0.125
    assert report["results"][0]["sample"] == "perfect"
    assert report["unavailable_metrics"] == ["connectivity"]
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize("samples", [[], [{}], ["bad"], None])
def test_invalid_manifest_schema(tmp_path, samples):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"samples": samples}))
    with pytest.raises((ValueError, TypeError)):
        evaluate_manifest(manifest)


def test_manifest_image_dimensions_checked(tmp_path):
    Image.new("L", (2, 3)).save(tmp_path / "mask.png")
    Image.new("RGB", (3, 2)).save(tmp_path / "image.png")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "samples": [
                    {"image": "image.png", "prediction": "mask.png", "ground_truth": "mask.png"}
                ]
            }
        )
    )
    with pytest.raises(ValueError, match="image and mask dimensions"):
        evaluate_manifest(manifest)


def _report() -> dict[str, Any]:
    return {
        "profile": "balanced",
        "timing_unit": "seconds",
        "metrics": {"iou": 0.96, "boundary_f_score": 0.95, "mae": 0.02},
        "stages": {
            "inference": {"median": 0.08, "p95": 0.1},
            "export": {"median": 0.04, "p95": 0.05},
        },
    }


def test_gate_exact_limits_pass_and_no_mutation():
    baseline, candidate = _report(), _report()
    candidate["metrics"]["iou"] -= 0.01
    candidate["metrics"]["boundary_f_score"] -= 0.01
    candidate["stages"]["inference"]["p95"] *= 1.15
    candidate["stages"]["export"]["p95"] *= 1.15
    original = copy.deepcopy(candidate)
    assert compare_reports(baseline, candidate)["passed"]
    assert candidate == original


def test_gate_blocks_quality_and_each_stage_regressions():
    baseline, candidate = _report(), _report()
    candidate["metrics"]["iou"] -= 0.0101
    candidate["metrics"]["boundary_f_score"] -= 0.0101
    candidate["stages"]["inference"]["p95"] *= 1.151
    candidate["stages"]["export"]["p95"] *= 1.151
    gate = compare_reports(baseline, candidate)
    assert not gate["passed"]
    assert len(gate["failures"]) == 4


def test_gate_tiny_positive_baseline_keeps_relative_limit():
    baseline, candidate = _report(), _report()
    baseline["stages"]["inference"]["p95"] = 1e-13
    candidate["stages"]["inference"]["p95"] = 2e-13
    assert not compare_reports(baseline, candidate)["passed"]


@pytest.mark.parametrize("invalid", [None, True, "0.95", float("nan"), float("inf"), -1, 1.1])
def test_gate_invalid_quality_fails_closed(invalid):
    candidate = _report()
    candidate["metrics"]["iou"] = invalid
    gate = compare_reports(_report(), candidate)
    assert not gate["passed"]
    assert "Invalid comparison" in gate["failures"][0]


@pytest.mark.parametrize("invalid", [None, True, "1", float("nan"), float("inf"), -1, 0])
def test_gate_invalid_p95_baseline_fails_closed(invalid):
    baseline = _report()
    baseline["stages"]["inference"]["p95"] = invalid
    gate = compare_reports(baseline, _report())
    assert not gate["passed"]
    assert "baseline.default.inference.p95" in gate["failures"][0]


@pytest.mark.parametrize("missing", ["metrics", "stages"])
def test_gate_missing_sections_fail(missing):
    candidate = _report()
    del candidate[missing]
    assert not compare_reports(_report(), candidate)["passed"]


def test_gate_stage_coverage_export_profile_and_units_fail():
    baseline, candidate = _report(), _report()
    del candidate["stages"]["inference"]
    assert not compare_reports(baseline, candidate)["passed"]
    candidate = _report()
    del candidate["stages"]["export"]
    assert "export" in compare_reports(baseline, candidate)["failures"][0]
    candidate = _report()
    candidate["profile"] = "fast"
    assert not compare_reports(baseline, candidate)["passed"]
    candidate = _report()
    candidate["timing_unit"] = "milliseconds"
    assert not compare_reports(baseline, candidate)["passed"]


def test_gate_accepts_benchmark_sizes_and_per_profile_reports(tmp_path):
    report = _report()
    report["sizes"] = {"1mp": {"stages": report.pop("stages")}}
    baseline = {"profiles": {"balanced": report, "fast": copy.deepcopy(report)}}
    candidate = copy.deepcopy(baseline)
    candidate["profiles"]["fast"]["sizes"]["1mp"]["stages"]["export"]["p95"] *= 1.2
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(baseline))
    gate = compare_reports(path, candidate)
    assert not gate["passed"]
    assert "fast.1mp.export" in gate["failures"][0]
    del candidate["profiles"]["fast"]
    assert "profile sets differ" in compare_reports(baseline, candidate)["failures"][0]


def test_gate_invalid_json_returns_failure(tmp_path):
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not JSON")
    assert not compare_reports(invalid, _report())["passed"]


class _FakeRemover:
    def __init__(self) -> None:
        self.calls = 0

    def remove(self, source: str | Path | bytes | Image.Image) -> Result:
        assert isinstance(source, Path)
        self.calls += 1
        with Image.open(source) as image:
            rgba = image.convert("RGBA")
        mask = np.ones((rgba.height, rgba.width), dtype=np.float32)
        return Result(
            rgba, mask, {"inference": self.calls * 0.001}, None, None, "SyntheticExecutionProvider"
        )


def test_benchmark_defaults_warmups_and_statistics(monkeypatch):
    # Deterministic fake timings verify warmup exclusion without running an ONNX model.
    remover = _FakeRemover()
    monkeypatch.setitem(sys.modules, "psutil", None)
    report = run_benchmark(remover, megapixels=[0.0001], profile="test")
    assert remover.calls == 23
    assert report["warmups"] == 3 and report["runs"] == 20
    result = report["sizes"]["0.0001mp"]
    assert result["provider"] == "SyntheticExecutionProvider"
    assert result["stages"]["inference"]["median"] == pytest.approx(0.0135)
    assert result["stages"]["inference"]["p95"] == pytest.approx(0.02205)
    assert result["stages"]["export"]["p95"] > 0
    assert result["stages"]["total"]["p95"] > 0
    assert result["memory"]["process_peak_rss_bytes"] is None
    assert "unavailable" in result["memory"]["rss_note"]
    assert result["memory"]["peak_vram_bytes"] is None
    assert "onnxruntime" in report["environment"]
    json.dumps(report, allow_nan=False)


def test_benchmark_multiple_sizes_preserve_source_aspect():
    remover = _FakeRemover()
    report = run_benchmark(
        remover, Image.new("RGB", (20, 10)), runs=2, warmups=1, megapixels=[0.0002, 0.0008]
    )
    assert remover.calls == 6
    assert report["input"] == "resized_source"
    assert len(report["sizes"]) == 2
    for result in report["sizes"].values():
        assert result["width"] == result["height"] * 2


@pytest.mark.parametrize(
    "kwargs",
    [
        {"runs": 0},
        {"warmups": -1},
        {"runs": True},
        {"megapixels": []},
        {"megapixels": [0]},
        {"megapixels": [float("nan")]},
        {"megapixels": [1, 1]},
        {"megapixels": [121]},
    ],
)
def test_benchmark_invalid_settings_fail_before_processing(kwargs):
    remover = _FakeRemover()
    with pytest.raises(ValueError):
        run_benchmark(remover, **kwargs)
    assert remover.calls == 0
