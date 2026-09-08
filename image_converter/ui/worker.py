"""
Background QThread worker for responsive batch conversions.
"""

import time
from pathlib import Path
from typing import List, Tuple

from PySide6.QtCore import QThread, Signal

from image_converter.core.engine import (
    ConversionConfig,
    ConversionResult,
    ImageConverterEngine,
)


class BatchConversionWorker(QThread):
    """Worker thread running batch conversions in background."""

    # Signals
    file_started = Signal(int, str)  # (index, filename)
    file_completed = Signal(int, object)  # (index, ConversionResult)
    progress_updated = Signal(int, int, int)  # (current, total, percentage)
    batch_finished = Signal(int, int, float, int, int)  # (success, failed, elapsed_sec, bytes_in, bytes_out)
    batch_cancelled = Signal()

    def __init__(
        self,
        tasks: List[Tuple[str | Path, str | Path, ConversionConfig]],
        engine: ImageConverterEngine,
        parent=None,
    ):
        super().__init__(parent)
        self.tasks = tasks
        self.engine = engine
        self._is_cancelled = False

    def cancel(self):
        """Request worker to abort remaining conversions."""
        self._is_cancelled = True

    def is_cancelled(self) -> bool:
        return self._is_cancelled

    def run(self):
        total = len(self.tasks)
        success_count = 0
        fail_count = 0
        total_in_bytes = 0
        total_out_bytes = 0
        t_start = time.perf_counter()

        for idx, (in_p, out_p, config) in enumerate(self.tasks):
            if self._is_cancelled:
                break

            in_path_obj = Path(in_p)
            self.file_started.emit(idx, in_path_obj.name)

            res = self.engine.convert_single(in_p, out_p, config)

            if res.success:
                success_count += 1
                total_in_bytes += res.input_size_bytes
                total_out_bytes += res.output_size_bytes
            else:
                fail_count += 1

            pct = int(((idx + 1) / total) * 100) if total > 0 else 100
            self.file_completed.emit(idx, res)
            self.progress_updated.emit(idx + 1, total, pct)

        t_elapsed = time.perf_counter() - t_start
        if self._is_cancelled:
            self.batch_cancelled.emit()
            return

        self.batch_finished.emit(
            success_count,
            fail_count,
            t_elapsed,
            total_in_bytes,
            total_out_bytes,
        )
