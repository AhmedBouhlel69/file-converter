"""Output fidelity: data, text and images must survive conversion unchanged.

Each test here reproduces a real defect found in the November 2026 audit.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageCms, ImageDraw

from image_converter.core.conversion.engine import ConversionConfig, UniversalConverterEngine


@pytest.fixture
def engine():
    return UniversalConverterEngine()


def convert(engine, source: Path, target: str, out: Path, **options):
    result = engine.convert_single(source, out, ConversionConfig(target_format=target, **options))
    assert result.success, result.error_message
    return result


# ---------------------------------------------------------------------------
# CSV and Excel
# ---------------------------------------------------------------------------

def test_semicolon_csv_with_decimal_commas_and_ansi_encoding(engine, tmp_path):
    import openpyxl

    source = tmp_path / "export.csv"
    source.write_bytes("Code;Nom;Prix;Date\n00123;Café;12,50;01/02/2024\n00456;Thé;1.234,75;15/03/2024\n".encode("cp1252"))
    convert(engine, source, "XLSX", tmp_path / "export.xlsx")
    rows = [[c.value for c in r] for r in openpyxl.load_workbook(tmp_path / "export.xlsx").active.iter_rows()]
    assert rows == [
        ["Code", "Nom", "Prix", "Date"],
        ["00123", "Café", 12.5, "01/02/2024"],
        ["00456", "Thé", 1234.75, "15/03/2024"],
    ]


def test_csv_keeps_leading_zeros_and_whole_numbers(engine, tmp_path):
    source = tmp_path / "contacts.csv"
    source.write_text("id,name,amount,phone\n1,Alice,10.5,0612345678\n2,Bob,,0698765432\n3,\"Smith, J\",7,\n", encoding="utf-8")
    convert(engine, source, "JSON", tmp_path / "contacts.json")
    records = json.loads((tmp_path / "contacts.json").read_text(encoding="utf-8"))
    assert records[0] == {"id": 1, "name": "Alice", "amount": 10.5, "phone": "0612345678"}
    assert records[1]["amount"] is None and records[2]["phone"] is None
    assert records[2]["amount"] == 7 and isinstance(records[2]["amount"], int)

    convert(engine, source, "TXT", tmp_path / "contacts.txt")
    text = (tmp_path / "contacts.txt").read_text(encoding="utf-8")
    assert "0612345678" in text and "7.0" not in text


@pytest.mark.parametrize("delimiter", ["\t", "|"])
def test_other_delimiters_are_detected(engine, tmp_path, delimiter):
    import openpyxl

    source = tmp_path / "data.csv"
    source.write_text(delimiter.join(["a", "b", "c"]) + "\n" + delimiter.join(["1", "x, y", "3"]) + "\n", encoding="utf-8")
    convert(engine, source, "XLSX", tmp_path / "data.xlsx")
    rows = [[c.value for c in r] for r in openpyxl.load_workbook(tmp_path / "data.xlsx").active.iter_rows()]
    assert rows == [["a", "b", "c"], [1, "x, y", 3]]


def test_csv_text_never_becomes_a_live_formula(engine, tmp_path):
    import openpyxl

    source = tmp_path / "evil.csv"
    source.write_text('name,note\nA,"=HYPERLINK(""http://x"",""click"")"\nB,-5\n', encoding="utf-8")
    convert(engine, source, "XLSX", tmp_path / "evil.xlsx")
    ws = openpyxl.load_workbook(tmp_path / "evil.xlsx").active
    assert ws["B2"].data_type == "s"
    assert ws["B2"].value.startswith("=HYPERLINK")
    assert ws["B3"].value == "-5"  # same column as text, so it stays text


def test_utf16_csv_with_bom(engine, tmp_path):
    source = tmp_path / "unicode.csv"
    source.write_text("ville;population\nTunis;1056247\nصفاقس;330440\n", encoding="utf-16")
    convert(engine, source, "JSON", tmp_path / "unicode.json")
    records = json.loads((tmp_path / "unicode.json").read_text(encoding="utf-8"))
    assert records == [{"ville": "Tunis", "population": 1056247}, {"ville": "صفاقس", "population": 330440}]


def _workbook(path: Path) -> Path:
    import datetime

    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sales"
    ws.append(["Date", "Product", "Qty", "Price", "Zip"])
    ws.append([datetime.date(2024, 1, 5), "Widget", 3, 9.99, "00712"])
    ws.append([datetime.datetime(2024, 1, 6, 14, 30), "Gadget", None, 1.5, "01000"])
    other = wb.create_sheet("Notes")
    other.append(["Note"])
    other.append(["Ünïcödé"])
    wb.save(path)
    return path


def test_excel_to_csv_keeps_types_and_exports_every_sheet(engine, tmp_path):
    source = _workbook(tmp_path / "book.xlsx")
    result = convert(engine, source, "CSV", tmp_path / "book.csv")
    lines = (tmp_path / "book.csv").read_text(encoding="utf-8-sig").splitlines()
    assert lines == ["Date,Product,Qty,Price,Zip", "2024-01-05,Widget,3,9.99,00712", "2024-01-06 14:30,Gadget,,1.5,01000"]
    side = tmp_path / "book - Notes.csv"
    assert side.read_text(encoding="utf-8-sig").splitlines() == ["Note", "Ünïcödé"]
    assert "Notes" in (result.error_message or "")


def test_excel_to_json_keeps_integers(engine, tmp_path):
    source = _workbook(tmp_path / "book.xlsx")
    convert(engine, source, "JSON", tmp_path / "book.json")
    data = json.loads((tmp_path / "book.json").read_text(encoding="utf-8"))
    assert data["Sales"][0] == {"Date": "2024-01-05", "Product": "Widget", "Qty": 3, "Price": 9.99, "Zip": "00712"}


def test_excel_to_pdf_without_excel_renders_tables(engine, tmp_path, monkeypatch):
    import pymupdf

    from image_converter.core.data import engine as data_engine

    def no_excel(self, *_args):
        raise data_engine._OfficeUnavailable()

    monkeypatch.setattr(data_engine.DataConverter, "_excel_com_to_pdf", no_excel)
    source = _workbook(tmp_path / "book.xlsx")
    result = convert(engine, source, "PDF", tmp_path / "book.pdf")
    text = pymupdf.open(tmp_path / "book.pdf")[0].get_text()
    assert "Widget" in text and "00712" in text and "Ünïcödé" in text
    assert "Microsoft Excel was not available" in result.error_message


def test_long_csv_to_pdf_is_not_silently_truncated(engine, tmp_path):
    import pymupdf

    source = tmp_path / "long.csv"
    source.write_text("n,label\n" + "".join(f"{i},row {i}\n" for i in range(1500)), encoding="utf-8")
    convert(engine, source, "PDF", tmp_path / "long.pdf")
    doc = pymupdf.open(tmp_path / "long.pdf")
    assert "row 1499" in doc[-1].get_text()


# ---------------------------------------------------------------------------
# Plain text
# ---------------------------------------------------------------------------

TEXT = "Résumé — café naïve façade\nPrix: €100\n\n    indented line\nمرحبا بالعالم\n中文测试\n"


@pytest.mark.parametrize("encoding", ["utf-16", "utf-8-sig", "utf-8"])
def test_text_encodings_survive_to_pdf_and_docx(engine, tmp_path, encoding):
    import docx
    import pymupdf

    source = tmp_path / "note.txt"
    source.write_text(TEXT, encoding=encoding)
    convert(engine, source, "DOCX", tmp_path / "note.docx")
    paragraphs = [p.text for p in docx.Document(str(tmp_path / "note.docx")).paragraphs]
    assert paragraphs[:6] == ["Résumé — café naïve façade", "Prix: €100", "", "    indented line", "مرحبا بالعالم", "中文测试"]

    convert(engine, source, "PDF", tmp_path / "note.pdf")
    page = pymupdf.open(tmp_path / "note.pdf")[0]
    text = page.get_text()
    assert "Résumé — café naïve façade" in text and "€100" in text
    fonts = " ".join(font[3] for font in page.get_fonts())
    # Arabic and Chinese are drawn with real fallback fonts, not missing glyphs.
    assert "Arabic" in fonts
    assert "Fallback" in fonts or "CJK" in fonts or "Han" in fonts


def test_windows_1252_text_keeps_accents(engine, tmp_path):
    source = tmp_path / "ansi.txt"
    source.write_bytes("Résumé — café naïve façade\nPrix: €100\n".encode("cp1252"))
    convert(engine, source, "HTML", tmp_path / "ansi.html")
    html_text = (tmp_path / "ansi.html").read_text(encoding="utf-8")
    assert "Résumé — café naïve façade\nPrix: €100" in html_text


def test_text_to_rtf_escapes_unicode_for_word(engine, tmp_path):
    from striprtf.striprtf import rtf_to_text

    source = tmp_path / "note.txt"
    source.write_text(TEXT, encoding="utf-8")
    convert(engine, source, "RTF", tmp_path / "note.rtf")
    raw = (tmp_path / "note.rtf").read_bytes()
    raw.decode("ascii")  # RTF must be 7-bit
    assert "Résumé — café naïve façade" in rtf_to_text(raw.decode("ascii"))
    assert "مرحبا" in rtf_to_text(raw.decode("ascii"))


def test_text_to_pptx_keeps_every_line(engine, tmp_path):
    from pptx import Presentation

    source = tmp_path / "agenda.txt"
    source.write_text("Agenda\n" + "\n".join(f"Point {i}" for i in range(1, 21)), encoding="utf-8")
    convert(engine, source, "PPTX", tmp_path / "agenda.pptx")
    text = "\n".join(
        shape.text_frame.text
        for slide in Presentation(str(tmp_path / "agenda.pptx")).slides
        for shape in slide.shapes
        if shape.has_text_frame
    )
    assert all(f"Point {i}" in text for i in range(1, 21))


def test_encoding_detection_cases():
    from image_converter.core.text_io import decode_text

    samples = {
        "cp1252": "Résumé — café naïve façade, prix €100\n",
        "cp1256": "مرحبا بالعالم، هذا نص تجريبي باللغة العربية\n",
        "cp1251": "Привет мир, это тестовый текст\n",
    }
    for encoding, text in samples.items():
        assert decode_text(text.encode(encoding))[0] == text, encoding


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

def test_16_bit_png_keeps_its_tones(engine, tmp_path):
    gradient = np.tile(np.linspace(0, 65535, 512), (64, 1)).astype(np.uint16)
    source = tmp_path / "scan16.png"
    Image.fromarray(gradient).save(source)
    for target, ext in (("JPG", "jpg"), ("WEBP", "webp"), ("GIF", "gif"), ("BMP", "bmp")):
        convert(engine, source, target, tmp_path / f"out.{ext}")
        values = np.asarray(Image.open(tmp_path / f"out.{ext}").convert("L")).astype(int)
        assert 115 < values.mean() < 140, target
        assert values[:, 0].mean() < 10 and values[:, -1].mean() > 245, target
    convert(engine, source, "PNG", tmp_path / "copy.png")
    assert Image.open(tmp_path / "copy.png").mode.startswith("I")  # still 16-bit


def test_transparent_png_to_gif_keeps_transparency(engine, tmp_path):
    source = tmp_path / "logo.png"
    image = Image.new("RGBA", (80, 60), (0, 0, 0, 0))
    ImageDraw.Draw(image).ellipse((10, 10, 70, 50), fill=(220, 30, 30, 255))
    image.save(source)
    convert(engine, source, "GIF", tmp_path / "logo.gif")
    gif = Image.open(tmp_path / "logo.gif").convert("RGBA")
    assert gif.getpixel((0, 0))[3] == 0
    assert gif.getpixel((40, 30)) == (220, 30, 30, 255)


def test_cmyk_jpeg_converts_to_gif_and_png(engine, tmp_path):
    source = tmp_path / "print.jpg"
    Image.new("RGB", (40, 30), (200, 40, 40)).convert("CMYK").save(source)
    convert(engine, source, "GIF", tmp_path / "print.gif")
    convert(engine, source, "PNG", tmp_path / "print.png")
    assert Image.open(tmp_path / "print.png").mode in ("RGB", "P")  # P = lossless palette for flat colour


def test_animation_is_kept(engine, tmp_path):
    frames = []
    for i in range(5):
        frame = Image.new("RGB", (60, 40), "white")
        ImageDraw.Draw(frame).rectangle((i * 10, 10, i * 10 + 15, 30), fill=(0, 90, 200))
        frames.append(frame)
    source = tmp_path / "spinner.gif"
    frames[0].save(source, save_all=True, append_images=frames[1:], duration=120, loop=0)
    for target, ext in (("WEBP", "webp"), ("GIF", "gif"), ("PNG", "png")):
        result = convert(engine, source, target, tmp_path / f"spin.{ext}")
        with Image.open(tmp_path / f"spin.{ext}") as out:
            assert out.n_frames == 5, target
        assert result.error_message is None
    result = convert(engine, source, "JPG", tmp_path / "still.jpg")
    assert "first of 5 frames" in result.error_message


def test_multipage_tiff_to_pdf_keeps_all_pages(engine, tmp_path):
    import pymupdf

    source = tmp_path / "fax.tiff"
    pages = [Image.new("L", (100, 140), shade) for shade in (30, 120, 220)]
    pages[0].save(source, save_all=True, append_images=pages[1:])
    convert(engine, source, "PDF", tmp_path / "fax.pdf")
    assert len(pymupdf.open(tmp_path / "fax.pdf")) == 3


def test_colour_profile_is_kept(engine, tmp_path):
    srgb = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    source = tmp_path / "photo.jpg"
    Image.new("RGB", (32, 32), (10, 120, 200)).save(source, icc_profile=srgb)
    for target, ext in (("PNG", "png"), ("WEBP", "webp"), ("JPG", "jpeg"), ("TIFF", "tiff")):
        convert(engine, source, target, tmp_path / f"photo_out.{ext}")
        assert Image.open(tmp_path / f"photo_out.{ext}").info.get("icc_profile") == srgb, target


def test_cmyk_profile_is_used_for_conversion(engine, tmp_path):
    candidates = [
        Path("/usr/share/texlive/texmf-dist/tex/generic/colorprofiles/FOGRA39L_coated.icc"),
        Path(r"C:\Windows\System32\spool\drivers\color\RSWOP.icm"),
    ]
    profile = next((p for p in candidates if p.is_file()), None)
    if profile is None:
        pytest.skip("no CMYK ICC profile on this machine")
    cmyk = Image.new("CMYK", (16, 16), (0, 100, 255, 0))
    source = tmp_path / "press.jpg"
    cmyk.save(source, icc_profile=profile.read_bytes())
    convert(engine, source, "PNG", tmp_path / "press.png")
    managed = Image.open(tmp_path / "press.png").convert("RGB").getpixel((8, 8))
    expected = ImageCms.profileToProfile(cmyk, str(profile), ImageCms.createProfile("sRGB"), outputMode="RGB").getpixel((8, 8))
    assert max(abs(a - b) for a, b in zip(managed, expected)) <= 2
    assert Image.open(tmp_path / "press.png").info.get("icc_profile") is None


def test_high_quality_jpeg_from_png_uses_full_colour_resolution(engine, tmp_path):
    from PIL import JpegImagePlugin

    source = tmp_path / "screenshot.png"
    Image.new("RGB", (64, 64), (255, 0, 0)).save(source)
    convert(engine, source, "JPG", tmp_path / "hi.jpg", quality=92)
    convert(engine, source, "JPG", tmp_path / "lo.jpg", quality=70)
    assert JpegImagePlugin.get_sampling(Image.open(tmp_path / "hi.jpg")) == 0
    assert JpegImagePlugin.get_sampling(Image.open(tmp_path / "lo.jpg")) == 2


# ---------------------------------------------------------------------------
# Word and PDF text
# ---------------------------------------------------------------------------

def _report(path: Path) -> Path:
    import docx
    from docx.shared import Inches

    picture = path.with_name("pic.png")
    Image.new("RGB", (20, 10), "navy").save(picture)
    d = docx.Document()
    d.add_heading("Quarterly Report", 0)
    p = d.add_paragraph("Revenue grew ")
    p.add_run("12 percent").bold = True
    d.add_paragraph("First bullet", style="List Bullet")
    d.add_paragraph("Second bullet", style="List Bullet")
    d.add_paragraph("Step one", style="List Number")
    d.add_paragraph("Step two", style="List Number")
    d.add_paragraph("Before the table.")
    table = d.add_table(rows=3, cols=3)
    for i, row in enumerate([["Region", "Q1", "Q2"], ["North", "10", "12"], ["South", "8", "9"]]):
        for j, value in enumerate(row):
            table.cell(i, j).text = value
    table.cell(2, 1).merge(table.cell(2, 2))
    d.add_paragraph("After the table.")
    d.add_picture(str(picture), width=Inches(1))
    d.save(path)
    return path


def test_docx_to_text_keeps_reading_order_lists_and_merged_cells(engine, tmp_path):
    source = _report(tmp_path / "report.docx")
    convert(engine, source, "TXT", tmp_path / "report.txt")
    text = (tmp_path / "report.txt").read_text(encoding="utf-8")
    assert text.index("Before the table.") < text.index("Region\tQ1\tQ2") < text.index("After the table.")
    assert "• First bullet\n• Second bullet\n1. Step one\n2. Step two" in text
    south = next(line for line in text.splitlines() if line.startswith("South"))
    assert south.count("8") == 1  # merged cell is not duplicated


def test_docx_to_html_keeps_structure(engine, tmp_path):
    source = _report(tmp_path / "report.docx")
    convert(engine, source, "HTML", tmp_path / "report.html")
    html_text = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "<h1>Quarterly Report</h1>" in html_text
    assert "<strong>12 percent</strong>" in html_text
    assert "<ul><li>" in html_text and "<ol><li>" in html_text
    assert 'colspan="2"' in html_text
    assert 'src="data:image/png;base64,' in html_text
    assert html_text.index("Before the table.") < html_text.index("<table>") < html_text.index("After the table.")


def test_pdf_to_text_joins_list_markers(engine, tmp_path):
    import pymupdf

    source = tmp_path / "list.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "\u2022", fontsize=11)
    page.insert_text((90, 72), "First item", fontsize=11)
    page.insert_text((72, 90), "1.", fontsize=11)
    page.insert_text((150, 90), "Numbered item", fontsize=11)
    doc.save(source)
    convert(engine, source, "TXT", tmp_path / "list.txt")
    text = (tmp_path / "list.txt").read_text(encoding="utf-8")
    import re

    assert re.search(r"^[•·] First item$", text, re.M), text


def test_scanned_pdf_to_text_explains_missing_ocr(engine, tmp_path, monkeypatch):
    import pymupdf

    from image_converter.core import ocr_engine

    monkeypatch.setattr(ocr_engine, "is_ocr_available", lambda: False)
    source = tmp_path / "scan.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    picture = Image.new("RGB", (200, 100), "white")
    buf = io.BytesIO()
    picture.save(buf, "PNG")
    page.insert_image(page.rect, stream=buf.getvalue())
    doc.save(source)
    result = engine.convert_single(source, tmp_path / "scan.txt", ConversionConfig(target_format="TXT"))
    assert not result.success
    assert "looks like a scan" in result.error_message and "Tesseract" in result.error_message


def test_image_without_text_says_so(engine, tmp_path):
    from image_converter.core.ocr.engine import is_ocr_available

    if not is_ocr_available():
        pytest.skip("Tesseract is not installed")
    source = tmp_path / "sky.png"
    Image.new("RGB", (300, 200), (120, 170, 230)).save(source)
    result = engine.convert_single(source, tmp_path / "sky.txt", ConversionConfig(target_format="TXT"))
    assert not result.success and "No text was found" in result.error_message


def test_ocr_preparation_handles_odd_images():
    from image_converter.core.ocr.engine import _prepare_for_ocr

    sixteen = Image.fromarray(np.full((50, 80), 40000, dtype=np.uint16))
    assert _prepare_for_ocr(sixteen).mode == "L"
    rgba = Image.new("RGBA", (300, 100), (0, 0, 0, 0))
    prepared = _prepare_for_ocr(rgba)
    assert prepared.mode == "L" and prepared.size == (900, 300)  # small crops are upscaled
    assert prepared.getpixel((0, 0)) == 255  # transparent becomes white paper


def test_tesseract_found_from_environment(monkeypatch, tmp_path):
    from image_converter.core.ocr import engine as ocr_engine

    if not ocr_engine._PYTESSERACT_AVAILABLE:
        pytest.skip("pytesseract not installed")
    fake = tmp_path / "tesseract.exe"
    fake.write_bytes(b"")
    monkeypatch.setenv("TESSERACT_CMD", str(fake))
    monkeypatch.setattr(ocr_engine, "_TESSERACT_CHECKED", False)
    original = ocr_engine.pytesseract.pytesseract.tesseract_cmd
    try:
        ocr_engine._locate_tesseract()
        assert ocr_engine.pytesseract.pytesseract.tesseract_cmd == str(fake)
    finally:
        ocr_engine.pytesseract.pytesseract.tesseract_cmd = original
        ocr_engine._TESSERACT_CHECKED = False
