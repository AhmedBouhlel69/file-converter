"""
Unit tests for Document conversions (PDF, DOCX).
"""

from pathlib import Path
import tempfile
import fitz
import docx
import pytest
from PIL import Image

from image_converter.core.engine import (
    ConversionConfig,
    ImageConverterEngine,
    get_file_metadata,
)


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def engine():
    return ImageConverterEngine()


def create_sample_pdf(path: Path, text: str = "Hello Universal File Converter") -> Path:
    """Create a simple PDF with test text."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 72), text, fontsize=14)
    doc.save(str(path))
    doc.close()
    return path


def create_sample_docx(path: Path, title: str = "Test Document", body: str = "This is a test paragraph.") -> Path:
    """Create a simple DOCX file with headings, paragraphs, and a table."""
    doc = docx.Document()
    doc.add_heading(title, level=1)
    doc.add_paragraph(body)

    # Add a 2x2 table
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Header 1"
    table.cell(0, 1).text = "Header 2"
    table.cell(1, 0).text = "Cell A"
    table.cell(1, 1).text = "Cell B"

    doc.save(str(path))
    return path


def test_pdf_metadata(temp_dir):
    pdf_path = temp_dir / "meta.pdf"
    create_sample_pdf(pdf_path, "Metadata test content")

    meta = get_file_metadata(pdf_path)
    assert meta["format"] == "PDF"
    assert meta["page_count"] == 1
    assert meta["width"] == 595
    assert meta["height"] == 842
    assert meta["file_size"] > 0


def test_docx_metadata(temp_dir):
    docx_path = temp_dir / "meta.docx"
    create_sample_docx(docx_path, "Docx Title", "Some sample body text.")

    meta = get_file_metadata(docx_path)
    assert meta["format"] == "DOCX"
    assert meta["paragraphs"] >= 1
    assert meta["tables"] == 1
    assert meta["word_count"] > 0


def test_pdf_to_png(engine, temp_dir):
    pdf_path = temp_dir / "sample.pdf"
    create_sample_pdf(pdf_path, "PDF to PNG test")
    out_img = temp_dir / "rendered.png"

    config = ConversionConfig(target_format="PNG")
    result = engine.convert_single(pdf_path, out_img, config)

    assert result.success is True
    assert out_img.is_file()
    assert out_img.stat().st_size > 0

    with Image.open(out_img) as img:
        assert img.format == "PNG"
        assert img.width > 0
        assert img.height > 0


def test_pdf_to_txt(engine, temp_dir):
    pdf_path = temp_dir / "sample.pdf"
    create_sample_pdf(pdf_path, "Unique keyword text content")
    out_txt = temp_dir / "sample.txt"

    config = ConversionConfig(target_format="TXT")
    result = engine.convert_single(pdf_path, out_txt, config)

    assert result.success is True
    assert out_txt.is_file()
    content = out_txt.read_text(encoding="utf-8")
    assert "Unique keyword text content" in content


def test_pdf_to_docx(engine, temp_dir):
    pdf_path = temp_dir / "sample.pdf"
    create_sample_pdf(pdf_path, "PDF to Word conversion test")
    out_docx = temp_dir / "sample.docx"

    config = ConversionConfig(target_format="DOCX")
    result = engine.convert_single(pdf_path, out_docx, config)

    assert result.success is True
    assert out_docx.is_file()
    assert out_docx.stat().st_size > 0

    # Verify readable with python-docx
    doc = docx.Document(str(out_docx))
    full_text = " ".join(p.text for p in doc.paragraphs)
    assert "PDF to Word" in full_text or len(doc.paragraphs) > 0


def test_docx_to_pdf(engine, temp_dir):
    docx_path = temp_dir / "sample.docx"
    create_sample_docx(docx_path, "ReportLab Fallback Test", "Paragraph inside DOCX.")
    out_pdf = temp_dir / "sample.pdf"

    config = ConversionConfig(target_format="PDF")
    result = engine.convert_single(docx_path, out_pdf, config)

    assert result.success is True
    assert out_pdf.is_file()
    assert out_pdf.stat().st_size > 0

    # Verify generated PDF is valid via PyMuPDF
    doc = fitz.open(str(out_pdf))
    assert len(doc) >= 1
    doc.close()


def test_docx_to_txt(engine, temp_dir):
    docx_path = temp_dir / "sample.docx"
    create_sample_docx(docx_path, "Text Export Test", "Body line for export.")
    out_txt = temp_dir / "exported.txt"

    config = ConversionConfig(target_format="TXT")
    result = engine.convert_single(docx_path, out_txt, config)

    assert result.success is True
    assert out_txt.is_file()
    content = out_txt.read_text(encoding="utf-8")
    assert "Text Export Test" in content
    assert "Body line for export." in content


def test_docx_to_html(engine, temp_dir):
    docx_path = temp_dir / "sample.docx"
    create_sample_docx(docx_path, "HTML Heading", "HTML Paragraph")
    out_html = temp_dir / "page.html"

    config = ConversionConfig(target_format="HTML")
    result = engine.convert_single(docx_path, out_html, config)

    assert result.success is True
    assert out_html.is_file()
    content = out_html.read_text(encoding="utf-8")
    assert "<h1>HTML Heading</h1>" in content
    assert "<p>HTML Paragraph</p>" in content
    assert "<table" in content


def test_docx_to_png_images(engine, temp_dir):
    docx_path = temp_dir / "sample.docx"
    create_sample_docx(docx_path, "Docx To Images", "Rendered through PDF.")
    out_png = temp_dir / "page.png"

    config = ConversionConfig(target_format="PNG")
    result = engine.convert_single(docx_path, out_png, config)

    assert result.success is True
    assert Path(result.output_path).is_file()
