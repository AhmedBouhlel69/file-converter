"""
Unit tests for OCR engine, fallback detection, and status reporting.
"""

from pathlib import Path
from unittest.mock import patch
import fitz
from PIL import Image
import pytest

from image_converter.core.ocr_engine import (
    is_ocr_available,
    get_ocr_status_message,
    pdf_needs_ocr,
    ocr_image_to_text,
)


def test_ocr_status_reporting():
    status = get_ocr_status_message()
    assert isinstance(status, str)
    assert len(status) > 0


def test_pdf_needs_ocr_detection(tmp_path: Path):
    # 1. Normal PDF with selectable text
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "This is a document with full selectable text content.")
    assert pdf_needs_ocr(doc) is False
    doc.close()

    # 2. PDF with only an image (no selectable text)
    doc_scanned = fitz.open()
    page_img = doc_scanned.new_page()
    # No insert_text!
    assert pdf_needs_ocr(doc_scanned) is True
    doc_scanned.close()


def test_ocr_mocked_execution(tmp_path: Path):
    # Test OCR workflow with mocked pytesseract to ensure clean fallback behavior
    sample_img = tmp_path / "scan.png"
    Image.new("RGB", (100, 100), color="white").save(sample_img)

    with patch("pytesseract.image_to_string", return_value="Recognized Text Line 1"):
        text = ocr_image_to_text(sample_img)
        assert text == "Recognized Text Line 1"
