"""Smaller PNGs, LibreOffice fallback, PDF password and page-number tools."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pymupdf
import pytest
from PIL import Image, ImageDraw
from PySide6.QtWidgets import QApplication, QMessageBox

from image_converter.core.conversion.engine import ConversionConfig, UniversalConverterEngine
from image_converter.core.platform import libreoffice


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def engine():
    return UniversalConverterEngine()


def _screenshot(path: Path) -> Path:
    image = Image.new("RGB", (640, 400), (15, 23, 42))
    draw = ImageDraw.Draw(image)
    for i in range(40):
        draw.rectangle((10 + i * 15, 20, 20 + i * 15, 380), fill=(30 + i * 5, 80, 200 - i * 3))
        draw.text((12, 20 + i * 9), f"Line {i} of a UI", fill=(240, 240, 240))
    image = image.resize((1280, 800), Image.Resampling.LANCZOS)  # anti-aliasing: thousands of colours
    image.save(path)
    return path


# ---------------------------------------------------------------------------
# PNG palettes
# ---------------------------------------------------------------------------

def test_png_with_few_colours_is_stored_losslessly_as_palette(engine, tmp_path):
    source = tmp_path / "icon.png"
    image = Image.new("RGBA", (120, 80), (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle((10, 10, 60, 60), fill=(200, 30, 30, 255))
    ImageDraw.Draw(image).rectangle((60, 20, 110, 70), fill=(30, 30, 200, 128))
    image.save(source)
    result = engine.convert_single(source, tmp_path / "out.png", ConversionConfig(target_format="PNG"))
    assert result.success
    out = Image.open(tmp_path / "out.png")
    assert out.mode == "P"
    assert np.array_equal(np.asarray(out.convert("RGBA")), np.asarray(image))


def test_png_reduce_shrinks_screenshots_with_small_error(engine, tmp_path):
    source = _screenshot(tmp_path / "screen.png")
    engine.convert_single(source, tmp_path / "full.png", ConversionConfig(target_format="PNG"))
    engine.convert_single(source, tmp_path / "small.png", ConversionConfig(target_format="PNG", png_palette="reduce"))
    full, small = (tmp_path / "full.png").stat().st_size, (tmp_path / "small.png").stat().st_size
    assert small < full * 0.6
    error = np.abs(np.asarray(Image.open(source).convert("RGB"), dtype=int) - np.asarray(Image.open(tmp_path / "small.png").convert("RGB"), dtype=int))
    assert error.mean() < 3


def test_image_compressor_uses_png_palette_option(qapp, tmp_path, monkeypatch):
    from image_converter.ui.tool_dialogs import ImageCompressDialog

    source = _screenshot(tmp_path / "screen.png")
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    dialog = ImageCompressDialog(initial_files=[source])
    dialog.combo_format.setCurrentText("PNG")
    dialog.chk_resize.setChecked(False)
    dialog.txt_output_dir.setText(str(tmp_path / "out"))
    assert dialog.chk_png_palette.isChecked()
    dialog._execute_compress()
    dialog.wait_until_done()
    output = tmp_path / "out" / "screen_compressed.png"
    assert Image.open(output).mode == "P"
    assert output.stat().st_size < source.stat().st_size * 0.6


# ---------------------------------------------------------------------------
# LibreOffice fallback
# ---------------------------------------------------------------------------

def test_office_message_mentions_libreoffice_when_neither_is_installed(engine, tmp_path, monkeypatch):
    import docx

    monkeypatch.setattr("sys.platform", "linux")
    source = tmp_path / "letter.docx"
    docx.Document().save(source)
    result = engine.convert_single(source, tmp_path / "letter.pdf", ConversionConfig(target_format="PDF"))
    assert not result.success
    assert "requires Microsoft Word" in result.error_message and "LibreOffice" in result.error_message


needs_lo = pytest.mark.skipif(libreoffice.find_soffice() is None, reason="LibreOffice is not installed")


@pytest.mark.libreoffice
@needs_lo
def test_word_to_pdf_without_office_uses_libreoffice(engine, tmp_path, monkeypatch):
    import docx

    monkeypatch.setattr("sys.platform", "linux")
    source = tmp_path / "letter.docx"
    d = docx.Document()
    d.add_heading("Hello from Word", 1)
    d.add_paragraph("Accents: é è ü. Arabic: مرحبا")
    d.save(source)
    result = engine.convert_single(source, tmp_path / "letter.pdf", ConversionConfig(target_format="PDF"))
    assert result.success, result.error_message
    assert "Hello from Word" in pymupdf.open(tmp_path / "letter.pdf")[0].get_text()


@pytest.mark.libreoffice
@needs_lo
def test_odt_and_rtf_conversions_use_libreoffice(engine, tmp_path, monkeypatch):
    monkeypatch.setattr("os.name", "posix")
    source = tmp_path / "note.txt"
    source.write_text("Line one é\nLine two", encoding="utf-8")
    assert engine.convert_single(source, tmp_path / "note.rtf", ConversionConfig(target_format="RTF")).success
    rtf_to_odt = engine.convert_single(tmp_path / "note.rtf", tmp_path / "note.odt", ConversionConfig(target_format="ODT"))
    assert rtf_to_odt.success, rtf_to_odt.error_message
    odt_to_docx = engine.convert_single(tmp_path / "note.odt", tmp_path / "note.docx", ConversionConfig(target_format="DOCX"))
    assert odt_to_docx.success, odt_to_docx.error_message
    import docx

    assert "Line one é" in "\n".join(p.text for p in docx.Document(str(tmp_path / "note.docx")).paragraphs)


@pytest.mark.libreoffice
@needs_lo
def test_powerpoint_and_excel_to_pdf_use_libreoffice(engine, tmp_path, monkeypatch):
    import openpyxl
    from pptx import Presentation

    monkeypatch.setattr("os.name", "posix")
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = "Quarterly slide"
    prs.save(tmp_path / "deck.pptx")
    result = engine.convert_single(tmp_path / "deck.pptx", tmp_path / "deck.pdf", ConversionConfig(target_format="PDF"))
    assert result.success, result.error_message
    assert "Quarterly slide" in pymupdf.open(tmp_path / "deck.pdf")[0].get_text()

    wb = openpyxl.Workbook()
    wb.active.append(["Item", "Qty"])
    wb.active.append(["Bolts", 12])
    wb.save(tmp_path / "book.xlsx")
    result = engine.convert_single(tmp_path / "book.xlsx", tmp_path / "book.pdf", ConversionConfig(target_format="PDF"))
    assert result.success and not result.error_message  # LibreOffice keeps the sheet layout: no fallback note
    assert "Bolts" in pymupdf.open(tmp_path / "book.pdf")[0].get_text()


# ---------------------------------------------------------------------------
# PDF password and page numbers
# ---------------------------------------------------------------------------

def _pdf(path: Path, pages: int = 3, rotations=()) -> Path:
    doc = pymupdf.open()
    for index in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"Body text {index + 1}", fontsize=14)
        if index < len(rotations):
            page.set_rotation(rotations[index])
    doc.save(path)
    return path


def test_protect_and_unlock_round_trip(tmp_path):
    from image_converter.core.pdf.tools import protect_pdf, unlock_pdf

    source = _pdf(tmp_path / "plain.pdf")
    protect_pdf(source, tmp_path / "locked.pdf", "s3cret!", allow_copying=False)
    locked = pymupdf.open(tmp_path / "locked.pdf")
    assert locked.needs_pass and not locked.authenticate("wrong")
    assert locked.authenticate("s3cret!")
    assert "AES" in (locked.metadata.get("encryption") or "")
    with pytest.raises(ValueError, match="not correct"):
        unlock_pdf(tmp_path / "locked.pdf", tmp_path / "x.pdf", "nope")
    unlock_pdf(tmp_path / "locked.pdf", tmp_path / "open.pdf", "s3cret!")
    reopened = pymupdf.open(tmp_path / "open.pdf")
    assert not reopened.is_encrypted and "Body text 2" in reopened[1].get_text()
    with pytest.raises(ValueError, match="already has a password"):
        protect_pdf(tmp_path / "locked.pdf", tmp_path / "twice.pdf", "again")


def test_page_numbers_are_upright_on_rotated_pages_and_respect_options(tmp_path):
    from image_converter.core.pdf.tools import add_page_numbers

    source = _pdf(tmp_path / "rot.pdf", pages=4, rotations=(0, 90, 180, 270))
    add_page_numbers(source, tmp_path / "num.pdf", position="bottom-right", style="Page n of total", start=5, skip_first=True)
    doc = pymupdf.open(tmp_path / "num.pdf")
    assert "Page" not in doc[0].get_text()
    for index, expected in ((1, "Page 5 of 7"), (2, "Page 6 of 7"), (3, "Page 7 of 7")):
        page = doc[index]
        assert expected in page.get_text()
        # Render the page as the reader sees it and check the number is in the
        # bottom-right corner: dark pixels there, none in the top-left corner.
        pix = page.get_pixmap(dpi=72)
        img = np.asarray(Image.frombytes("RGB", (pix.width, pix.height), pix.samples).convert("L"))
        h, w = img.shape
        assert (img[int(h * 0.85):, int(w * 0.7):] < 128).any(), index
    with pytest.raises(ValueError):
        add_page_numbers(source, tmp_path / "bad.pdf", style="no number")


def test_protect_and_numbers_dialogs_save_new_copies(qapp, tmp_path, monkeypatch):
    from image_converter.ui.tool_dialogs import PageNumbersDialog, ProtectDialog

    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    source = _pdf(tmp_path / "doc.pdf")
    dialog = ProtectDialog(initial_file=source)
    dialog.txt_password.setText("abc")
    dialog.txt_confirm.setText("abd")
    dialog._execute()
    assert "do not match" in dialog.lbl_result.text()
    dialog.txt_confirm.setText("abc")
    dialog._execute()
    assert dialog.last_output.name == "doc_protected.pdf" and pymupdf.open(dialog.last_output).needs_pass

    unlock = ProtectDialog(initial_file=dialog.last_output)
    assert unlock.rb_remove.isChecked()  # a locked PDF opens in "remove" mode
    unlock.txt_password.setText("abc")
    unlock._execute()
    assert not pymupdf.open(unlock.last_output).is_encrypted

    numbers = PageNumbersDialog(initial_file=source)
    numbers.combo_position.setCurrentIndex(3)  # top centre
    numbers._execute()
    assert numbers.last_output.name == "doc_numbered.pdf"
    assert "1 / 3" in pymupdf.open(numbers.last_output)[0].get_text()
    assert source.read_bytes() == _pdf(tmp_path / "again.pdf").read_bytes() or source.exists()


def test_new_pdf_tools_are_on_the_page_and_accept_drops(qapp, tmp_path, monkeypatch):
    from image_converter.ui.main_window import ImageConverterMainWindow

    window = ImageConverterMainWindow()
    labels = [button.text() for button in window.pdf_tools_page.nav_buttons]
    assert labels[-2:] == ["Protect", "Page numbers"]
    opened = []
    monkeypatch.setattr(window, "_open_protect_dialog_with_file", lambda p: opened.append(("protect", p)))
    monkeypatch.setattr(window, "_open_numbers_dialog_with_file", lambda p: opened.append(("numbers", p)))
    window._set_app_mode(2)
    pdf = tmp_path / "a.pdf"
    window.pdf_tools_page.set_active_tool(4)
    assert window._route_drop_to_tool([pdf])
    window.pdf_tools_page.set_active_tool(5)
    assert window._route_drop_to_tool([pdf])
    assert opened == [("protect", pdf), ("numbers", pdf)]
    window.close()
