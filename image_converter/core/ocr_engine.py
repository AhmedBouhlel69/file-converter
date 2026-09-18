"""
Optical Character Recognition (OCR) module for Universal File Converter.
Uses pytesseract and PyMuPDF to extract text from scanned PDFs and images.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Union

import fitz  # PyMuPDF
from PIL import Image

_PYTESSERACT_AVAILABLE = False
try:
    import pytesseract
    _PYTESSERACT_AVAILABLE = True
except ImportError:
    pass


def is_ocr_available() -> bool:
    """
    Check if OCR is fully operational (pytesseract library installed
    AND tesseract binary executable found on system).
    """
    if not _PYTESSERACT_AVAILABLE:
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def get_ocr_status_message() -> str:
    """Return a descriptive message explaining OCR status or setup requirements."""
    if not _PYTESSERACT_AVAILABLE:
        return "pytesseract Python library is not installed."
    try:
        ver = pytesseract.get_tesseract_version()
        return f"Tesseract OCR is available (version {ver})."
    except Exception as e:
        return (
            "pytesseract is installed, but the Tesseract OCR executable was not found on PATH. "
            "Please install Tesseract-OCR (e.g., via winget install UB-Mannheim.TesseractOCR on Windows "
            "or brew install tesseract on macOS)."
        )


def ocr_image_to_text(
    image_input: Union[Image.Image, str, Path],
    lang: str = "eng",
) -> str:
    """
    Perform OCR on a PIL Image or image file path.
    Raises RuntimeError with helpful instructions if Tesseract is not installed.
    """
    if not _PYTESSERACT_AVAILABLE:
        raise RuntimeError("pytesseract package is required for OCR.")

    try:
        if isinstance(image_input, (str, Path)):
            with Image.open(image_input) as img:
                return pytesseract.image_to_string(img, lang=lang).strip()
        else:
            return pytesseract.image_to_string(image_input, lang=lang).strip()
    except Exception as e:
        if "tesseract is not installed" in str(e).lower() or "not found" in str(e).lower():
            raise RuntimeError(
                "Tesseract OCR engine is not found on your system PATH. "
                "Please install Tesseract-OCR to use OCR text extraction."
            ) from e
        raise


def ocr_pdf_page(page: fitz.Page, dpi: int = 200, lang: str = "eng") -> str:
    """Render a single PDF page and extract text using OCR."""
    scale = dpi / 72.0
    matrix = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=matrix, alpha=False)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    return ocr_image_to_text(img, lang=lang)


def pdf_needs_ocr(doc: fitz.Document, sample_pages: int = 5) -> bool:
    """
    Inspect a PDF document to determine if it consists primarily of scanned
    (non-selectable) text that requires OCR.
    """
    pages_to_check = min(len(doc), sample_pages)
    if pages_to_check == 0:
        return False

    total_chars = 0
    for i in range(pages_to_check):
        page_text = doc[i].get_text("text").strip()
        total_chars += len(page_text)

    # If average characters per page is below threshold (e.g. less than 30 chars), likely scanned
    avg_chars = total_chars / pages_to_check
    return avg_chars < 30


def ocr_pdf_to_text(
    pdf_path: str | Path,
    lang: str = "eng",
    dpi: int = 200,
) -> str:
    """Process an entire PDF through OCR page-by-page."""
    p = Path(pdf_path)
    doc = fitz.open(str(p))
    page_texts = []

    try:
        for idx, page in enumerate(doc, 1):
            text = ocr_pdf_page(page, dpi=dpi, lang=lang)
            page_texts.append(f"--- Page {idx} (OCR) ---\n{text}\n")
    finally:
        doc.close()

    return "\n".join(page_texts)
