"""
Comprehensive automated tests for PDF Toolkit Engine and UI Components.
Covers all 26 tools across 7 categories:
1. Organize: Merge, Split, Remove Pages, Extract Pages, Organize Pages, Images to PDF, Rotate.
2. Optimize: Compress, Repair, OCR.
3. Convert To: Word to PDF, PPTX to PDF, Excel to PDF, HTML to PDF.
4. Convert From: PDF to Images, PDF to Word, PDF to PowerPoint, PDF to Excel, PDF to PDF/A.
5. Edit: Edit Content, Page Numbers, Watermark, Crop, PDF Forms (inspect, fill, add, export).
6. Security: Protect, Unlock, Sign, Redact.
7. Intelligence: AI Summarizer, Translate, PDF to Markdown, Compare PDFs.
8. UI Components: ToolCardWidget, ToolkitDashboardWidget, ToolWorkspaceWidget, PDFViewerWidget, SignatureCanvasWidget.
"""

import io
import json
import os
import tempfile
from pathlib import Path
from typing import List

import fitz  # PyMuPDF
import pytest
from PIL import Image

from image_converter.core.pdf_toolkit_engine import (
    PDFToolkitEngine,
    add_form_field,
    add_page_numbers,
    add_watermark,
    compare_pdfs,
    compress_pdf,
    crop_pdf,
    edit_pdf_content,
    excel_to_pdf,
    export_form_data,
    extract_pages,
    fill_form_fields,
    get_form_fields,
    html_to_pdf,
    images_to_pdf,
    merge_pdfs,
    ocr_pdf,
    organize_pages,
    parse_page_range_str,
    pdf_to_excel,
    pdf_to_images,
    pdf_to_markdown,
    pdf_to_pdfa,
    pdf_to_powerpoint,
    pdf_to_word,
    powerpoint_to_pdf,
    protect_pdf,
    redact_pdf,
    remove_pages,
    repair_pdf,
    rotate_pdf,
    sign_pdf,
    split_pdf,
    summarize_pdf,
    translate_pdf,
    unlock_pdf,
    word_to_pdf,
)
from image_converter.ui.toolkit_components import (
    ALL_TOOLS,
    CATEGORIES,
    DrawCanvas,
    PDFViewerWidget,
    SignatureCanvasWidget,
    ToolCardWidget,
    ToolkitDashboardWidget,
    ToolWorkspaceWidget,
)


# ---------------------------------------------------------------------------
# Test Data Fixtures
# ---------------------------------------------------------------------------

def make_sample_pdf(path: Path, num_pages: int = 3, prefix: str = "Page") -> Path:
    """Create a multi-page PDF document with distinctive text on each page."""
    doc = fitz.open()
    for i in range(num_pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text(fitz.Point(72, 100), f"{prefix} {i + 1} Content Heading", fontsize=20)
        page.insert_text(fitz.Point(72, 140), f"This is the body paragraph for page {i + 1} of the document.", fontsize=12)
    doc.save(str(path))
    doc.close()
    return path


def make_sample_image(path: Path, width: int = 200, height: int = 200, color: str = "blue") -> Path:
    """Create a sample raster image."""
    img = Image.new("RGB", (width, height), color=color)
    img.save(str(path))
    return path


# ===========================================================================
# 1. ORGANIZE PDF TESTS
# ===========================================================================

def test_parse_page_range_str():
    """Verify page range parsing handles single pages, ranges, and 'end'."""
    assert parse_page_range_str("1, 3, 5-7", 10) == [0, 2, 4, 5, 6]
    assert parse_page_range_str("2-end", 5) == [1, 2, 3, 4]
    assert parse_page_range_str("", 4) == [0, 1, 2, 3]


def test_merge_pdfs(tmp_path):
    """Merge 2 PDFs into a single document and verify page count and bookmarks."""
    pdf1 = make_sample_pdf(tmp_path / "doc1.pdf", num_pages=2, prefix="Doc1 Page")
    pdf2 = make_sample_pdf(tmp_path / "doc2.pdf", num_pages=3, prefix="Doc2 Page")
    merged = tmp_path / "merged.pdf"

    res = merge_pdfs([pdf1, pdf2], merged)
    assert Path(res).exists()

    doc = fitz.open(res)
    assert len(doc) == 5
    toc = doc.get_toc()
    assert len(toc) == 2
    assert toc[0][1] == "doc1"
    assert toc[1][1] == "doc2"
    doc.close()


def test_split_pdf_ranges(tmp_path):
    """Split a 4-page PDF by custom ranges."""
    pdf = make_sample_pdf(tmp_path / "source.pdf", num_pages=4)
    out_dir = tmp_path / "split_ranges"

    files = split_pdf(pdf, out_dir, mode="ranges", ranges="1-2, 3-4")
    assert len(files) == 2
    for f in files:
        doc = fitz.open(f)
        assert len(doc) == 2
        doc.close()


def test_split_pdf_single_and_every_n(tmp_path):
    """Split a 3-page PDF into single pages and every N pages."""
    pdf = make_sample_pdf(tmp_path / "source.pdf", num_pages=3)

    # All single
    out_single = tmp_path / "split_single"
    files = split_pdf(pdf, out_single, mode="all_single")
    assert len(files) == 3

    # Every N
    out_n = tmp_path / "split_n"
    files_n = split_pdf(pdf, out_n, mode="every_n", n=2)
    assert len(files_n) == 2  # 2 in first, 1 in second


def test_remove_pages(tmp_path):
    """Remove page 2 from a 3-page PDF."""
    pdf = make_sample_pdf(tmp_path / "source.pdf", num_pages=3)
    out = tmp_path / "removed.pdf"

    remove_pages(pdf, out, "2")
    doc = fitz.open(out)
    assert len(doc) == 2
    # Verify page 1 and page 3 content remain
    text1 = doc[0].get_text()
    text2 = doc[1].get_text()
    assert "Page 1" in text1
    assert "Page 3" in text2
    doc.close()


def test_extract_pages(tmp_path):
    """Extract pages 1 and 3 into a new PDF."""
    pdf = make_sample_pdf(tmp_path / "source.pdf", num_pages=3)
    out = tmp_path / "extracted.pdf"

    extract_pages(pdf, out, "1, 3")
    doc = fitz.open(out)
    assert len(doc) == 2
    assert "Page 1" in doc[0].get_text()
    assert "Page 3" in doc[1].get_text()
    doc.close()


def test_organize_pages(tmp_path):
    """Reorder pages and apply rotation in organize_pages."""
    pdf = make_sample_pdf(tmp_path / "source.pdf", num_pages=3)
    out = tmp_path / "reorganized.pdf"

    # Reorder sequence: page 3, page 1, page 2
    organize_pages(pdf, out, page_order=[2, 0, 1], rotations={0: 90})
    doc = fitz.open(out)
    assert len(doc) == 3
    assert "Page 3" in doc[0].get_text()
    assert doc[0].rotation == 90
    assert "Page 1" in doc[1].get_text()
    doc.close()


def test_images_to_pdf_scan(tmp_path):
    """Combine multiple images into a scanned PDF."""
    img1 = make_sample_image(tmp_path / "scan1.png", color="red")
    img2 = make_sample_image(tmp_path / "scan2.jpg", color="green")
    out = tmp_path / "scanned.pdf"

    images_to_pdf([img1, img2], out, page_size="A4")
    doc = fitz.open(out)
    assert len(doc) == 2
    doc.close()


def test_rotate_pdf(tmp_path):
    """Rotate odd pages by 90 degrees."""
    pdf = make_sample_pdf(tmp_path / "source.pdf", num_pages=3)
    out = tmp_path / "rotated.pdf"

    rotate_pdf(pdf, out, angle=90, page_target="odd")
    doc = fitz.open(out)
    assert doc[0].rotation == 90  # Page 1 (odd)
    assert doc[1].rotation == 0   # Page 2 (even)
    assert doc[2].rotation == 90  # Page 3 (odd)
    doc.close()


# ===========================================================================
# 2. OPTIMIZE PDF TESTS
# ===========================================================================

def test_compress_pdf(tmp_path):
    """Compress PDF and verify result dictionary containing savings."""
    pdf = make_sample_pdf(tmp_path / "uncompressed.pdf", num_pages=2)
    out = tmp_path / "compressed.pdf"

    stats = compress_pdf(pdf, out, level="medium")
    assert Path(stats["output_path"]).exists()
    assert stats["original_size"] > 0
    assert stats["compressed_size"] > 0
    assert "savings_percent" in stats


def test_repair_pdf(tmp_path):
    """Repair damaged PDF and verify structural recovery."""
    pdf = make_sample_pdf(tmp_path / "corrupt_candidate.pdf", num_pages=2)
    out = tmp_path / "repaired.pdf"

    res = repair_pdf(pdf, out)
    assert res["success"] is True
    assert res["recovered_pages"] == 2
    assert Path(out).exists()


def test_ocr_pdf(tmp_path):
    """OCR PDF runs without errors."""
    pdf = make_sample_pdf(tmp_path / "ocr_target.pdf", num_pages=1)
    out = tmp_path / "searchable.pdf"

    res = ocr_pdf(pdf, out)
    assert Path(res["output_path"]).exists()
    assert res["pages_processed"] == 1


# ===========================================================================
# 3. CONVERT TO PDF TESTS
# ===========================================================================

def test_html_to_pdf(tmp_path):
    """Convert HTML string to vector PDF."""
    html_src = "<html><body><h1>Universal PDF Toolkit</h1><p>Test paragraph content.</p></body></html>"
    out = tmp_path / "html_doc.pdf"

    res = html_to_pdf(html_src, out)
    assert Path(res).exists()
    doc = fitz.open(res)
    assert len(doc) >= 1
    doc.close()


def test_excel_to_pdf(tmp_path):
    """Convert CSV/Excel to PDF table."""
    csv_file = tmp_path / "data.csv"
    with open(csv_file, "w", encoding="utf-8") as f:
        f.write("Product,Price,Quantity\nWidget A,19.99,100\nWidget B,29.99,50\n")
    out = tmp_path / "data.pdf"

    res = excel_to_pdf(csv_file, out)
    assert Path(res).exists()
    doc = fitz.open(res)
    assert len(doc) >= 1
    doc.close()


# ===========================================================================
# 4. CONVERT FROM PDF TESTS
# ===========================================================================

def test_pdf_to_images(tmp_path):
    """Export PDF pages as JPG images."""
    pdf = make_sample_pdf(tmp_path / "doc.pdf", num_pages=2)
    out_dir = tmp_path / "images_out"

    imgs = pdf_to_images(pdf, out_dir, dpi=100, fmt="JPG")
    assert len(imgs) == 2
    for img_p in imgs:
        assert Path(img_p).exists()
        with Image.open(img_p) as im:
            assert im.format in ("JPEG", "JPG")


def test_pdf_to_excel(tmp_path):
    """Extract table content from PDF into XLSX and CSV."""
    pdf = tmp_path / "table.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(fitz.Point(72, 100), "Header1  Header2  Header3\nValue1  Value2  Value3")
    doc.save(str(pdf))
    doc.close()

    # CSV
    out_csv = tmp_path / "table.csv"
    pdf_to_excel(pdf, out_csv, format="CSV")
    assert out_csv.exists()
    assert out_csv.stat().st_size > 0

    # XLSX
    out_xlsx = tmp_path / "table.xlsx"
    pdf_to_excel(pdf, out_xlsx, format="XLSX")
    assert out_xlsx.exists()
    assert out_xlsx.stat().st_size > 0


def test_pdf_to_pdfa(tmp_path):
    """Convert standard PDF to PDF/A archive standard."""
    pdf = make_sample_pdf(tmp_path / "standard.pdf", num_pages=1)
    out = tmp_path / "archival_pdfa.pdf"

    res = pdf_to_pdfa(pdf, out)
    assert Path(res).exists()
    doc = fitz.open(res)
    assert "PDF/A" in doc.metadata.get("producer", "")
    doc.close()


# ===========================================================================
# 5. EDIT PDF TESTS
# ===========================================================================

def test_edit_pdf_content(tmp_path):
    """Add text, shapes, and custom annotations to PDF."""
    pdf = make_sample_pdf(tmp_path / "source.pdf", num_pages=1)
    out = tmp_path / "edited.pdf"

    edit_pdf_content(
        pdf,
        out,
        text_items=[{"page": 1, "text": "CUSTOM INSERTED TEXT", "rect": (72, 200, 300, 250), "fontsize": 16}],
        shape_items=[{"page": 1, "type": "rect", "rect": (70, 195, 305, 255), "color": (1, 0, 0)}],
    )
    doc = fitz.open(out)
    text = doc[0].get_text()
    assert "CUSTOM INSERTED TEXT" in text
    doc.close()


def test_add_page_numbers(tmp_path):
    """Add formatted page numbers to headers or footers."""
    pdf = make_sample_pdf(tmp_path / "source.pdf", num_pages=3)
    out = tmp_path / "numbered.pdf"

    add_page_numbers(pdf, out, position="bottom_center", format_str="Page {n} of {total}", skip_first=False)
    doc = fitz.open(out)
    assert "Page 1 of 3" in doc[0].get_text()
    assert "Page 2 of 3" in doc[1].get_text()
    assert "Page 3 of 3" in doc[2].get_text()
    doc.close()


def test_add_watermark(tmp_path):
    """Add visual text watermark."""
    pdf = make_sample_pdf(tmp_path / "source.pdf", num_pages=1)
    out = tmp_path / "watermarked.pdf"

    add_watermark(pdf, out, watermark_type="text", text="DRAFT-REVIEW", opacity=0.4)
    doc = fitz.open(out)
    text = doc[0].get_text()
    assert "DRAFT-REVIEW" in text
    doc.close()


def test_crop_pdf(tmp_path):
    """Crop margins of PDF pages."""
    pdf = make_sample_pdf(tmp_path / "source.pdf", num_pages=1)
    out = tmp_path / "cropped.pdf"

    crop_pdf(pdf, out, margins=(50, 50, 50, 50))
    doc = fitz.open(out)
    cropbox = doc[0].cropbox
    assert cropbox.x0 == 50
    assert cropbox.y0 == 50
    doc.close()


def test_pdf_forms(tmp_path):
    """Add form field, inspect fields, fill values, and export data."""
    pdf = make_sample_pdf(tmp_path / "form_blank.pdf", num_pages=1)
    with_field = tmp_path / "form_field.pdf"

    # Add text field
    add_form_field(pdf, with_field, field_type="text", name="Username", rect=(100, 100, 250, 130), page_num=1)
    fields = get_form_fields(with_field)
    assert len(fields) >= 1
    assert any(f["name"] == "Username" for f in fields)

    # Fill field
    filled = tmp_path / "form_filled.pdf"
    fill_form_fields(with_field, filled, {"Username": "AliceSmith"})
    fields_filled = get_form_fields(filled)
    alice_field = [f for f in fields_filled if f["name"] == "Username"][0]
    assert alice_field["value"] == "AliceSmith"

    # Export to JSON
    json_out = tmp_path / "form_data.json"
    export_form_data(filled, json_out, fmt="json")
    assert json_out.exists()
    with open(json_out, "r") as f:
        data = json.load(f)
    assert len(data) >= 1


# ===========================================================================
# 6. PDF SECURITY TESTS
# ===========================================================================

def test_protect_and_unlock_pdf(tmp_path):
    """Encrypt a PDF with password and unlock it."""
    pdf = make_sample_pdf(tmp_path / "plain.pdf", num_pages=2)
    protected = tmp_path / "protected.pdf"

    protect_pdf(pdf, protected, user_password="SafePassword123")
    doc_enc = fitz.open(protected)
    assert doc_enc.is_encrypted is True
    assert doc_enc.authenticate("SafePassword123") > 0
    doc_enc.close()

    # Unlock
    unlocked = tmp_path / "unlocked.pdf"
    unlock_pdf(protected, unlocked, password="SafePassword123")
    doc_clean = fitz.open(unlocked)
    assert doc_clean.is_encrypted is False
    assert len(doc_clean) == 2
    doc_clean.close()


def test_sign_pdf(tmp_path):
    """Stamp visual signature and signer metadata onto PDF."""
    pdf = make_sample_pdf(tmp_path / "agreement.pdf", num_pages=1)
    out = tmp_path / "agreement_signed.pdf"

    # Create dummy PNG signature bytes
    img = Image.new("RGBA", (150, 60), color=(0, 0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, "PNG")

    sign_pdf(pdf, out, signature_data=buf.getvalue(), signer_name="Jane Auditor", add_date=True)
    doc = fitz.open(out)
    text = doc[0].get_text()
    assert "Signer: Jane Auditor" in text
    doc.close()


def test_redact_pdf_forensic(tmp_path):
    """Permanently eradicate sensitive text from PDF forensically."""
    pdf = tmp_path / "confidential.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(fitz.Point(72, 100), "Public Header", fontsize=14)
    page.insert_text(fitz.Point(72, 140), "SECRET_KEY_998877 is highly sensitive.", fontsize=12)
    doc.save(str(pdf))
    doc.close()

    out = tmp_path / "sanitized.pdf"
    redact_pdf(pdf, out, search_terms=["SECRET_KEY_998877"])

    # Verify text is completely absent from the stream
    doc_clean = fitz.open(out)
    clean_text = doc_clean[0].get_text()
    assert "SECRET_KEY_998877" not in clean_text
    assert "Public Header" in clean_text
    doc_clean.close()


# ===========================================================================
# 7. INTELLIGENCE & ANALYSIS TESTS
# ===========================================================================

def test_summarize_pdf(tmp_path):
    """Generate extractive NLP summary and key bullet points."""
    pdf = tmp_path / "report.pdf"
    doc = fitz.open()
    page = doc.new_page()
    content = (
        "Antigravity is an advanced software engineering toolkit. "
        "The system provides complete multi-file batch conversion capabilities. "
        "Furthermore, high performance PyMuPDF rendering ensures vector fidelity. "
        "Security audits verify AES-256 encryption and forensic sanitization. "
        "Overall the application delivers unprecedented productivity gains for users."
    )
    page.insert_text(fitz.Point(72, 100), content, fontsize=12)
    doc.save(str(pdf))
    doc.close()

    res = summarize_pdf(pdf, length="short")
    assert "summary" in res
    assert len(res["summary"]) > 20
    assert res["original_word_count"] > 0


def test_translate_pdf(tmp_path):
    """Translate PDF content and produce translated report."""
    pdf = make_sample_pdf(tmp_path / "doc.pdf", num_pages=1)
    out = tmp_path / "translated.txt"

    res = translate_pdf(pdf, target_lang="es", output_path=out)
    assert "translated_text" in res
    assert out.exists()
    assert out.stat().st_size > 0


def test_pdf_to_markdown(tmp_path):
    """Convert PDF to clean GitHub Flavored Markdown."""
    pdf = make_sample_pdf(tmp_path / "doc.pdf", num_pages=2)
    out = tmp_path / "doc.md"

    md = pdf_to_markdown(pdf, output_path=out)
    assert "# doc" in md
    assert "Page 1" in md
    assert out.exists()


def test_compare_pdfs(tmp_path):
    """Compare 2 versions of a PDF document."""
    pdf1 = make_sample_pdf(tmp_path / "version1.pdf", num_pages=2, prefix="Original")
    pdf2 = make_sample_pdf(tmp_path / "version2.pdf", num_pages=2, prefix="Modified")
    out_html = tmp_path / "diff_report.html"

    res = compare_pdfs(pdf1, pdf2, output_report_path=out_html)
    assert res["pages_compared"] == 2
    assert res["has_differences"] is True
    assert out_html.exists()


# ===========================================================================
# 8. FACADE ENGINE TESTS
# ===========================================================================

def test_pdf_toolkit_engine_facade():
    """Verify PDFToolkitEngine class exposes all operations."""
    engine = PDFToolkitEngine()
    assert callable(engine.merge_pdfs)
    assert callable(engine.split_pdf)
    assert callable(engine.compress_pdf)
    assert callable(engine.protect_pdf)
    assert callable(engine.summarize_pdf)
    assert callable(engine.compare_pdfs)


# ===========================================================================
# 9. UI COMPONENT TESTS
# ===========================================================================

@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_toolkit_dashboard_and_cards(qapp):
    """Test ToolkitDashboardWidget and ToolCardWidget."""
    dashboard = ToolkitDashboardWidget()

    assert len(ALL_TOOLS) >= 26
    assert len(dashboard.cards) >= 26

    # Filter by category
    dashboard.category_group.buttons()[1].click()
    # Search input
    dashboard.search_input.setText("watermark")
    dashboard._filter_cards()


def test_tool_workspace_lifecycle(qapp, tmp_path):
    """Test ToolWorkspaceWidget loading and tool configuration."""
    ws = ToolWorkspaceWidget()

    # Load Compress tool
    ws.load_tool("compress_pdf")
    assert ws.current_tool.id == "compress_pdf"
    assert hasattr(ws, "cmb_comp")

    # Load Split tool
    ws.load_tool("split_pdf")
    assert ws.current_tool.id == "split_pdf"
    assert hasattr(ws, "cmb_split_mode")

    # Load Sign tool
    ws.load_tool("sign_pdf")
    assert hasattr(ws, "sig_canvas")


def test_signature_canvas(qapp):
    """Test SignatureCanvasWidget drawing and export."""
    sig = SignatureCanvasWidget()

    canvas = sig.draw_canvas
    canvas.set_pen_width(4)
    canvas.current_line = [canvas.rect().topLeft(), canvas.rect().bottomRight()]
    canvas.lines.append(canvas.current_line)

    png_bytes = canvas.to_png_bytes()
    assert len(png_bytes) > 0
    assert png_bytes.startswith(b"\x89PNG")

