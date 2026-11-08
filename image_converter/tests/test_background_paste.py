"""Pasting images straight into the background-removal queue (and the conversion queue)."""

from __future__ import annotations

import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PySide6.QtCore import QMimeData, QPointF, Qt, QThreadPool, QUrl
from PySide6.QtGui import QColor, QDropEvent, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from image_converter.core.engine import ConversionResult
from image_converter.ui import image_clipboard
from image_converter.ui.background_removal_page import BackgroundRemovalPage
from image_converter.ui.main_window import ImageConverterMainWindow


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app
    app.clipboard().clear()
    app.processEvents()


@pytest.fixture(autouse=True)
def isolated_temp(tmp_path, monkeypatch):
    """Keep pasted scratch files and the Pictures folder inside the test sandbox."""
    scratch = tmp_path / "tmp"
    scratch.mkdir()
    monkeypatch.setattr(image_clipboard.tempfile, "gettempdir", lambda: str(scratch))
    return scratch


@pytest.fixture
def page(qapp, tmp_path, monkeypatch):
    result = BackgroundRemovalPage()
    monkeypatch.setattr(result, "_pasted_output_dir", lambda: tmp_path / "Pictures" / "Background Removed")
    yield result
    QThreadPool.globalInstance().waitForDone(5000)
    qapp.processEvents()
    result._discard_all_pasted()
    result.close()


def settle(qapp, predicate, timeout=5):
    end = time.monotonic() + timeout
    while not predicate() and time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.005)
    qapp.processEvents()
    assert predicate()


def bitmap(width=40, height=30, color="#3366cc", alpha=255):
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    value = QColor(color)
    value.setAlpha(alpha)
    image.fill(value)
    return image


def jpeg(path: Path) -> Path:
    Image.new("RGB", (16, 12), "red").save(path)
    return path


def test_paste_bitmap_saves_private_png_queues_and_selects_it(qapp, page, isolated_temp):
    qapp.clipboard().setImage(bitmap(alpha=120))
    page.paste_images()
    settle(qapp, lambda: len(page.files) == 1)
    path = page.files[0]
    assert path.parent == (isolated_temp / "UniversalFileConverter" / "pasted").resolve()
    assert path.name.startswith("pasted-") and path.suffix == ".png"
    with Image.open(path) as saved:
        assert saved.mode == "RGBA" and saved.size == (40, 30)
        assert saved.getpixel((0, 0))[3] == 120  # transparency survives the paste
    assert page.file_list.currentRow() == 0
    assert page.btn_start.isEnabled() and page.btn_paste.isEnabled()
    assert "Pasted image" in page.lbl_status.text()
    assert path in page._pasted


def test_ctrl_v_shortcut_pastes_from_the_queue(qapp, page):
    page.show()
    page.activateWindow()
    page.file_list.setFocus()
    qapp.processEvents()
    qapp.clipboard().setImage(bitmap())
    QTest.keyClick(page.file_list, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    settle(qapp, lambda: len(page.files) == 1)


def test_ctrl_v_in_a_text_field_still_pastes_text_not_an_image(qapp, page):
    page.show()
    page.activateWindow()
    page.txt_output.setFocus()
    qapp.processEvents()
    qapp.clipboard().setText("C:/cutouts")
    QTest.keyClick(page.txt_output, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    assert page.txt_output.text() == "C:/cutouts"
    assert not page.files


def test_paste_copied_files_queues_the_originals_without_copying(qapp, page, tmp_path):
    first, second = jpeg(tmp_path / "a.jpg"), jpeg(tmp_path / "b.jpg")
    notes = tmp_path / "notes.txt"
    notes.write_text("not an image")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(p)) for p in (first, second, notes)])
    qapp.clipboard().setMimeData(mime)
    page.paste_images()
    assert page.files == [first.resolve(), second.resolve()]
    assert not page._pasted  # originals are never treated as deletable scratch copies
    assert "Pasted 2 images" in page.lbl_status.text()


def test_paste_text_path_and_ignores_other_text(qapp, page, tmp_path):
    photo = jpeg(tmp_path / "photo.jpg")
    qapp.clipboard().setText(f'"{photo}"')
    page.paste_images()
    assert page.files == [photo.resolve()]
    qapp.clipboard().setText("just some words")
    page.paste_images()
    assert page.files == [photo.resolve()]
    assert "no image" in page.lbl_status.text().lower()
    assert page.lbl_status.property("state") == "warning"


def test_paste_empty_clipboard_reports_how_to_proceed(qapp, page):
    qapp.clipboard().clear()
    page.paste_images()
    assert not page.files
    assert "Copy a picture or take a screenshot" in page.lbl_status.text()


def test_removing_or_clearing_pasted_images_deletes_their_scratch_files(qapp, page):
    for color in ("#ff0000", "#00ff00"):
        qapp.clipboard().setImage(bitmap(color=color))
        page.paste_images()
        settle(qapp, lambda: not page._paste_tasks and page.btn_paste.isEnabled())
    assert len(page.files) == 2
    first, second = page.files
    assert first.exists() and second.exists()
    page.file_list.setCurrentRow(0)
    page.file_list.item(0).setSelected(True)
    page.remove_selected()
    assert not first.exists() and second.exists()
    page.clear_files()
    assert not second.exists() and not page.files


def test_two_pastes_in_one_second_get_distinct_files(qapp, page):
    for color in ("#ff0000", "#00ff00", "#0000ff"):
        qapp.clipboard().setImage(bitmap(color=color))
        page.paste_images()
        settle(qapp, lambda: not page._paste_tasks and page.btn_paste.isEnabled())
    assert len(set(page.files)) == 3 == len(page.files)


def test_pasted_images_are_saved_to_the_default_folder_not_the_scratch_folder(
    qapp, page, tmp_path, monkeypatch
):
    import image_converter.ui.background_worker as worker_module

    seen = {}

    class Service:
        active_model = "balanced"

        def __init__(self, config):
            pass

        def run_batch(self, tasks, progress_callback, cancel_check):
            results = []
            for task in tasks:
                seen["output"] = task.output_path
                task.output_path.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGBA", (40, 30), (255, 0, 0, 0)).save(task.output_path)
                result = ConversionResult(True, str(task.input_path), str(task.output_path))
                results.append(result)
                progress_callback(len(results), len(tasks), result)
            return results

    monkeypatch.setattr(worker_module, "BackgroundRemovalService", Service)
    qapp.clipboard().setImage(bitmap())
    page.paste_images()
    settle(qapp, lambda: len(page.files) == 1)
    page.start()
    settle(qapp, lambda: not page.is_running)
    expected = (tmp_path / "Pictures" / "Background Removed").resolve()
    assert seen["output"].parent == expected
    assert seen["output"].exists()
    assert "Balanced model" in page.lbl_status.text()
    # A chosen output folder always wins over the default.
    page.clear_files()
    qapp.clipboard().setImage(bitmap(color="#112233"))
    page.paste_images()
    settle(qapp, lambda: len(page.files) == 1)
    page.txt_output.setText(str(tmp_path / "chosen"))
    page.start()
    settle(qapp, lambda: not page.is_running)
    assert seen["output"].parent == (tmp_path / "chosen").resolve()


def test_paste_is_refused_while_a_batch_runs(qapp, page):
    page.worker = object()  # any non-None worker means a batch is running
    try:
        qapp.clipboard().setImage(bitmap())
        page.paste_images()
        assert not page.files
        assert "Wait for the current batch" in page.lbl_status.text()
    finally:
        page.worker = None


def test_dropping_pixels_without_a_file_pastes_them(qapp, page):
    mime = QMimeData()
    mime.setImageData(bitmap(color="#abcdef"))
    event = QDropEvent(
        QPointF(5, 5), Qt.DropAction.CopyAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    page.dropEvent(event)
    settle(qapp, lambda: len(page.files) == 1)


def test_save_pasted_image_rejects_empty_and_oversized_images(monkeypatch):
    with pytest.raises(ValueError):
        image_clipboard.save_pasted_image(QImage())
    monkeypatch.setattr(image_clipboard, "MAX_CLIPBOARD_PIXELS", 100)
    with pytest.raises(ValueError, match="120 megapixel"):
        image_clipboard.save_pasted_image(bitmap(20, 20))


def test_large_opaque_paste_falls_back_to_jpeg_but_transparent_one_stays_png(monkeypatch):
    monkeypatch.setattr(image_clipboard, "MAX_PASTE_BYTES", 10)
    opaque = image_clipboard.save_pasted_image(bitmap(64, 64, alpha=255).convertToFormat(QImage.Format.Format_RGB32))
    assert opaque.suffix == ".jpg" and opaque.exists()
    assert not opaque.with_suffix(".png").exists()
    transparent = image_clipboard.save_pasted_image(bitmap(64, 64, alpha=100))
    assert transparent.suffix == ".png"


def test_scratch_helpers_never_delete_outside_the_paste_folder(tmp_path):
    outside = tmp_path / "keep.png"
    outside.write_bytes(b"x")
    image_clipboard.discard_pasted_file(outside)
    assert outside.exists()
    inside = image_clipboard.save_pasted_image(bitmap())
    old = time.time() - 5 * 24 * 3600
    os.utime(inside, (old, old))
    fresh = image_clipboard.save_pasted_image(bitmap())
    assert image_clipboard.purge_stale_pasted_files() == 1
    assert not inside.exists() and fresh.exists()


def test_auto_copy_after_a_single_result(qapp, page, tmp_path, monkeypatch):
    import image_converter.ui.background_worker as worker_module

    class Service:
        active_model = "fast"

        def __init__(self, config):
            pass

        def run_batch(self, tasks, progress_callback, cancel_check):
            results = []
            for task in tasks:
                task.output_path.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGBA", (40, 30), (255, 0, 0, 255)).save(task.output_path)
                result = ConversionResult(True, str(task.input_path), str(task.output_path))
                results.append(result)
                progress_callback(len(results), len(tasks), result)
            return results

    monkeypatch.setattr(worker_module, "BackgroundRemovalService", Service)
    source = jpeg(tmp_path / "photo.jpg")
    page.add_files([source])
    page.chk_autocopy.setChecked(True)
    qapp.clipboard().setText("before")
    page.start()
    settle(qapp, lambda: not page.is_running)
    settle(qapp, lambda: qapp.clipboard().mimeData().hasImage(), timeout=8)
    assert qapp.clipboard().mimeData().hasFormat("image/png")


def test_main_window_ctrl_v_pastes_files_and_bitmaps_on_conversion_pages(qapp, tmp_path, monkeypatch):
    window = ImageConverterMainWindow()
    monkeypatch.setattr(
        "image_converter.ui.main_window.QStandardPaths.writableLocation",
        lambda *_: str(tmp_path / "Pictures"),
    )
    photo = jpeg(tmp_path / "copied.jpg")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(photo))])
    qapp.clipboard().setMimeData(mime)
    window._paste_from_clipboard()
    assert photo.resolve() in [p.resolve() for p in window.queue_table.file_paths]
    qapp.clipboard().setImage(bitmap())
    window._paste_from_clipboard()
    settle(qapp, lambda: any(p.parent.name == "Pasted Images" for p in window.queue_table.file_paths))
    saved = next(p for p in window.queue_table.file_paths if p.parent.name == "Pasted Images")
    assert saved.parent == tmp_path / "Pictures" / "Pasted Images" and saved.exists()
    window.close()


def test_main_window_disables_its_paste_shortcut_on_the_background_page(qapp):
    window = ImageConverterMainWindow()
    window._set_app_mode(3)
    assert not window._paste_shortcut.isEnabled()
    assert window.background_removal_page.paste_shortcut.isEnabled()
    window._set_app_mode(0)
    assert window._paste_shortcut.isEnabled()
    window.close()
