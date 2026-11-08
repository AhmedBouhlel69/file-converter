"""Usability: no silent overwrites, sensible defaults, responsive tools."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication, QMessageBox

from image_converter.core.conversion.engine import ConversionConfig, UniversalConverterEngine
from image_converter.ui.components import default_output_format, get_compatible_output_formats
from image_converter.ui.main_window import ImageConverterMainWindow, unique_destination


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def settle(qapp, window, rounds=40):
    from PySide6.QtCore import QThreadPool

    QThreadPool.globalInstance().waitForDone(5000)
    for _ in range(rounds):
        qapp.processEvents()


def test_unique_destination_never_reuses_existing_or_reserved_names(tmp_path):
    (tmp_path / "report.pdf").write_bytes(b"old")
    reserved: set = set()
    first = unique_destination(tmp_path / "report.pdf", reserved)
    second = unique_destination(tmp_path / "report.pdf", reserved)
    assert first.name == "report (2).pdf" and second.name == "report (3).pdf"
    assert unique_destination(tmp_path / "new.pdf", reserved).name == "new.pdf"


def test_conversion_does_not_overwrite_an_existing_output(qapp, tmp_path, monkeypatch):
    import image_converter.ui.main_window as main_module

    source = tmp_path / "photo.jpg"
    Image.new("RGB", (40, 30), "red").save(source)
    existing = tmp_path / "photo.png"
    existing.write_bytes(b"keep me")
    captured = []

    class FakeWorker:
        def __init__(self, tasks, _engine):
            captured.extend(tasks)
            raise RuntimeError("stop after planning")

    monkeypatch.setattr(main_module, "BatchConversionWorker", FakeWorker)
    window = ImageConverterMainWindow()
    window.add_images([source])
    settle(qapp, window)
    window.queue_table.set_target_format_for_row(0, "PNG")
    with pytest.raises(RuntimeError):
        window.start_conversion()
    assert captured and captured[0][1].name == "photo (2).png"
    assert existing.read_bytes() == b"keep me"
    window._is_converting = False
    window.close()


def test_mixed_queue_gets_a_sensible_target_per_file(qapp, tmp_path):
    import docx
    import pymupdf

    photo = tmp_path / "photo.jpg"
    Image.new("RGB", (40, 30), "red").save(photo)
    report = tmp_path / "report.docx"
    docx.Document().save(report)
    table = tmp_path / "table.csv"
    table.write_text("a,b\n1,2\n", encoding="utf-8")
    pdf = tmp_path / "scan.pdf"
    doc = pymupdf.open()
    doc.new_page()
    doc.save(pdf)

    window = ImageConverterMainWindow()
    window.add_images([photo, report, table, pdf])
    settle(qapp, window)
    model = window.queue_table.queue_model
    targets = {entry.path.name: entry.target_format for entry in model.entries}
    assert targets == {"photo.jpg": "PNG", "report.docx": "PDF", "table.csv": "XLSX", "scan.pdf": "DOCX"}
    assert window.settings_widget.get_target_format() == "PER_FILE"
    window.close()


def test_single_kind_queue_defaults_to_a_real_conversion(qapp, tmp_path):
    photo = tmp_path / "photo.heic"
    Image.new("RGB", (40, 30), "red").save(tmp_path / "photo.png")
    window = ImageConverterMainWindow()
    window.settings_widget.combo_format.setCurrentText("TXT")  # left over from an earlier batch
    window.settings_widget._format_chosen_by_user = False
    window.add_images([tmp_path / "photo.png"])
    settle(qapp, window)
    assert window.settings_widget.get_target_format() == "JPG"
    window.close()
    assert not photo.exists()


def test_formats_that_always_failed_are_no_longer_offered():
    assert "PPTX" not in get_compatible_output_formats(Path("a.docx"))
    assert "DOCX" not in get_compatible_output_formats(Path("a.pptx"))
    assert default_output_format(Path("a.jpg")) == "PNG"
    assert default_output_format(Path("a.png")) == "JPG"
    assert default_output_format(Path("a.pdf")) == "DOCX"


def test_pdf_to_powerpoint_makes_one_slide_per_page(tmp_path):
    import pymupdf
    from pptx import Presentation

    source = tmp_path / "deck.pdf"
    doc = pymupdf.open()
    for number in range(3):
        page = doc.new_page(width=842, height=595)
        page.insert_text((72, 100), f"Page {number + 1} heading", fontsize=28)
    doc.save(source)
    result = UniversalConverterEngine().convert_single(source, tmp_path / "deck.pptx", ConversionConfig(target_format="PPTX"))
    assert result.success, result.error_message
    prs = Presentation(str(tmp_path / "deck.pptx"))
    slides = list(prs.slides)
    assert len(slides) == 3
    assert abs(prs.slide_width / prs.slide_height - 842 / 595) < 0.01
    assert "Page 2 heading" in slides[1].notes_slide.notes_text_frame.text


def test_pdf_to_images_never_overwrite_earlier_pages(tmp_path):
    import pymupdf

    source = tmp_path / "two.pdf"
    doc = pymupdf.open()
    doc.new_page()
    doc.new_page()
    doc.save(source)
    (tmp_path / "two_page_1.png").write_bytes(b"earlier export")
    engine = UniversalConverterEngine()
    engine.convert_single(source, tmp_path / "two.png", ConversionConfig(target_format="PNG"))
    assert (tmp_path / "two_page_1.png").read_bytes() == b"earlier export"
    assert (tmp_path / "two (2)_page_1.png").is_file() and (tmp_path / "two (2)_page_2.png").is_file()


def test_rotated_photo_reports_and_previews_upright(qapp, tmp_path):
    from image_converter.core.engine import get_image_metadata
    from image_converter.ui.queue_model import make_thumbnail

    exif = Image.Exif()
    exif[0x0112] = 6
    source = tmp_path / "phone.jpg"
    Image.new("RGB", (120, 80), "green").save(source, exif=exif.tobytes())
    meta = get_image_metadata(source)
    assert (meta["width"], meta["height"]) == (80, 120)
    with Image.open(source) as img:
        thumb = make_thumbnail(img, (72, 72))
    assert thumb.height > thumb.width


def test_image_compressor_runs_in_background_and_reports_each_file(qapp, tmp_path, monkeypatch):
    from image_converter.ui.tool_dialogs import ImageCompressDialog

    sources = []
    for index in range(3):
        path = tmp_path / f"photo{index}.png"
        Image.effect_noise((300, 200), 60).convert("RGB").save(path)
        sources.append(path)
    # Same stem twice must not collide in one batch.
    Image.effect_noise((300, 200), 60).convert("RGB").save(tmp_path / "photo0.bmp")
    sources.append(tmp_path / "photo0.bmp")
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: messages.append(args[2]) or QMessageBox.StandardButton.Ok)
    dialog = ImageCompressDialog(initial_files=sources)
    dialog.combo_format.setCurrentText("JPG")
    dialog.txt_output_dir.setText(str(tmp_path / "out"))
    dialog._execute_compress()
    assert dialog.is_running or messages  # returns immediately; work happens off the GUI thread
    assert not dialog.btn_compress.isEnabled() or messages
    dialog.wait_until_done()
    outputs = sorted(p.name for p in (tmp_path / "out").iterdir())
    assert outputs == ["photo0_compressed.jpg", "photo0_compressed_2.jpg", "photo1_compressed.jpg", "photo2_compressed.jpg"]
    assert all(dialog.table.item(row, 3).text() != "Waiting…" for row in range(4))
    assert messages and "4 outputs saved" in messages[0]


def test_image_compressor_can_be_stopped(qapp, tmp_path, monkeypatch):
    import time

    from image_converter.ui.tool_dialogs import ImageCompressDialog

    sources = []
    for index in range(6):
        path = tmp_path / f"p{index}.png"
        Image.new("RGB", (40, 30), "blue").save(path)
        sources.append(path)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    dialog = ImageCompressDialog(initial_files=sources)
    real = dialog.engine.convert_single

    def slow(*args, **kwargs):
        time.sleep(0.15)
        return real(*args, **kwargs)

    monkeypatch.setattr(dialog.engine, "convert_single", slow)
    dialog.txt_output_dir.setText(str(tmp_path / "out"))
    dialog._execute_compress()
    dialog.reject()  # "Stop"
    assert dialog.btn_cancel.text() == "Stopping…"
    dialog.wait_until_done()
    produced = list((tmp_path / "out").iterdir()) if (tmp_path / "out").exists() else []
    assert len(produced) < 6
    assert not dialog.is_running


def test_files_dropped_on_a_tool_page_open_that_tool(qapp, tmp_path, monkeypatch):
    window = ImageConverterMainWindow()
    opened = []
    monkeypatch.setattr(window, "_open_merge_dialog_with_files", lambda paths: opened.append(("merge", paths)))
    monkeypatch.setattr(window, "_open_compress_dialog_with_file", lambda path: opened.append(("compress", path)))
    monkeypatch.setattr(window, "_open_image_compress_dialog_with_files", lambda paths: opened.append(("images", paths)))
    pdf, photo, sheet = tmp_path / "a.pdf", tmp_path / "b.jpg", tmp_path / "c.csv"

    window._set_app_mode(2)
    window.pdf_tools_page.set_active_tool(0)
    assert window._route_drop_to_tool([pdf, photo, sheet])
    window.pdf_tools_page.set_active_tool(3)
    assert window._route_drop_to_tool([photo, pdf])
    window._set_app_mode(1)
    assert window._route_drop_to_tool([photo, sheet])
    window._set_app_mode(0)
    assert not window._route_drop_to_tool([photo])
    assert opened == [("merge", [pdf, photo]), ("compress", pdf), ("images", [photo])]
    window.close()
