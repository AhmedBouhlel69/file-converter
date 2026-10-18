"""Qt worker for serial background removal without blocking the interface."""

from __future__ import annotations

import logging
from pathlib import Path
from threading import Event
from typing import Sequence

from PySide6.QtCore import QThread, Signal

from image_converter.core.background_removal import (
    BackgroundRemovalConfig,
    BackgroundRemovalService,
    BackgroundRemovalTask,
)
from image_converter.core.engine import ConversionResult

logger = logging.getLogger(__name__)


class BackgroundRemovalWorker(QThread):
    """Process a planned batch; cancellation takes effect between files."""

    file_completed = Signal(int, object)
    progress_updated = Signal(int, int)
    batch_completed = Signal(object, bool)

    def __init__(
        self,
        tasks: Sequence[BackgroundRemovalTask],
        config: BackgroundRemovalConfig,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.tasks = list(tasks)
        self.config = config
        self._cancel_event = Event()

    def cancel(self) -> None:
        """Ask the service to stop safely without terminating its thread."""
        self._cancel_event.set()

    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def run(self) -> None:
        total = len(self.tasks)
        completed: dict[int, ConversionResult] = {}

        def record_result(result: ConversionResult) -> None:
            key = Path(result.input_path).resolve()
            index = task_indices[key]
            if index in completed:
                return
            completed[index] = result
            self.file_completed.emit(index, result)
            self.progress_updated.emit(len(completed), total)

        def on_progress(
            _completed_count: int, _total_count: int, result: ConversionResult
        ) -> None:
            record_result(result)

        try:
            if self.is_cancelled() or total == 0:
                return
            task_indices = {
                Path(task.input_path).resolve(): index for index, task in enumerate(self.tasks)
            }
            service = BackgroundRemovalService(self.config)
            results = service.run_batch(
                self.tasks,
                progress_callback=on_progress,
                cancel_check=self.is_cancelled,
            )
            # Retain results even if a service returns an item without a callback.
            for result in results:
                record_result(result)
        except Exception as exc:
            logger.exception("Background removal batch failed")
            for index, task in enumerate(self.tasks):
                if index in completed:
                    continue
                result = ConversionResult(
                    success=False,
                    input_path=str(task.input_path),
                    output_path=str(task.output_path),
                    error_message=f"Background removal failed: {exc}",
                )
                completed[index] = result
                self.file_completed.emit(index, result)
                self.progress_updated.emit(len(completed), total)
        finally:
            ordered_results = [completed[index] for index in sorted(completed)]
            self.batch_completed.emit(ordered_results, self.is_cancelled())
