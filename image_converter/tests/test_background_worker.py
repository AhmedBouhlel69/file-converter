"""Worker boundary checks using a fake service rather than model inference."""

from __future__ import annotations

import os
from pathlib import Path
from threading import get_ident

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from image_converter.core.background_removal import BackgroundRemovalConfig, BackgroundRemovalTask
from image_converter.core.engine import ConversionResult
from image_converter.ui import background_worker


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def tasks(tmp_path: Path):
    return [
        BackgroundRemovalTask(tmp_path / f"input_{index}.png", tmp_path / f"output_{index}.png")
        for index in range(3)
    ]


def _result(task, *, success=True):
    return ConversionResult(
        success=success,
        input_path=str(task.input_path),
        output_path=str(task.output_path),
        error_message=None if success else "Cannot decode this image",
    )


def _observe(worker):
    return (
        QSignalSpy(worker.file_completed),
        QSignalSpy(worker.progress_updated),
        QSignalSpy(worker.batch_completed),
        QSignalSpy(worker.finished),
    )


def _start_and_wait(worker, qapp):
    worker.start()
    assert worker.wait(5000), "Background worker did not exit"
    qapp.processEvents()


def test_worker_constructs_service_off_ui_thread_and_maps_callback_rows(
    qapp, tasks, monkeypatch
):
    constructed_on = []
    main_thread = get_ident()
    config = BackgroundRemovalConfig()

    class FakeService:
        def __init__(self, received_config):
            assert received_config is config
            constructed_on.append(get_ident())

        def run_batch(self, received_tasks, progress_callback, cancel_check):
            assert received_tasks == tasks
            assert not cancel_check()
            results = []
            for completed, task in enumerate(reversed(received_tasks), 1):
                result = _result(task, success=task != tasks[1])
                progress_callback(completed, len(received_tasks), result)
                results.append(result)
            return results

    monkeypatch.setattr(background_worker, "BackgroundRemovalService", FakeService)
    worker = background_worker.BackgroundRemovalWorker(tasks, config)
    file_spy, progress_spy, batch_spy, finished_spy = _observe(worker)
    assert constructed_on == []

    _start_and_wait(worker, qapp)

    assert len(constructed_on) == 1 and constructed_on[0] != main_thread
    assert [file_spy.at(index)[0] for index in range(file_spy.count())] == [2, 1, 0]
    assert [progress_spy.at(index) for index in range(progress_spy.count())] == [
        [1, 3], [2, 3], [3, 3]
    ]
    assert batch_spy.count() == finished_spy.count() == 1
    results, cancelled = batch_spy.at(0)
    assert not cancelled
    assert [result.input_path for result in results] == [str(task.input_path) for task in tasks]
    assert [result.success for result in results] == [True, False, True]
    assert results[1].error_message == "Cannot decode this image"


def test_worker_cancel_stops_between_files_and_retains_completed_output(qapp, tasks, monkeypatch):
    attempted = []

    class FakeService:
        def __init__(self, config):
            pass

        def run_batch(self, received_tasks, progress_callback, cancel_check):
            results = []
            for task in received_tasks:
                if cancel_check():
                    break
                attempted.append(task)
                result = _result(task)
                progress_callback(len(results) + 1, len(received_tasks), result)
                results.append(result)
            return results

    monkeypatch.setattr(background_worker, "BackgroundRemovalService", FakeService)
    worker = background_worker.BackgroundRemovalWorker(tasks, BackgroundRemovalConfig())
    file_spy, progress_spy, batch_spy, finished_spy = _observe(worker)
    worker.file_completed.connect(lambda *_args: worker.cancel(), Qt.ConnectionType.DirectConnection)

    _start_and_wait(worker, qapp)

    assert attempted == tasks[:1]
    assert worker.is_cancelled()
    assert file_spy.count() == progress_spy.count() == 1
    assert batch_spy.count() == finished_spy.count() == 1
    results, cancelled = batch_spy.at(0)
    assert cancelled and len(results) == 1
    assert results[0].success and results[0].output_path == str(tasks[0].output_path)


@pytest.mark.parametrize("cancelled", [False, True])
def test_empty_or_precancelled_batch_finishes_without_constructing_service(
    qapp, tasks, monkeypatch, cancelled
):
    def unexpected_service(_config):
        pytest.fail("No service should be constructed for an empty or cancelled batch")

    monkeypatch.setattr(background_worker, "BackgroundRemovalService", unexpected_service)
    worker = background_worker.BackgroundRemovalWorker(
        tasks if cancelled else [], BackgroundRemovalConfig()
    )
    file_spy, progress_spy, batch_spy, finished_spy = _observe(worker)
    if cancelled:
        worker.cancel()

    _start_and_wait(worker, qapp)

    assert file_spy.count() == progress_spy.count() == 0
    assert batch_spy.count() == finished_spy.count() == 1
    assert batch_spy.at(0) == [[], cancelled]


@pytest.mark.parametrize("fail_during_init", [False, True])
def test_catastrophic_error_reports_unfinished_tasks_and_keeps_successes(
    qapp, tasks, monkeypatch, fail_during_init
):
    class FailingService:
        def __init__(self, config):
            if fail_during_init:
                raise RuntimeError("Model is missing")

        def run_batch(self, received_tasks, progress_callback, cancel_check):
            progress_callback(1, len(received_tasks), _result(received_tasks[0]))
            raise RuntimeError("Inference session crashed")

    monkeypatch.setattr(background_worker, "BackgroundRemovalService", FailingService)
    worker = background_worker.BackgroundRemovalWorker(tasks, BackgroundRemovalConfig())
    file_spy, progress_spy, batch_spy, finished_spy = _observe(worker)

    _start_and_wait(worker, qapp)

    assert batch_spy.count() == finished_spy.count() == 1
    assert file_spy.count() == progress_spy.count() == len(tasks)
    results, cancelled = batch_spy.at(0)
    assert not cancelled and len(results) == len(tasks)
    failures = results if fail_during_init else results[1:]
    if not fail_during_init:
        assert results[0].success and results[0].output_path == str(tasks[0].output_path)
    expected_error = "Model is missing" if fail_during_init else "Inference session crashed"
    assert all(not result.success and expected_error in result.error_message for result in failures)
