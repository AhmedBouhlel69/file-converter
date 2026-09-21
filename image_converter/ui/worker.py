"""
Background QThread worker for responsive batch conversions.
"""

import time
import logging
from pathlib import Path
from typing import List, Tuple

from PySide6.QtCore import QThread, Signal

from image_converter.core.engine import (
    ConversionConfig,
    ConversionResult,
    ImageConverterEngine,
)

logger = logging.getLogger(__name__)


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
        if total == 0:
            self.batch_finished.emit(0, 0, 0.0, 0, 0)
            return

        success_count = 0
        fail_count = 0
        total_in_bytes = 0
        total_out_bytes = 0
        t_start = time.perf_counter()

        def on_task_progress(completed_count: int, total_count: int, res: ConversionResult):
            nonlocal success_count, fail_count, total_in_bytes, total_out_bytes
            if res.success:
                success_count += 1
                total_in_bytes += res.input_size_bytes
                total_out_bytes += res.output_size_bytes
            else:
                fail_count += 1

            # Map to task row index
            task_idx = 0
            for i, (inp, _, _) in enumerate(self.tasks):
                if str(Path(inp).resolve()) == str(Path(res.input_path).resolve()):
                    task_idx = i
                    break

            pct = int((completed_count / total_count) * 100) if total_count > 0 else 100
            self.file_completed.emit(task_idx, res)
            self.progress_updated.emit(completed_count, total_count, pct)

        try:
            self.engine.convert_batch(
                self.tasks,
                progress_callback=on_task_progress,
                cancel_check=lambda: self._is_cancelled,
            )
        except Exception as batch_err:
            logger.error(f"Catastrophic batch conversion error in UI worker: {batch_err}", exc_info=True)
            # Handle catastrophic failure gracefully
            fail_count += (total - success_count - fail_count)
            err_res = ConversionResult(
                success=False,
                input_path=str(self.tasks[0][0]) if self.tasks else "",
                error_message=f"Batch conversion error: {str(batch_err)}",
            )
            self.file_completed.emit(0, err_res)

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
