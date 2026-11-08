"""
Optical Character Recognition (OCR) module for Universal File Converter.
Uses pytesseract and PyMuPDF to extract text from scanned PDFs and images.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Optional, Union

import fitz  # PyMuPDF
from PIL import Image

logger = logging.getLogger(__name__)

_PYTESSERACT_AVAILABLE = False
try:
    import pytesseract
    _PYTESSERACT_AVAILABLE = True
except ImportError:
    pass

_TESSERACT_CHECKED = False
_EXTRA_LANGUAGES = ("fra", "ara", "deu", "spa", "ita", "por", "nld")


def _windows_tesseract_candidates():
    roots = [
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs"),
        os.environ.get("LOCALAPPDATA", ""),
    ]
    for root in roots:
        if root:
            yield Path(root) / "Tesseract-OCR" / "tesseract.exe"


def _locate_tesseract() -> None:
    """Point pytesseract at Tesseract when it is installed but not on PATH.

    The common Windows installer puts Tesseract in Program Files without adding
    it to PATH, which used to make OCR look unavailable.
    """
    global _TESSERACT_CHECKED
    if _TESSERACT_CHECKED or not _PYTESSERACT_AVAILABLE:
        return
    _TESSERACT_CHECKED = True
    configured = os.environ.get("TESSERACT_CMD")
    if configured and Path(configured).is_file():
        pytesseract.pytesseract.tesseract_cmd = configured
        return
    if shutil.which(pytesseract.pytesseract.tesseract_cmd):
        return
    if os.name == "nt":
        for candidate in _windows_tesseract_candidates():
            if candidate.is_file():
                pytesseract.pytesseract.tesseract_cmd = str(candidate)
                return


def is_ocr_available() -> bool:
    """
    Check if OCR is fully operational (pytesseract library installed
    AND tesseract binary executable found on system).
    """
    if not _PYTESSERACT_AVAILABLE:
        return False
    _locate_tesseract()
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception as e:
        logger.debug(f"Tesseract version check failed: {e}")
        return False


def get_ocr_status_message() -> str:
    """Return a descriptive message explaining OCR status or setup requirements."""
    if not _PYTESSERACT_AVAILABLE:
        return "pytesseract Python library is not installed."
    _locate_tesseract()
    try:
        ver = pytesseract.get_tesseract_version()
        return f"Tesseract OCR is available (version {ver})."
    except Exception as e:
        logger.info(f"Tesseract executable not found on PATH: {e}")
        return (
            "pytesseract is installed, but the Tesseract OCR executable was not found. "
            "Please install Tesseract-OCR (e.g., via winget install UB-Mannheim.TesseractOCR on Windows "
            "or brew install tesseract on macOS), or set TESSERACT_CMD to tesseract.exe."
        )


_LANG_CACHE: Optional[str] = None


def resolve_languages(lang: Optional[str]) -> str:
    """Turn "auto" into English plus up to two other installed languages."""
    global _LANG_CACHE
    if lang and lang.lower() != "auto":
        return lang
    if _LANG_CACHE is not None:
        return _LANG_CACHE
    chosen = ["eng"]
    try:
        installed = set(pytesseract.get_languages(config=""))
        if "eng" not in installed and installed - {"osd"}:
            chosen = []
        for code in _EXTRA_LANGUAGES:
            if code in installed and len(chosen) < 3:
                chosen.append(code)
        if not chosen:
            chosen = sorted(installed - {"osd"})[:1] or ["eng"]
    except Exception as exc:
        logger.debug("Could not list Tesseract languages: %s", exc)
    _LANG_CACHE = "+".join(chosen)
    return _LANG_CACHE


def _prepare_for_ocr(image: Image.Image) -> Image.Image:
    """Upright, greyscale, and large enough for Tesseract's character models."""
    from PIL import ImageOps

    try:
        image = ImageOps.exif_transpose(image) or image
    except Exception:
        pass
    if image.mode in ("RGBA", "LA", "PA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        canvas = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        image = Image.alpha_composite(canvas, rgba)
    if image.mode.startswith("I;16") or image.mode in ("I", "F"):
        from image_converter.core.conversion.engine import _to_8bit
        image = _to_8bit(image)
    gray = image.convert("L")
    # Small screenshots and phone crops OCR much better when upscaled.
    longest = max(gray.size)
    if longest and longest < 1500:
        factor = min(3.0, 1500 / longest)
        gray = gray.resize((round(gray.width * factor), round(gray.height * factor)), Image.Resampling.LANCZOS)
    return gray


def ocr_image_to_text(
    image_input: Union[Image.Image, str, Path],
    lang: str = "auto",
) -> str:
    """
    Perform OCR on a PIL Image or image file path.
    Raises RuntimeError with helpful instructions if Tesseract is not installed.
    """
    if not _PYTESSERACT_AVAILABLE:
        raise RuntimeError("pytesseract package is required for OCR.")
    _locate_tesseract()

    try:
        if isinstance(image_input, (str, Path)):
            with Image.open(image_input) as img:
                img.load()
                prepared = _prepare_for_ocr(img)
        else:
            prepared = _prepare_for_ocr(image_input)
        return pytesseract.image_to_string(prepared, lang=resolve_languages(lang)).strip()
    except Exception as e:
        if "tesseract is not installed" in str(e).lower() or "not found" in str(e).lower():
            raise RuntimeError(
                "Tesseract OCR engine is not found on your system PATH. "
                "Please install Tesseract-OCR to use OCR text extraction."
            ) from e
        raise


def ocr_pdf_page(page: fitz.Page, dpi: int = 300, lang: str = "auto") -> str:
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
    lang: str = "auto",
    dpi: int = 300,
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
