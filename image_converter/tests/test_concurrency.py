"""
Unit tests for batch concurrency, multithreading, and mid-batch cancellation.
"""

from pathlib import Path
from PIL import Image
import pytest
import time

from image_converter.core.engine import (
    ConversionConfig,
    ConversionResult,
    ImageConverterEngine,
)


@pytest.fixture
def engine():
    return ImageConverterEngine()


def test_concurrent_batch_conversion(engine, tmp_path: Path):
    tasks = []
    for i in range(8):
        src = tmp_path / f"img_{i}.png"
        Image.new("RGB", (30, 30), color="blue").save(src)
        dst = tmp_path / f"out_{i}.jpg"
        tasks.append((src, dst, ConversionConfig(target_format="JPG")))

    progress_events = []

    def on_progress(completed: int, total: int, res: ConversionResult):
        progress_events.append((completed, total, res.success))

    results = engine.convert_batch(tasks, progress_callback=on_progress, max_workers=4)

    assert len(results) == 8
    assert all(r.success for r in results)
    assert len(progress_events) == 8
    # Last event should be completed == total
    assert progress_events[-1][0] == 8
    assert progress_events[-1][1] == 8


def test_batch_cancellation_mid_run(engine, tmp_path: Path):
    tasks = []
    for i in range(12):
        src = tmp_path / f"cancel_img_{i}.png"
        Image.new("RGB", (40, 40), color="green").save(src)
        dst = tmp_path / f"cancel_out_{i}.jpg"
        tasks.append((src, dst, ConversionConfig(target_format="JPG")))

    call_count = 0
    cancelled = False

    def cancel_trigger():
        return cancelled

    def on_progress(completed: int, total: int, res: ConversionResult):
        nonlocal call_count, cancelled
        call_count += 1
        if call_count >= 2:
            cancelled = True

    # Use single worker to deterministically test cancellation after 2 items
    results = engine.convert_batch(
        tasks,
        progress_callback=on_progress,
        cancel_check=cancel_trigger,
        max_workers=1,
    )

    # Should have stopped early, not completing all 12
    assert len(results) < 12
    assert call_count >= 2


def test_default_batch_limits_simultaneous_decoded_images(engine, tmp_path, monkeypatch):
    import threading
    from image_converter.core.conversion import engine as implementation

    monkeypatch.setattr(implementation.os, "cpu_count", lambda: 12)
    lock = threading.Lock()
    active = peak = 0

    def convert(source, output, config):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            time.sleep(0.03)
            return ConversionResult(True, str(source), str(output))
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(engine, "convert_single", convert)
    tasks = [(tmp_path / f"{index}.png", tmp_path / f"{index}.jpg",
              ConversionConfig(target_format="JPG")) for index in range(8)]
    results = engine.convert_batch(tasks)
    assert len(results) == 8 and all(result.success for result in results)
    assert peak == 2
