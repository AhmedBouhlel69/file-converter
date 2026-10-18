"""Offline mask evaluation and strict quality/performance release comparisons."""

import hashlib
import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from numpy.typing import ArrayLike, NDArray
from PIL import Image, ImageOps


def _alpha(value: ArrayLike) -> NDArray[np.float64]:
    array = np.asarray(value, dtype=np.float64)
    if array.ndim != 2 or not array.size:
        raise ValueError("Masks must be nonempty two-dimensional arrays")
    if not np.isfinite(array).all() or np.any((array < 0) | (array > 1)):
        raise ValueError("Mask alpha must be finite and between 0 and 1")
    return array


def read_mask(path: str | Path) -> NDArray[np.float64]:
    """Read soft alpha from RGBA/LA, otherwise grayscale; preserve 16-bit precision."""
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source)
        if "A" in image.getbands():
            values = np.asarray(image.getchannel("A"), dtype=np.float64) / 255.0
        elif image.mode.startswith("I;16") or image.mode == "I":
            values = np.asarray(image, dtype=np.float64) / 65535.0
        elif image.mode == "F":
            values = np.asarray(image, dtype=np.float64)
        else:
            values = np.asarray(image.convert("L"), dtype=np.float64) / 255.0
    return _alpha(values)


def _boundary(mask: NDArray[np.bool_]) -> NDArray[np.uint8]:
    binary = mask.astype(np.uint8)
    eroded = cv2.erode(
        binary, np.ones((3, 3), dtype=np.uint8), borderType=cv2.BORDER_CONSTANT, borderValue=0
    )
    return np.asarray(binary - eroded, dtype=np.uint8)


def _boundary_score(
    prediction: NDArray[np.bool_], truth: NDArray[np.bool_], tolerance: int
) -> float:
    predicted_boundary, true_boundary = _boundary(prediction), _boundary(truth)
    predicted_count, true_count = int(predicted_boundary.sum()), int(true_boundary.sum())
    if not predicted_count or not true_count:
        return float(predicted_count == true_count)
    coordinates = np.arange(-tolerance, tolerance + 1)
    disk = (coordinates[:, None] ** 2 + coordinates[None, :] ** 2 <= tolerance**2).astype(np.uint8)
    near_true = np.asarray(cv2.dilate(true_boundary, disk), dtype=np.uint8)
    near_predicted = np.asarray(cv2.dilate(predicted_boundary, disk), dtype=np.uint8)
    precision = float(np.count_nonzero(predicted_boundary & near_true)) / predicted_count
    recall = float(np.count_nonzero(true_boundary & near_predicted)) / true_count
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def _gradient(alpha: NDArray[np.float64], sigma: float = 1.4) -> NDArray[np.float64]:
    radius = math.ceil(3 * sigma)
    coordinates = np.arange(-radius, radius + 1, dtype=np.float64)
    gaussian = np.exp(-(coordinates**2) / (2 * sigma**2))
    gaussian /= gaussian.sum()
    derivative = -coordinates * gaussian / sigma**2
    horizontal = cv2.sepFilter2D(alpha, cv2.CV_64F, derivative, gaussian)
    vertical = cv2.sepFilter2D(alpha, cv2.CV_64F, gaussian, derivative)
    return np.hypot(horizontal, vertical)


def compute_metrics(
    prediction: ArrayLike,
    ground_truth: ArrayLike,
    *,
    threshold: float = 0.5,
    boundary_tolerance: int = 2,
    matting: bool = False,
) -> dict[str, float]:
    """Compute macro-compatible mask metrics; IoU/F1 define two empty masks as perfect."""
    if not math.isfinite(threshold) or not 0 < threshold < 1:
        raise ValueError("threshold must be finite and strictly between 0 and 1")
    if isinstance(boundary_tolerance, bool) or not isinstance(boundary_tolerance, int):
        raise TypeError("boundary_tolerance must be a nonnegative integer")
    if boundary_tolerance < 0:
        raise ValueError("boundary_tolerance must be a nonnegative integer")
    predicted, truth = _alpha(prediction), _alpha(ground_truth)
    if predicted.shape != truth.shape:
        raise ValueError("Prediction and ground-truth mask dimensions differ")
    binary_prediction, binary_truth = predicted >= threshold, truth >= threshold
    intersection = int(np.count_nonzero(binary_prediction & binary_truth))
    union = int(np.count_nonzero(binary_prediction | binary_truth))
    foreground_count = int(binary_prediction.sum()) + int(binary_truth.sum())
    absolute_error = np.abs(predicted - truth)
    metrics = {
        "iou": intersection / union if union else 1.0,
        "mae": float(absolute_error.mean()),
        "f_measure": 2 * intersection / foreground_count if foreground_count else 1.0,
        "boundary_f_score": _boundary_score(binary_prediction, binary_truth, boundary_tolerance),
    }
    if matting:
        metrics.update(
            sad=float(absolute_error.sum() / 1000),
            mse=float(np.square(predicted - truth).mean()),
            gradient=float(np.square(_gradient(predicted) - _gradient(truth)).sum() / 1000),
        )
    return metrics


def _read_object(source: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(source, Mapping):
        return dict(source)
    value: Any = json.loads(Path(source).read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise TypeError("Expected a JSON object")
    return value


def _file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def evaluate_manifest(
    manifest: str | Path,
    *,
    threshold: float = 0.5,
    boundary_tolerance: int = 2,
    matting: bool = False,
) -> dict[str, Any]:
    """Evaluate explicit prediction/ground_truth pairs relative to the manifest file."""
    path = Path(manifest)
    data = _read_object(path)
    samples = data.get("samples")
    if not isinstance(samples, list) or not samples:
        raise ValueError("Evaluation manifest requires a nonempty samples list")
    results: list[dict[str, Any]] = []
    identities: list[str] = []
    for index, sample in enumerate(samples):
        if not isinstance(sample, dict):
            raise TypeError(f"Sample {index} must be an object")
        for key in ("prediction", "ground_truth"):
            if not isinstance(sample.get(key), str) or not sample[key]:
                raise ValueError(f"Sample {index} requires a {key} mask path")
        predicted = read_mask(path.parent / sample["prediction"])
        truth = read_mask(path.parent / sample["ground_truth"])
        identity = {
            "id": sample.get("id"),
            "ground_truth_sha256": _file_hash(path.parent / sample["ground_truth"]),
        }
        if "image" in sample:
            if not isinstance(sample["image"], str) or not sample["image"]:
                raise ValueError(f"Sample {index} image must be a path")
            with Image.open(path.parent / sample["image"]) as image:
                width, height = ImageOps.exif_transpose(image).size
            if truth.shape != (height, width):
                raise ValueError(f"Sample {index} image and mask dimensions differ")
            identity["image_sha256"] = _file_hash(path.parent / sample["image"])
        identities.append(json.dumps(identity, sort_keys=True, separators=(",", ":")))
        metrics = compute_metrics(
            predicted,
            truth,
            threshold=threshold,
            boundary_tolerance=boundary_tolerance,
            matting=matting,
        )
        results.append({"sample": sample.get("id", index), "metrics": metrics})
    return {
        "schema_version": 1,
        "profile": data.get("profile", "unspecified"),
        "sample_count": len(results),
        "dataset": {
            "sha256": hashlib.sha256("\n".join(sorted(identities)).encode()).hexdigest(),
            "identity": "ground-truth files, optional source images and sample IDs",
        },
        "metrics": {
            key: float(np.mean([row["metrics"][key] for row in results]))
            for key in results[0]["metrics"]
        },
        "settings": {
            "threshold": threshold,
            "boundary_tolerance_pixels": boundary_tolerance,
            "f_measure_beta": 1,
            "aggregation": "mean_per_image",
            "gradient_method": "gaussian_derivative_sigma_1.4" if matting else None,
        },
        "unavailable_metrics": ["connectivity"] if matting else [],
        "results": results,
    }


def _number(value: Any, label: str, *, positive: bool = False, score: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be numeric")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError(f"{label} must be finite") from exc
    if not math.isfinite(number) or number < 0 or (positive and number == 0):
        raise ValueError(f"{label} must be finite and {'positive' if positive else 'nonnegative'}")
    if score and number > 1:
        raise ValueError(f"{label} must be between 0 and 1")
    return number


def _stage_sets(report: dict[str, Any], label: str) -> dict[str, Any]:
    if "sizes" in report:
        sizes = report["sizes"]
        if not isinstance(sizes, dict) or not sizes:
            raise ValueError(f"{label}.sizes must be a nonempty object")
        sets: dict[str, Any] = {}
        for name, item in sizes.items():
            if not isinstance(item, dict):
                raise TypeError(f"{label}.sizes.{name} must be an object")
            sets[name] = item.get("stages")
    else:
        sets = {"default": report.get("stages")}
    for name, stages in sets.items():
        if not isinstance(stages, dict) or not stages:
            raise ValueError(f"{label}.{name}.stages must be a nonempty object")
        if "export" not in stages:
            raise ValueError(f"{label}.{name}.stages requires export timing")
        for stage, timing in stages.items():
            if not isinstance(timing, dict):
                raise TypeError(f"{label}.{name}.{stage} timing must be an object")
            _number(timing.get("p95"), f"{label}.{name}.{stage}.p95", positive=True)
            _number(timing.get("median"), f"{label}.{name}.{stage}.median")
    return sets


def _compare_profile(
    baseline: dict[str, Any], candidate: dict[str, Any], label: str, failures: list[str]
) -> None:
    for key in ("profile", "dataset", "settings", "sample_count", "provider", "runtime_options"):
        if baseline.get(key) != candidate.get(key):
            raise ValueError(f"{label} baseline and candidate {key} differ")
    before_environment, after_environment = (
        baseline.get("environment"),
        candidate.get("environment"),
    )
    if before_environment is not None or after_environment is not None:
        if not isinstance(before_environment, dict) or not isinstance(after_environment, dict):
            raise TypeError(f"{label} both reports require environment objects")
        for key in ("cpu", "machine", "logical_cpu_count"):
            if before_environment.get(key) != after_environment.get(key):
                raise ValueError(f"{label} baseline and candidate environment.{key} differ")
    for report, side in ((baseline, "baseline"), (candidate, "candidate")):
        metrics = report.get("metrics")
        if not isinstance(metrics, dict):
            raise TypeError(f"{label}.{side}.metrics must be an object")
        for metric in ("iou", "boundary_f_score"):
            _number(metrics.get(metric), f"{label}.{side}.{metric}", score=True)
        for metric, value in metrics.items():
            _number(
                value,
                f"{label}.{side}.{metric}",
                score=metric in {"iou", "mae", "f_measure", "boundary_f_score", "mse"},
            )
    for metric in ("iou", "boundary_f_score"):
        previous = float(baseline["metrics"][metric])
        current = float(candidate["metrics"][metric])
        if previous - current > 0.01 + 1e-12:
            failures.append(f"{label}.{metric} dropped by {previous - current:.6f} (> 0.01)")
    baseline_stages = _stage_sets(baseline, f"{label}.baseline")
    candidate_stages = _stage_sets(candidate, f"{label}.candidate")
    if baseline_stages.keys() != candidate_stages.keys():
        raise ValueError(f"{label} baseline and candidate timing size sets differ")
    if baseline.get("timing_unit", "seconds") != candidate.get("timing_unit", "seconds"):
        raise ValueError(f"{label} baseline and candidate timing units differ")
    for size, stages in baseline_stages.items():
        current_stages = candidate_stages[size]
        before_size = baseline.get("sizes", {}).get(size, {})
        after_size = candidate.get("sizes", {}).get(size, {})
        for key in ("width", "height", "pixels", "provider"):
            if before_size.get(key) != after_size.get(key):
                raise ValueError(f"{label}.{size} baseline and candidate {key} differ")
        if stages.keys() != current_stages.keys():
            raise ValueError(f"{label}.{size} baseline and candidate stage sets differ")
        for stage, timing in stages.items():
            previous_p95, current_p95 = float(timing["p95"]), float(current_stages[stage]["p95"])
            regression = current_p95 / previous_p95 - 1
            if regression > 0.15 + 1e-12:
                failures.append(
                    f"{label}.{size}.{stage}.p95 regressed by {regression * 100:.2f}% (> 15%)"
                )


def compare_reports(
    baseline: str | Path | Mapping[str, Any], candidate: str | Path | Mapping[str, Any]
) -> dict[str, Any]:
    """Fail closed on absent quality/timing data, invalid numbers or changed coverage."""
    failures: list[str] = []
    try:
        previous, current = _read_object(baseline), _read_object(candidate)
        if "profiles" in previous or "profiles" in current:
            before, after = previous.get("profiles"), current.get("profiles")
            if not isinstance(before, dict) or not isinstance(after, dict) or not before:
                raise ValueError("Both reports require nonempty profiles objects")
            if before.keys() != after.keys():
                raise ValueError("Baseline and candidate profile sets differ")
            for name in before:
                if not isinstance(before[name], dict) or not isinstance(after[name], dict):
                    raise TypeError(f"Profile {name} must contain report objects")
                _compare_profile(before[name], after[name], str(name), failures)
        else:
            if previous.get("profile") != current.get("profile"):
                raise ValueError("Baseline and candidate model profiles differ")
            _compare_profile(previous, current, "report", failures)
    except (ValueError, OSError, TypeError) as exc:
        failures.append(f"Invalid comparison: {exc}")
    return {
        "passed": not failures,
        "failures": failures,
        "limits": {"quality_absolute_drop": 0.01, "p95_relative_regression": 0.15},
    }
