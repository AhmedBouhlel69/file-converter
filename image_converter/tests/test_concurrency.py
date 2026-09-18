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
