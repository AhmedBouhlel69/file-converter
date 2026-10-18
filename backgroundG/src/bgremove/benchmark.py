"""Reproducible local pipeline timings; no model or dataset is downloaded."""

import math
import os
import platform
import tempfile
import threading
from collections.abc import Iterable
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol

import numpy as np
import onnxruntime as ort
from PIL import Image

from .config import MAX_PIXELS
from .loader import load
from .remover import Result


class _Remover(Protocol):
    def remove(self, source: str | Path | bytes | Image.Image) -> Result: ...


class _PeakRSS:
    """Sample absolute process RSS, including native ONNX/OpenCV allocations."""

    def __init__(self) -> None:
        self.peak: int | None = None
        self.error: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._process: Any = None
        self._errors: tuple[type[Exception], ...] = (OSError,)

    def start(self) -> None:
        try:
            import psutil
        except ImportError as exc:
            self.error = f"RSS sampling unavailable: {exc}"
            return
        try:
            self._errors = (OSError, psutil.Error)
            self._process = psutil.Process()
            self.peak = int(self._process.memory_info().rss)
        except self._errors as exc:
            self.error = f"RSS sampling unavailable: {exc}"
            return
        self._thread = threading.Thread(target=self._sample, daemon=True)
        self._thread.start()

    def _sample(self) -> None:
        while not self._stop.is_set():
            try:
                value = int(self._process.memory_info().rss)
                self.peak = max(self.peak or 0, value)
            except self._errors as exc:
                self.error = f"RSS sampling interrupted: {exc}"
                return
            self._stop.wait(0.005)

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        return {
            "process_peak_rss_bytes": self.peak,
            "rss_sampling_interval_ms": 5,
            "rss_note": self.error or "Sampled absolute process RSS; short peaks may be missed",
            "peak_vram_bytes": None,
            "vram_note": "Unavailable: no portable per-process GPU memory sampler configured",
        }


def _dimensions(megapixels: float, aspect: float) -> tuple[int, int]:
    pixels = megapixels * 1_000_000
    width = max(1, round(math.sqrt(pixels * aspect)))
    height = max(1, round(pixels / width))
    if width * height > MAX_PIXELS:
        raise ValueError(f"Benchmark dimensions exceed the {MAX_PIXELS}-pixel input cap")
    return width, height


def _synthetic(size: tuple[int, int]) -> Image.Image:
    width, height = size
    horizontal = np.arange(width, dtype=np.uint16)[None, :]
    vertical = np.arange(height, dtype=np.uint16)[:, None]
    rgb = np.empty((height, width, 3), dtype=np.uint8)
    rgb[:, :, 0] = horizontal % 256
    rgb[:, :, 1] = vertical % 256
    rgb[:, :, 2] = (horizontal + vertical) % 256
    return Image.fromarray(rgb)


def _summary(samples: list[dict[str, float]]) -> dict[str, dict[str, float]]:
    stages = samples[0].keys()
    if any(row.keys() != stages for row in samples):
        raise ValueError("Pipeline stages changed during the benchmark")
    summary: dict[str, dict[str, float]] = {}
    for stage in stages:
        values = np.array([row[stage] for row in samples], dtype=np.float64)
        if not np.isfinite(values).all() or np.any(values < 0):
            raise ValueError(f"Invalid benchmark duration for {stage}")
        summary[stage] = {
            "median": float(np.median(values)),
            "p95": float(np.percentile(values, 95)),
        }
    return summary


def run_benchmark(
    remover: _Remover,
    image: str | Path | bytes | Image.Image | None = None,
    *,
    warmups: int = 3,
    runs: int = 20,
    megapixels: Iterable[float] = (1, 12, 24),
    profile: str | None = None,
) -> dict[str, Any]:
    """Time resized inputs, including disk load/export, for each requested MP size.

    Input preparation is excluded. Each prepared image is saved as JPEG quality 95
    and processed from disk; the timed output is always a PNG. Warmup runs include
    export and are excluded from timing statistics. A model must already be installed.
    """
    if isinstance(runs, bool) or not isinstance(runs, int) or runs < 1:
        raise ValueError("runs must be a positive integer")
    if isinstance(warmups, bool) or not isinstance(warmups, int) or warmups < 0:
        raise ValueError("warmups must be a nonnegative integer")
    sizes = list(megapixels)
    if not sizes:
        raise ValueError("At least one megapixel size is required")
    for size in sizes:
        if isinstance(size, bool) or not math.isfinite(size) or size <= 0:
            raise ValueError("Megapixel sizes must be finite and positive")
        if size * 1_000_000 > MAX_PIXELS:
            raise ValueError("Megapixel size exceeds the input pixel cap")
    labels = [f"{size:g}mp" for size in sizes]
    if len(set(labels)) != len(labels):
        raise ValueError("Megapixel sizes must be unique")
    original = Image.fromarray(load(image).rgb) if image is not None else None
    aspect = original.width / original.height if original else 4 / 3
    reports: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="bgremove-benchmark-") as temporary:
        directory = Path(temporary)
        input_path, output_path = directory / "input.jpg", directory / "output.png"
        for size, label in zip(sizes, labels, strict=True):
            dimensions = _dimensions(float(size), aspect)
            prepared = (
                original.resize(dimensions, Image.Resampling.LANCZOS)
                if original
                else _synthetic(dimensions)
            )
            prepared.save(input_path, format="JPEG", quality=95)
            prepared.close()
            samples: list[dict[str, float]] = []
            providers: set[str] = set()
            memory = _PeakRSS()
            memory.start()
            try:
                for index in range(warmups + runs):
                    started = perf_counter()
                    result = remover.remove(input_path)
                    result.save(output_path, overwrite=True)
                    elapsed = perf_counter() - started
                    if index >= warmups:
                        timings = dict(result.timings)
                        if "export" not in timings:
                            raise ValueError("Result.save() did not report export timing")
                        timings["total"] = elapsed
                        samples.append(timings)
                        providers.add(result.provider)
                    del result
            finally:
                memory_report = memory.stop()
            if len(providers) != 1:
                raise ValueError("Execution provider changed during the benchmark")
            reports[label] = {
                "width": dimensions[0],
                "height": dimensions[1],
                "pixels": dimensions[0] * dimensions[1],
                "provider": next(iter(providers)),
                "stages": _summary(samples),
                "memory": memory_report,
            }
    if original is not None:
        original.close()
    return {
        "schema_version": 1,
        "profile": profile or "unspecified",
        "warmups": warmups,
        "runs": runs,
        "timing_unit": "seconds",
        "input": "resized_source" if image is not None else "synthetic_rgb_gradient",
        "input_encoding": "JPEG quality 95; preparation excluded from timings",
        "runtime_options": {
            "requested_device": getattr(remover, "device", None),
            "requested_threads": getattr(remover, "threads", None),
            "strict_device": getattr(remover, "strict", None),
        },
        "environment": {
            "os": platform.platform(),
            "cpu": platform.processor(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "onnxruntime": ort.__version__,
            "available_providers": ort.get_available_providers(),
            "logical_cpu_count": os.cpu_count(),
        },
        "sizes": reports,
    }
