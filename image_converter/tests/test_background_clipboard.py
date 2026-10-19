"""Full-size transparent cutout clipboard behavior and worker races."""

from __future__ import annotations

import os
import time
from io import BytesIO
from pathlib import Path
from threading import Event, current_thread, main_thread

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PySide6.QtCore import QThreadPool, QTimer, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from image_converter.core.engine import ConversionResult
from image_converter.ui.background_removal_page import BackgroundRemovalPage


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app
    # Release offscreen-platform clipboard ownership before QApplication's
    # Python/C++ teardown; real Windows clipboard behavior is smoke-tested.
    app.clipboard().clear()
    app.processEvents()


def settle(qapp, predicate, timeout=5):
    end = time.monotonic() + timeout
    while not predicate() and time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.005)
    qapp.processEvents()
    assert predicate()


@pytest.fixture
def page(qapp):
    result = BackgroundRemovalPage()
    yield result
    QThreadPool.globalInstance().waitForDone(5000)
    qapp.processEvents()
    result.close()


def add_result(page, tmp_path, name="photo", fmt="PNG", size=(40, 30)):
    source = tmp_path / f"{name}.jpg"
    Image.new("RGB", (40, 30), "blue").save(source)
    output = tmp_path / f"{name}_nobg.{fmt.lower()}"
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    image.putpixel((3, 4), (240, 30, 50, 127))
    image.putpixel((9, 8), (10, 220, 70, 255))
    image.save(output, format=fmt, lossless=True)
    page.add_files([source])
    index = page.files.index(source.resolve())
    page._file_completed(index, ConversionResult(True, str(source), str(output)))
    return source.resolve(), output


@pytest.mark.parametrize("fmt", ["PNG", "WEBP"])
def test_copy_has_full_resolution_alpha_image_png_and_file_url(qapp, page, tmp_path, fmt):
    source, output = add_result(page, tmp_path, fmt=fmt, size=(1800, 1250))
    settle(qapp, lambda: not page.after_preview.image.isNull())
    assert page.after_preview.image.width() <= 1200
    assert page.btn_copy.isEnabled()
    qapp.clipboard().setText("previous clipboard")
    page.btn_copy.click()
    assert not page.btn_copy.isEnabled()
    settle(qapp, lambda: not page._copy_tasks)
    mime = qapp.clipboard().mimeData()
    assert mime.hasImage() and mime.hasFormat("image/png") and mime.hasUrls()
    assert Path(mime.urls()[0].toLocalFile()) == output
    native = QImage(mime.imageData())
    assert (native.width(), native.height()) == (1800, 1250)
    assert native.pixelColor(0, 0).alpha() == 0
    assert native.pixelColor(3, 4).getRgb() == (240, 30, 50, 127)
    assert native.pixelColor(9, 8).getRgb() == (10, 220, 70, 255)
    with Image.open(BytesIO(bytes(mime.data("image/png")))) as png:
        assert png.size == (1800, 1250)
        assert png.getpixel((0, 0))[3] == 0
        assert png.getpixel((3, 4)) == (240, 30, 50, 127)
    if os.name == "nt":
        assert bytes(mime.data('application/x-qt-windows-mime;value="PNG"')) == bytes(mime.data("image/png"))
    assert page.lbl_status.text() == "Copied image. Paste with Ctrl+V."


def test_copy_without_current_success_or_deleted_file_keeps_clipboard(qapp, page, tmp_path):
    qapp.clipboard().setText("keep me")
    page.copy_result()
    assert not page.btn_copy.isEnabled()
    source, output = add_result(page, tmp_path)
    settle(qapp, lambda: not page.after_preview._tasks)
    output.unlink()
    page.copy_result()
    assert not page.btn_copy.isEnabled()
    assert qapp.clipboard().text() == "keep me"
    page._file_completed(0, ConversionResult(False, str(source), str(output), error_message="Failed"))
    page.copy_result()
    assert not page.outputs and qapp.clipboard().text() == "keep me"
    page.clear_files()
    assert not page.btn_copy.isEnabled()


def test_unreadable_result_disables_copy_and_does_not_replace_clipboard(qapp, page, tmp_path):
    source, output = add_result(page, tmp_path)
    output.write_bytes(b"broken export")
    qapp.clipboard().setText("keep me")
    page.copy_result()
    settle(qapp, lambda: not page._copy_tasks)
    assert not page.btn_copy.isEnabled()
    assert "Could not copy image" in page.lbl_status.text()
    assert qapp.clipboard().text() == "keep me"


@pytest.mark.parametrize("focus", ["after_preview", "file_list"])
def test_copy_shortcut_is_scoped_to_result_or_queue(qapp, page, tmp_path, focus):
    add_result(page, tmp_path)
    page.show()
    page.activateWindow()
    widget = getattr(page, focus)
    widget.setFocus()
    qapp.processEvents()
    QTest.keyClick(widget, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    settle(qapp, lambda: page.lbl_status.text() == "Copied image. Paste with Ctrl+V.")
    assert qapp.clipboard().mimeData().hasImage()
    assert page.copy_action in page.after_preview.actions()


def test_line_edit_copy_keeps_ordinary_text_behavior(qapp, page, tmp_path):
    add_result(page, tmp_path)
    page.show()
    page.activateWindow()
    page.txt_output.setText("selected folder text")
    page.txt_output.selectAll()
    page.txt_output.setFocus()
    qapp.processEvents()
    QTest.keyClick(page.txt_output, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert qapp.clipboard().text() == "selected folder text"
    assert not page._copy_tasks


def test_clipboard_formats_are_built_and_published_on_gui_thread(qapp, page, tmp_path, monkeypatch):
    import image_converter.ui.background_removal_page as page_module

    add_result(page, tmp_path)
    threads = []
    real_mime = page_module.clipboard_mime_data

    def checked_mime(result):
        threads.append(current_thread())
        return real_mime(result)

    monkeypatch.setattr(page_module, "clipboard_mime_data", checked_mime)
    page.copy_result()
    settle(qapp, lambda: not page._copy_tasks)
    assert threads == [main_thread()]
    assert qapp.clipboard().mimeData().hasImage()


@pytest.mark.parametrize("change", ["selection", "clear", "rerun", "delete", "replace"])
def test_stale_copy_never_overwrites_clipboard_and_decode_is_off_gui(
    qapp, page, tmp_path, monkeypatch, change,
):
    import image_converter.ui.background_removal_page as page_module
    import image_converter.ui.background_worker as worker_module

    source, output = add_result(page, tmp_path)
    add_result(page, tmp_path, name="second")
    release, decoding = Event(), Event()
    real_load = page_module.load_clipboard_image
    threads = []

    def slow_load(path):
        threads.append(current_thread())
        prepared = real_load(path)
        decoding.set()
        release.wait(5)
        return prepared

    class FailedService:
        def __init__(self, config):
            pass

        def run_batch(self, tasks, progress_callback, cancel_check):
            results = []
            for index, task in enumerate(tasks):
                result = ConversionResult(False, str(task.input_path), str(task.output_path), error_message="Model missing")
                results.append(result)
                progress_callback(index + 1, len(tasks), result)
            return results

    monkeypatch.setattr(page_module, "load_clipboard_image", slow_load)
    monkeypatch.setattr(worker_module, "BackgroundRemovalService", FailedService)
    qapp.clipboard().setText("keep me")
    try:
        page.copy_result()
        settle(qapp, decoding.is_set)
        heartbeat = []
        QTimer.singleShot(0, lambda: heartbeat.append(True))
        qapp.processEvents()
        assert heartbeat and threads[0] is not main_thread()
        if change == "selection":
            page.file_list.setCurrentRow(1)
        elif change == "clear":
            page.clear_files()
        elif change == "rerun":
            page.start()
            assert not page.btn_copy.isEnabled()
            settle(qapp, lambda: not page.is_running)
        elif change == "delete":
            output.unlink()
        else:
            Image.new("RGBA", (50, 50), "red").save(output)
        release.set()
        settle(qapp, lambda: not page._copy_tasks)
        assert qapp.clipboard().text() == "keep me"
        if change != "selection":
            assert not page.btn_copy.isEnabled()
    finally:
        release.set()
        settle(qapp, lambda: not page._copy_tasks)


def test_multiple_selection_copies_only_current_completed_output(qapp, page, tmp_path):
    _, first = add_result(page, tmp_path)
    _, second = add_result(page, tmp_path, name="second")
    page.file_list.selectAll()
    page.file_list.setCurrentRow(1)
    page.copy_result()
    settle(qapp, lambda: not page._copy_tasks)
    assert [Path(url.toLocalFile()) for url in qapp.clipboard().mimeData().urls()] == [second]
