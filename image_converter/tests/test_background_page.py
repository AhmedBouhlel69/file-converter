"""Behavior checks for the separate background removal workspace."""

from __future__ import annotations

import os
import time
from threading import Event, current_thread, main_thread
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PySide6.QtCore import QMimeData, QPointF, Qt, QThreadPool, QTimer, QUrl
from PySide6.QtGui import QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from image_converter.core.engine import ConversionResult
from image_converter.ui.background_removal_page import BackgroundRemovalPage
from image_converter.ui.main_window import ImageConverterMainWindow


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def make_image(path, color="red"):
    Image.new("RGB", (40, 30), color).save(path)
    return path


def settle(qapp, predicate, timeout=5):
    end = time.monotonic() + timeout
    while not predicate() and time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()
    assert predicate()


def test_page_adds_supported_unique_files_and_previews_selection(qapp, tmp_path):
    page = BackgroundRemovalPage()
    source = make_image(tmp_path / "photo.jpg")
    unsupported = tmp_path / "notes.txt"
    unsupported.write_text("text")
    page.add_files([source, source, unsupported])
    assert page.files == [source.resolve()]
    settle(qapp, lambda: not page.before_preview.image.isNull())
    assert not page.before_preview.image.isNull()
    assert page.after_preview.image.isNull()
    assert page.btn_start.isEnabled()
    assert "skipped" in page.lbl_status.text()
    page.clear_files()
    assert not page.files
    assert page.before_preview.image.isNull()
    assert not page.btn_start.isEnabled()


def test_page_runs_async_and_retains_per_file_errors(qapp, tmp_path, monkeypatch):
    import image_converter.ui.background_worker as worker_module

    source = make_image(tmp_path / "photo.png")
    broken = tmp_path / "bad.png"
    broken.write_bytes(b"not an image")

    class Service:
        def __init__(self, config):
            assert config.model == "fast"
            assert config.bg_color is None

        def run_batch(self, tasks, progress_callback, cancel_check):
            results = []
            for task in tasks:
                good = task.input_path == source.resolve()
                if good:
                    Image.new("RGBA", (40, 30), (255, 0, 0, 0)).save(task.output_path)
                result = ConversionResult(good, str(task.input_path), str(task.output_path),
                                          error_message=None if good else "Corrupt image")
                results.append(result)
                progress_callback(len(results), len(tasks), result)
            return results

    monkeypatch.setattr(worker_module, "BackgroundRemovalService", Service)
    page = BackgroundRemovalPage()
    page.add_files([source, broken])
    page.start()
    assert page.is_running
    assert not page.btn_add.isEnabled()
    assert not page.btn_start.isEnabled()
    settle(qapp, lambda: not page.is_running)
    assert "1 saved" in page.lbl_status.text()
    assert "1 failed" in page.lbl_status.text()
    assert "Corrupt image" in page.file_list.item(1).toolTip()
    settle(qapp, lambda: not page.after_preview.image.isNull())
    assert page.btn_open.isEnabled()
    assert page.btn_start.isEnabled()
    assert page.outputs[source.resolve()].name == "photo_nobg.png"


def test_invalid_options_are_reported_before_worker_starts(qapp, tmp_path):
    page = BackgroundRemovalPage()
    page.add_files([make_image(tmp_path / "photo.png")])
    page.txt_fill.setText("invalid-color")
    page.start()
    assert not page.is_running
    assert "color" in page.lbl_status.text().lower()
    assert page.lbl_status.property("state") == "error"


def test_queue_action_and_drop_stay_on_dedicated_page(qapp, tmp_path):
    source = make_image(tmp_path / "photo.png")
    other = make_image(tmp_path / "other.jpg")
    window = ImageConverterMainWindow()
    window.add_images([source])
    window.queue_table.tool_background_removal_requested.emit([source])
    assert window.app_stack.currentWidget() is window.background_removal_page
    assert window.background_removal_page.files == [source.resolve()]
    data = QMimeData()
    data.setUrls([QUrl.fromLocalFile(str(other))])
    event = QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction, data,
                       Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    window.dropEvent(event)
    assert window.app_stack.currentWidget() is window.background_removal_page
    assert window.background_removal_page.files == [source.resolve(), other.resolve()]
    assert window.queue_table.rowCount() == 1
    window.close()
    QThreadPool.globalInstance().waitForDone(3000)


def test_close_requests_safe_cancel_while_removal_is_running(qapp, tmp_path, monkeypatch):
    import image_converter.ui.background_worker as worker_module

    class Service:
        def __init__(self, config):
            pass

        def run_batch(self, tasks, progress_callback, cancel_check):
            while not cancel_check():
                time.sleep(0.005)
            return []

    monkeypatch.setattr(worker_module, "BackgroundRemovalService", Service)
    window = ImageConverterMainWindow()
    window._open_background_removal_with_files([make_image(tmp_path / "photo.png")])
    window.background_removal_page.start()
    assert not window.close()
    settle(qapp, lambda: not window.background_removal_page.is_running)
    assert "Cancelled" in window.background_removal_page.lbl_status.text()
    assert window.close()


def test_preview_decode_keeps_event_loop_responsive(qapp, tmp_path, monkeypatch):
    import image_converter.ui.background_removal_page as page_module

    release = Event()
    decoding = Event()
    threads = []
    real_reader = page_module.QImageReader

    class SlowReader:
        def __init__(self, path):
            self.reader = real_reader(path)

        def __getattr__(self, name):
            return getattr(self.reader, name)

        def read(self):
            threads.append(current_thread())
            decoding.set()
            release.wait(3)
            return self.reader.read()

    monkeypatch.setattr(page_module, "QImageReader", SlowReader)
    page = BackgroundRemovalPage()
    try:
        page.add_files([make_image(tmp_path / "photo.png")])
        settle(qapp, decoding.is_set)
        heartbeat = []
        QTimer.singleShot(0, lambda: heartbeat.append(True))
        qapp.processEvents()
        assert heartbeat
        assert threads and threads[0] is not main_thread()
    finally:
        release.set()
        settle(qapp, lambda: not page.before_preview._tasks)


def test_failed_rerun_does_not_show_previous_cutout(qapp, tmp_path, monkeypatch):
    import image_converter.ui.background_worker as worker_module

    calls = []

    class Service:
        def __init__(self, config):
            pass

        def run_batch(self, tasks, progress_callback, cancel_check):
            task = tasks[0]
            good = not calls
            calls.append(True)
            if good:
                Image.new("RGBA", (40, 30), (255, 0, 0, 128)).save(task.output_path)
            result = ConversionResult(good, str(task.input_path), str(task.output_path),
                                      error_message=None if good else "Model missing")
            progress_callback(1, 1, result)
            return [result]

    monkeypatch.setattr(worker_module, "BackgroundRemovalService", Service)
    page = BackgroundRemovalPage()
    page.add_files([make_image(tmp_path / "photo.png")])
    page.start()
    settle(qapp, lambda: not page.is_running)
    settle(qapp, lambda: not page.after_preview.image.isNull())
    page.start()
    assert not page.outputs
    assert page.after_preview.image.isNull()
    settle(qapp, lambda: not page.is_running)
    assert "Model missing" in page.lbl_status.text()
    assert page.after_preview.image.isNull()


def test_delete_edits_output_path_without_removing_images(qapp, tmp_path):
    window = ImageConverterMainWindow()
    window._open_background_removal_with_files([make_image(tmp_path / "photo.png")])
    page = window.background_removal_page
    window.show()
    page.txt_output.setText("folder")
    page.txt_output.setCursorPosition(0)
    page.txt_output.setFocus()
    qapp.processEvents()
    QTest.keyClick(page.txt_output, Qt.Key.Key_Delete)
    assert page.txt_output.text() == "older"
    assert len(page.files) == 1
    page.file_list.setFocus()
    qapp.processEvents()
    QTest.keyClick(page.file_list, Qt.Key.Key_Delete)
    assert not page.files
    window.close()
