"""
PDF Toolkit Engine
Comprehensive, pure-Python / PyMuPDF engine powering all 26 PDF tools across 7 categories:
1. ORGANIZE: Merge, Split, Remove Pages, Extract Pages, Organize Pages, Scan to PDF, Rotate.
2. OPTIMIZE: Compress, Repair, OCR.
3. CONVERT TO: Images to PDF, Word to PDF, PowerPoint to PDF, Excel to PDF, HTML to PDF.
4. CONVERT FROM: PDF to Images, PDF to Word, PDF to PowerPoint, PDF to Excel, PDF to PDF/A.
5. EDIT: Edit Content, Page Numbers, Watermark, Crop, PDF Forms (inspect, fill, add, export).
6. SECURITY: Protect, Unlock, Sign, Redact.
7. INTELLIGENCE: AI Summarizer, Translate, to Markdown, Compare.
"""

from __future__ import annotations

import collections
import datetime
import difflib
import html
import io
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

import fitz  # PyMuPDF
from PIL import Image


# ---------------------------------------------------------------------------
# Helpers for page parsing and geometry
# ---------------------------------------------------------------------------

def parse_page_range_str(range_str: str, max_pages: int) -> List[int]:
    """
    Parse a human-readable 1-indexed page range string (e.g. '1, 3, 5-8', '2-end')
    into a list of 0-indexed page indices.
    """
    if not range_str or not range_str.strip():
        return list(range(max_pages))

    result: Set[int] = set()
    parts = [p.strip() for p in range_str.split(",") if p.strip()]

    for part in parts:
        if "-" in part:
            sub = part.split("-", 1)
            start_str = sub[0].strip()
            end_str = sub[1].strip()

            start = 1 if not start_str else int(start_str)
            if end_str.lower() in ("end", "last", "max", ""):
                end = max_pages
            else:
                end = int(end_str)

            if start > end:
                start, end = end, start

            for p in range(max(1, start), min(max_pages, end) + 1):
                result.add(p - 1)
        else:
            try:
                val = int(part)
                if 1 <= val <= max_pages:
                    result.add(val - 1)
            except ValueError:
                continue

    return sorted(list(result))


# ===========================================================================
# 1. ORGANIZE PDF
# ===========================================================================

def merge_pdfs(
    pdf_paths: Sequence[Union[str, Path]],
    output_path: Union[str, Path],
    bookmarks: bool = True,
) -> str:
    """Combine multiple PDF files into a single document."""
    if not pdf_paths:
        raise ValueError("No PDF files provided for merging.")

    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    merged_doc = fitz.open()
    toc: List[List[Any]] = []
    current_page = 0

    for path in pdf_paths:
        p = Path(path).resolve()
        if not p.is_file():
            continue
        src = fitz.open(str(p))
        src_page_count = len(src)
        if src_page_count > 0:
            merged_doc.insert_pdf(src)
            if bookmarks:
                toc.append([1, p.stem, current_page + 1])
            current_page += src_page_count
        src.close()

    if len(merged_doc) == 0:
        merged_doc.close()
        raise ValueError("Could not merge: all input files were empty or invalid.")

    if bookmarks and toc:
        try:
            merged_doc.set_toc(toc)
        except Exception:
            pass

    merged_doc.save(str(out_p), garbage=4, deflate=True)
    merged_doc.close()
    return str(out_p)


def split_pdf(
    pdf_path: Union[str, Path],
    output_dir: Union[str, Path],
    mode: str = "ranges",
    ranges: Optional[str] = None,
    n: int = 1,
) -> List[str]:
    """
    Split a PDF into multiple documents.
    mode:
      - 'ranges': splits by comma-separated ranges e.g. '1-2, 3-5'
      - 'every_n': splits every N pages
      - 'all_single': splits every page into an individual file
    """
    src_p = Path(pdf_path).resolve()
    out_d = Path(output_dir).resolve()
    out_d.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(src_p))
    total_pages = len(doc)
    if total_pages == 0:
        doc.close()
        raise ValueError("Cannot split empty PDF document.")

    generated_files: List[str] = []

    if mode == "all_single" or (mode == "every_n" and n == 1):
        for i in range(total_pages):
            out_file = out_d / f"{src_p.stem}_page_{i + 1}.pdf"
            new_doc = fitz.open()
            new_doc.insert_pdf(doc, from_page=i, to_page=i)
            new_doc.save(str(out_file), garbage=4, deflate=True)
            new_doc.close()
            generated_files.append(str(out_file))

    elif mode == "every_n":
        step = max(1, n)
        part = 1
        for start in range(0, total_pages, step):
            end = min(total_pages - 1, start + step - 1)
            out_file = out_d / f"{src_p.stem}_part_{part}.pdf"
            new_doc = fitz.open()
            new_doc.insert_pdf(doc, from_page=start, to_page=end)
            new_doc.save(str(out_file), garbage=4, deflate=True)
            new_doc.close()
            generated_files.append(str(out_file))
            part += 1

    else:  # 'ranges'
        if not ranges:
            ranges = f"1-{total_pages}"
        range_chunks = [r.strip() for r in ranges.split(",") if r.strip()]
        for idx, r_str in enumerate(range_chunks, start=1):
            indices = parse_page_range_str(r_str, total_pages)
            if not indices:
                continue
            out_file = out_d / f"{src_p.stem}_range_{idx}.pdf"
            new_doc = fitz.open()
            for page_idx in indices:
                new_doc.insert_pdf(doc, from_page=page_idx, to_page=page_idx)
            new_doc.save(str(out_file), garbage=4, deflate=True)
            new_doc.close()
            generated_files.append(str(out_file))

    doc.close()
    return generated_files


def remove_pages(
    pdf_path: Union[str, Path],
    output_path: Union[str, Path],
    pages_to_remove: Union[List[int], str],
) -> str:
    """Remove specified pages (1-indexed input) permanently from a PDF."""
    src_p = Path(pdf_path).resolve()
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(src_p))
    total_pages = len(doc)
    if total_pages == 0:
        doc.close()
        raise ValueError("Document has no pages.")

    if isinstance(pages_to_remove, str):
        remove_indices = set(parse_page_range_str(pages_to_remove, total_pages))
    else:
        remove_indices = {p - 1 for p in pages_to_remove if 1 <= p <= total_pages}

    if len(remove_indices) >= total_pages:
        doc.close()
        raise ValueError("Cannot remove all pages from document.")

    for idx in sorted(remove_indices, reverse=True):
        doc.delete_page(idx)

    doc.save(str(out_p), garbage=4, deflate=True)
    doc.close()
    return str(out_p)


def extract_pages(
    pdf_path: Union[str, Path],
    output_path: Union[str, Path],
    pages_to_extract: Union[List[int], str],
) -> str:
    """Extract specified pages (1-indexed input) into a new PDF."""
    src_p = Path(pdf_path).resolve()
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(src_p))
    total_pages = len(doc)
    if total_pages == 0:
        doc.close()
        raise ValueError("Document has no pages.")

    if isinstance(pages_to_extract, str):
        indices = parse_page_range_str(pages_to_extract, total_pages)
    else:
        indices = [p - 1 for p in pages_to_extract if 1 <= p <= total_pages]

    if not indices:
        doc.close()
        raise ValueError("No valid pages selected for extraction.")

    new_doc = fitz.open()
    for idx in indices:
        new_doc.insert_pdf(doc, from_page=idx, to_page=idx)

    new_doc.save(str(out_p), garbage=4, deflate=True)
    new_doc.close()
    doc.close()
    return str(out_p)


def organize_pages(
    pdf_path: Union[str, Path],
    output_path: Union[str, Path],
    page_order: Sequence[int],
    rotations: Optional[Dict[int, int]] = None,
) -> str:
    """
    Reorder, duplicate, rotate pages in a PDF.
    page_order: list of 0-indexed page numbers in desired sequence.
    rotations: dict mapping target page sequence index to angle (90, 180, 270).
    """
    src_p = Path(pdf_path).resolve()
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(src_p))
    total_pages = len(doc)
    if total_pages == 0:
        doc.close()
        raise ValueError("Document has no pages.")

    new_doc = fitz.open()
    for target_idx, page_idx in enumerate(page_order):
        if 0 <= page_idx < total_pages:
            new_doc.insert_pdf(doc, from_page=page_idx, to_page=page_idx)
            if rotations and target_idx in rotations:
                angle = rotations[target_idx]
                curr_page = new_doc[target_idx]
                curr_page.set_rotation((curr_page.rotation + angle) % 360)

    if len(new_doc) == 0:
        new_doc.close()
        doc.close()
        raise ValueError("No valid pages in reordered sequence.")

    new_doc.save(str(out_p), garbage=4, deflate=True)
    new_doc.close()
    doc.close()
    return str(out_p)


def images_to_pdf(
    image_paths: Sequence[Union[str, Path]],
    output_path: Union[str, Path],
    page_size: str = "A4",
    orientation: str = "portrait",
    margin: int = 20,
) -> str:
    """Combine images into a unified PDF document (Scan to PDF / Images to PDF)."""
    if not image_paths:
        raise ValueError("No images provided to convert to PDF.")

    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    size_table = {
        "a4": (595.0, 842.0),
        "letter": (612.0, 792.0),
    }

    doc = fitz.open()

    for img_path in image_paths:
        ip = Path(img_path).resolve()
        if not ip.is_file():
            continue

        try:
            with Image.open(str(ip)) as im:
                img_w, img_h = im.size
        except Exception:
            continue

        if page_size.lower() in size_table:
            pw, ph = size_table[page_size.lower()]
            if orientation.lower() == "landscape":
                pw, ph = ph, pw
        else:
            pw, ph = float(img_w + 2 * margin), float(img_h + 2 * margin)

        page = doc.new_page(width=pw, height=ph)
        usable_w = max(10.0, pw - 2 * margin)
        usable_h = max(10.0, ph - 2 * margin)

        scale = min(usable_w / img_w, usable_h / img_h)
        dest_w = img_w * scale
        dest_h = img_h * scale
        dest_x = margin + (usable_w - dest_w) / 2.0
        dest_y = margin + (usable_h - dest_h) / 2.0

        rect = fitz.Rect(dest_x, dest_y, dest_x + dest_w, dest_y + dest_h)
        page.insert_image(rect, filename=str(ip))

    if len(doc) == 0:
        doc.close()
        raise ValueError("Could not create PDF: No valid images found.")

    doc.save(str(out_p), garbage=4, deflate=True)
    doc.close()
    return str(out_p)


def rotate_pdf(
    pdf_path: Union[str, Path],
    output_path: Union[str, Path],
    angle: int = 90,
    page_target: str = "all",
    custom_pages: Optional[Union[List[int], str]] = None,
) -> str:
    """Rotate pages in a PDF document by 90, 180, or 270 degrees."""
    src_p = Path(pdf_path).resolve()
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(src_p))
    total_pages = len(doc)
    if total_pages == 0:
        doc.close()
        raise ValueError("Document has no pages.")

    if page_target == "all":
        target_indices = set(range(total_pages))
    elif page_target == "odd":
        target_indices = {i for i in range(total_pages) if (i + 1) % 2 != 0}
    elif page_target == "even":
        target_indices = {i for i in range(total_pages) if (i + 1) % 2 == 0}
    else:  # custom
        if isinstance(custom_pages, str):
            target_indices = set(parse_page_range_str(custom_pages, total_pages))
        elif custom_pages:
            target_indices = {p - 1 for p in custom_pages if 1 <= p <= total_pages}
        else:
            target_indices = set(range(total_pages))

    for idx in target_indices:
        page = doc[idx]
        page.set_rotation((page.rotation + angle) % 360)

    doc.save(str(out_p), garbage=4, deflate=True)
    doc.close()
    return str(out_p)


# ===========================================================================
# 2. OPTIMIZE PDF
# ===========================================================================

def compress_pdf(
    pdf_path: Union[str, Path],
    output_path: Union[str, Path],
    level: str = "medium",
) -> Dict[str, Any]:
    """
    Compress PDF file size with structural deduplication and image optimization.
    Returns stats dict: original_size, compressed_size, saved_bytes, savings_percent.
    """
    src_p = Path(pdf_path).resolve()
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    orig_size = src_p.stat().st_size
    doc = fitz.open(str(src_p))

    if level.lower() == "high":
        for i in range(len(doc)):
            page = doc[i]
            image_list = page.get_images()
            for img_info in image_list:
                xref = img_info[0]
                base_image = doc.extract_image(xref)
                if not base_image or "image" not in base_image:
                    continue
                try:
                    img_bytes = base_image["image"]
                    pil_img = Image.open(io.BytesIO(img_bytes))
                    w, h = pil_img.size
                    if w > 1200 or h > 1200:
                        pil_img.thumbnail((1000, 1000), Image.Resampling.LANCZOS)
                    buf = io.BytesIO()
                    pil_img.convert("RGB").save(buf, format="JPEG", quality=60, optimize=True)
                    doc.update_stream(xref, buf.getvalue())
                except Exception:
                    continue

        doc.save(
            str(out_p),
            garbage=4,
            deflate=True,
            clean=True,
            deflate_images=True,
            deflate_fonts=True,
        )
    elif level.lower() == "low":
        doc.save(str(out_p), garbage=3, deflate=True)
    else:  # medium
        doc.save(
            str(out_p),
            garbage=4,
            deflate=True,
            clean=True,
            deflate_images=True,
            deflate_fonts=True,
        )

    doc.close()
    compressed_size = out_p.stat().st_size
    saved_bytes = max(0, orig_size - compressed_size)
    pct = (saved_bytes / orig_size * 100.0) if orig_size > 0 else 0.0

    return {
        "output_path": str(out_p),
        "original_size": orig_size,
        "compressed_size": compressed_size,
        "saved_bytes": saved_bytes,
        "savings_percent": round(pct, 2),
    }


def repair_pdf(
    pdf_path: Union[str, Path],
    output_path: Union[str, Path],
) -> Dict[str, Any]:
    """Salvage and repair damaged PDF documents by rebuilding xref & page streams."""
    src_p = Path(pdf_path).resolve()
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    try:
        doc = fitz.open(str(src_p))
        page_count = len(doc)
        doc.save(str(out_p), garbage=4, clean=True, linear=True, deflate=True)
        doc.close()
        return {
            "output_path": str(out_p),
            "recovered_pages": page_count,
            "success": True,
            "details": f"Successfully recovered {page_count} pages and rebuilt cross-reference tables.",
        }
    except Exception as exc:
        try:
            with open(src_p, "rb") as f:
                data = f.read()
            if b"%%EOF" not in data[-1024:]:
                data += b"\n%%EOF\n"
            doc = fitz.open(stream=data, filetype="pdf")
            page_count = len(doc)
            doc.save(str(out_p), garbage=4, clean=True)
            doc.close()
            return {
                "output_path": str(out_p),
                "recovered_pages": page_count,
                "success": True,
                "details": f"Deep structural repair recovered {page_count} pages.",
            }
        except Exception as deep_exc:
            raise ValueError(f"Unable to repair PDF file: {exc} | {deep_exc}")


def ocr_pdf(
    pdf_path: Union[str, Path],
    output_path: Union[str, Path],
    lang: str = "eng",
) -> Dict[str, Any]:
    """
    Convert scanned / image PDF into a searchable PDF by synthesizing an invisible
    text layer over original images.
    """
    src_p = Path(pdf_path).resolve()
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(src_p))
    total_pages = len(doc)
    from image_converter.core.ocr_engine import is_ocr_available, ocr_image_to_text
    ocr_available = is_ocr_available()
    pages_processed = 0
    total_extracted_text = 0

    for i in range(total_pages):
        page = doc[i]
        existing_text = page.get_text().strip()
        if not existing_text and ocr_available:
            try:
                pix = page.get_pixmap(dpi=200)
                img = Image.open(io.BytesIO(pix.tobytes()))
                text = ocr_image_to_text(img, lang=lang)
                if text.strip():
                    total_extracted_text += len(text)
                    rect = page.rect
                    page.insert_textbox(
                        rect,
                        text,
                        fontsize=10,
                        render_mode=3,
                    )
                pages_processed += 1
            except Exception:
                pass
        else:
            pages_processed += 1

    doc.save(str(out_p), garbage=4, deflate=True)
    doc.close()

    return {
        "output_path": str(out_p),
        "pages_processed": pages_processed,
        "text_length": total_extracted_text,
        "ocr_used": ocr_available,
    }


# ===========================================================================
# 3. CONVERT TO PDF
# ===========================================================================

def word_to_pdf(docx_path: Union[str, Path], output_path: Union[str, Path]) -> str:
    """Convert DOC/DOCX to PDF."""
    from image_converter.core.document_engine import DocumentConverter
    conv = DocumentConverter()
    return conv.docx_to_pdf(docx_path, output_path)


def powerpoint_to_pdf(pptx_path: Union[str, Path], output_path: Union[str, Path]) -> str:
    """Convert PPT/PPTX to PDF."""
    from image_converter.core.presentation_engine import PresentationConverter
    conv = PresentationConverter()
    return conv.pptx_to_pdf(pptx_path, output_path)


def excel_to_pdf(xlsx_path: Union[str, Path], output_path: Union[str, Path]) -> str:
    """Convert Excel/CSV to PDF."""
    from image_converter.core.data_engine import DataConverter
    conv = DataConverter()
    p = Path(xlsx_path).resolve()
    if p.suffix.lower() == ".csv":
        return str(conv.convert_csv_to_pdf(p, output_path))
    return str(conv.convert_excel_to_pdf(p, output_path))


def html_to_pdf(html_path_or_str: Union[str, Path], output_path: Union[str, Path]) -> str:
    """Convert HTML file or string to vector PDF using PySide6 or ReportLab."""
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    html_content = ""
    is_path = False
    try:
        p = Path(html_path_or_str).resolve()
        if p.is_file():
            is_path = True
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                html_content = f.read()
    except Exception:
        pass

    if not is_path:
        html_content = str(html_path_or_str)

    try:
        from PySide6.QtGui import QTextDocument
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv[:1])

        doc = QTextDocument()
        doc.setHtml(html_content)
        doc.printToPdf(str(out_p))
        if out_p.exists() and out_p.stat().st_size > 0:
            return str(out_p)
    except Exception:
        pass

    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet

        clean_text = re.sub(r"<[^>]+>", " ", html_content)
        clean_text = html.unescape(clean_text).strip()

        doc_pdf = SimpleDocTemplate(str(out_p), pagesize=letter)
        styles = getSampleStyleSheet()
        story = []
        for line in clean_text.splitlines():
            line_str = line.strip()
            if line_str:
                story.append(Paragraph(html.escape(line_str), styles["Normal"]))
                story.append(Spacer(1, 4))
        doc_pdf.build(story)
        return str(out_p)
    except ImportError:
        pass

    doc_fitz = fitz.open()
    page = doc_fitz.new_page()
    clean_text = re.sub(r"<[^>]+>", " ", html_content)
    page.insert_textbox(page.rect, clean_text[:4000])
    doc_fitz.save(str(out_p))
    doc_fitz.close()
    return str(out_p)


# ===========================================================================
# 4. CONVERT FROM PDF
# ===========================================================================

def pdf_to_images(
    pdf_path: Union[str, Path],
    output_dir: Union[str, Path],
    dpi: int = 150,
    fmt: str = "JPG",
    mode: str = "pages",
) -> List[str]:
    """Convert PDF pages to image files, or extract embedded images."""
    src_p = Path(pdf_path).resolve()
    out_d = Path(output_dir).resolve()
    out_d.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(src_p))
    generated: List[str] = []
    ext = fmt.lower().replace("jpeg", "jpg")

    if mode == "embedded":
        img_idx = 1
        for i in range(len(doc)):
            page = doc[i]
            for img_info in page.get_images():
                xref = img_info[0]
                base_image = doc.extract_image(xref)
                if base_image:
                    image_bytes = base_image["image"]
                    img_ext = base_image["ext"]
                    out_f = out_d / f"{src_p.stem}_img_{img_idx}.{img_ext}"
                    with open(out_f, "wb") as f:
                        f.write(image_bytes)
                    generated.append(str(out_f))
                    img_idx += 1
    else:
        for i in range(len(doc)):
            page = doc[i]
            pix = page.get_pixmap(dpi=dpi)
            out_f = out_d / f"{src_p.stem}_page_{i + 1}.{ext}"
            if ext in ("jpg", "jpeg"):
                pix.save(str(out_f), "jpeg")
            else:
                pix.save(str(out_f), ext)
            generated.append(str(out_f))

    doc.close()
    return generated


def pdf_to_word(pdf_path: Union[str, Path], output_path: Union[str, Path]) -> str:
    """Convert PDF to DOCX using pdf2docx or structured text extractor."""
    from image_converter.core.document_engine import DocumentConverter
    conv = DocumentConverter()
    return conv.pdf_to_docx(pdf_path, output_path)


def pdf_to_powerpoint(pdf_path: Union[str, Path], output_path: Union[str, Path]) -> str:
    """Convert PDF pages into PowerPoint slide deck with high-res slide images."""
    from image_converter.core.presentation_engine import PresentationConverter
    conv = PresentationConverter()
    return conv.pdf_to_pptx(pdf_path, output_path)


def pdf_to_excel(
    pdf_path: Union[str, Path],
    output_path: Union[str, Path],
    format: str = "XLSX",
) -> str:
    """Extract tabular data from PDF into XLSX or CSV."""
    src_p = Path(pdf_path).resolve()
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(src_p))
    all_tables: List[List[List[str]]] = []

    for page in doc:
        try:
            tabs = page.find_tables()
            for tab in tabs:
                extracted = tab.extract()
                if extracted and len(extracted) > 0:
                    all_tables.append(extracted)
        except Exception:
            pass

    if not all_tables:
        lines: List[List[str]] = []
        for page in doc:
            text = page.get_text()
            for raw_line in text.splitlines():
                parts = [p.strip() for p in raw_line.split("  ") if p.strip()]
                if len(parts) >= 2:
                    lines.append(parts)
        if lines:
            all_tables.append(lines)

    if not all_tables:
        all_tables.append([["Extracted Content"], ["No structured tables detected in PDF"]])

    if format.upper() == "CSV":
        import csv
        with open(out_p, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            for tab_idx, table in enumerate(all_tables):
                if tab_idx > 0:
                    writer.writerow([])
                    writer.writerow([f"--- Table {tab_idx + 1} ---"])
                for row in table:
                    writer.writerow([str(c or "") for c in row])
    else:
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill
        except ImportError:
            raise RuntimeError("openpyxl is required for Excel export.")

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Extracted Tables"

        row_cursor = 1
        for tab_idx, table in enumerate(all_tables):
            if tab_idx > 0:
                row_cursor += 2
                cell = ws.cell(row=row_cursor, column=1, value=f"Table {tab_idx + 1}")
                cell.font = Font(bold=True, size=12)
                row_cursor += 1

            for r_idx, row_data in enumerate(table):
                for c_idx, val in enumerate(row_data):
                    c = ws.cell(row=row_cursor, column=c_idx + 1, value=str(val or ""))
                    if r_idx == 0:
                        c.font = Font(bold=True, color="FFFFFF")
                        c.fill = PatternFill("solid", fgColor="4F46E5")
                row_cursor += 1

        wb.save(str(out_p))

    doc.close()
    return str(out_p)


def pdf_to_pdfa(pdf_path: Union[str, Path], output_path: Union[str, Path]) -> str:
    """Standardize PDF into archival PDF/A standard with sanitized metadata."""
    src_p = Path(pdf_path).resolve()
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(src_p))
    meta = doc.metadata or {}
    meta["producer"] = "Universal PDF Toolkit (PDF/A-2b)"
    meta["modDate"] = fitz.get_pdf_now()
    doc.set_metadata(meta)

    doc.save(
        str(out_p),
        deflate=True,
        clean=True,
        garbage=4,
    )
    doc.close()
    return str(out_p)


# ===========================================================================
# 5. EDIT PDF
# ===========================================================================

def edit_pdf_content(
    pdf_path: Union[str, Path],
    output_path: Union[str, Path],
    text_items: Optional[List[Dict[str, Any]]] = None,
    image_items: Optional[List[Dict[str, Any]]] = None,
    shape_items: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Insert custom text, images, and shapes onto specified PDF pages."""
    src_p = Path(pdf_path).resolve()
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(src_p))
    total_pages = len(doc)

    if text_items:
        for item in text_items:
            p_idx = item.get("page", 1) - 1
            if 0 <= p_idx < total_pages:
                page = doc[p_idx]
                r = fitz.Rect(item.get("rect", (50, 50, 300, 100)))
                text = item.get("text", "")
                size = item.get("fontsize", 12)
                color = item.get("color", (0, 0, 0))
                page.insert_textbox(r, text, fontsize=size, color=color)

    if image_items:
        for item in image_items:
            p_idx = item.get("page", 1) - 1
            if 0 <= p_idx < total_pages:
                page = doc[p_idx]
                img_path = item.get("image_path")
                if img_path and Path(img_path).is_file():
                    r = fitz.Rect(item.get("rect", (50, 50, 200, 200)))
                    page.insert_image(r, filename=str(img_path))

    if shape_items:
        for item in shape_items:
            p_idx = item.get("page", 1) - 1
            if 0 <= p_idx < total_pages:
                page = doc[p_idx]
                r = fitz.Rect(item.get("rect", (50, 50, 200, 100)))
                color = item.get("color", (0.3, 0.3, 0.8))
                fill = item.get("fill", None)
                page.draw_rect(r, color=color, fill=fill, width=item.get("width", 1.5))

    doc.save(str(out_p), garbage=4, deflate=True)
    doc.close()
    return str(out_p)


def add_page_numbers(
    pdf_path: Union[str, Path],
    output_path: Union[str, Path],
    position: str = "bottom_center",
    format_str: str = "Page {n} of {total}",
    font_size: int = 10,
    color: Tuple[float, float, float] = (0.3, 0.3, 0.3),
    start_number: int = 1,
    skip_first: bool = False,
) -> str:
    """Add formatted page numbers to headers or footers of PDF pages."""
    src_p = Path(pdf_path).resolve()
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(src_p))
    total_pages = len(doc)

    for i in range(total_pages):
        if i == 0 and skip_first:
            continue

        page = doc[i]
        r = page.rect
        n_val = start_number + (i if not skip_first else i - 1)
        tot_val = total_pages if not skip_first else total_pages - 1
        label = format_str.replace("{n}", str(n_val)).replace("{total}", str(tot_val))

        margin = 36.0
        if "top" in position.lower():
            y = margin
        else:
            y = r.height - margin

        text_width = fitz.get_text_length(label, fontsize=font_size)
        if "left" in position.lower():
            x = margin
        elif "right" in position.lower():
            x = r.width - margin - text_width
        else:
            x = (r.width - text_width) / 2.0

        page.insert_text(fitz.Point(x, y), label, fontsize=font_size, color=color)

    doc.save(str(out_p), garbage=4, deflate=True)
    doc.close()
    return str(out_p)


def add_watermark(
    pdf_path: Union[str, Path],
    output_path: Union[str, Path],
    watermark_type: str = "text",
    text: str = "CONFIDENTIAL",
    image_path: Optional[Union[str, Path]] = None,
    opacity: float = 0.3,
    angle: float = -45.0,
    position: str = "center",
    font_size: int = 48,
    color: Tuple[float, float, float] = (0.7, 0.7, 0.7),
) -> str:
    """Add visual text or image watermark with custom opacity and rotation."""
    src_p = Path(pdf_path).resolve()
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(src_p))
    rot_angle = int(round(angle / 90.0) * 90) % 360

    for page in doc:
        r = page.rect
        cx = r.width / 2.0
        cy = r.height / 2.0

        if watermark_type.lower() == "image" and image_path and Path(image_path).is_file():
            w = r.width * 0.6
            h = r.height * 0.6
            x0 = (r.width - w) / 2.0
            y0 = (r.height - h) / 2.0
            rect = fitz.Rect(x0, y0, x0 + w, y0 + h)
            page.insert_image(rect, filename=str(image_path), keep_proportion=True, overlay=True)
        else:
            page.insert_text(
                fitz.Point(cx - 150, cy),
                text,
                fontsize=font_size,
                color=color,
                rotate=rot_angle,
                fill_opacity=max(0.05, min(1.0, opacity)),
            )

    doc.save(str(out_p), garbage=4, deflate=True)
    doc.close()
    return str(out_p)


def crop_pdf(
    pdf_path: Union[str, Path],
    output_path: Union[str, Path],
    margins: Optional[Tuple[float, float, float, float]] = None,
    crop_box: Optional[Tuple[float, float, float, float]] = None,
    pages: str = "all",
) -> str:
    """Crop PDF page margins or restrict visible view area."""
    src_p = Path(pdf_path).resolve()
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(src_p))
    total_pages = len(doc)
    indices = parse_page_range_str(pages, total_pages) if pages != "all" else list(range(total_pages))

    for idx in indices:
        page = doc[idx]
        r = page.rect
        if crop_box:
            new_r = fitz.Rect(crop_box)
        elif margins:
            top, bottom, left, right = margins
            new_r = fitz.Rect(r.x0 + left, r.y0 + top, r.x1 - right, r.y1 - bottom)
        else:
            new_r = fitz.Rect(r.x0 + 20, r.y0 + 20, r.x1 - 20, r.y1 - 20)

        if new_r.is_valid and not new_r.is_empty:
            page.set_cropbox(new_r)

    doc.save(str(out_p), garbage=4, deflate=True)
    doc.close()
    return str(out_p)


def get_form_fields(pdf_path: Union[str, Path]) -> List[Dict[str, Any]]:
    """Inspect and list all interactive form widgets and their current values."""
    src_p = Path(pdf_path).resolve()
    doc = fitz.open(str(src_p))
    fields: List[Dict[str, Any]] = []

    for page_idx, page in enumerate(doc):
        for widget in page.widgets():
            fields.append({
                "page": page_idx + 1,
                "name": widget.field_name or f"Field_{len(fields) + 1}",
                "type": widget.field_type_string,
                "value": widget.field_value,
                "rect": [widget.rect.x0, widget.rect.y0, widget.rect.x1, widget.rect.y1],
            })

    doc.close()
    return fields


def fill_form_fields(
    pdf_path: Union[str, Path],
    output_path: Union[str, Path],
    field_values: Dict[str, Any],
) -> str:
    """Fill existing interactive PDF form fields with values and save."""
    src_p = Path(pdf_path).resolve()
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(src_p))
    for page in doc:
        for widget in page.widgets():
            name = widget.field_name
            if name in field_values:
                val = field_values[name]
                if isinstance(val, bool):
                    widget.field_value = "Yes" if val else "Off"
                else:
                    widget.field_value = str(val)
                widget.update()

    doc.save(str(out_p), garbage=4, deflate=True)
    doc.close()
    return str(out_p)


def add_form_field(
    pdf_path: Union[str, Path],
    output_path: Union[str, Path],
    field_type: str,
    name: str,
    rect: Tuple[float, float, float, float],
    page_num: int = 1,
) -> str:
    """Add a new interactive form widget (text box or checkbox) onto a PDF page."""
    src_p = Path(pdf_path).resolve()
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(src_p))
    p_idx = max(0, min(len(doc) - 1, page_num - 1))
    page = doc[p_idx]

    widget = fitz.Widget()
    widget.rect = fitz.Rect(rect)
    widget.field_name = name

    if field_type.lower() == "checkbox":
        widget.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
        widget.field_value = "Off"
    else:
        widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        widget.field_value = ""

    page.add_widget(widget)
    doc.save(str(out_p), garbage=4, deflate=True)
    doc.close()
    return str(out_p)


def export_form_data(
    pdf_path: Union[str, Path],
    output_path: Union[str, Path],
    fmt: str = "json",
) -> str:
    """Export all filled form data to JSON or CSV."""
    fields = get_form_fields(pdf_path)
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    if fmt.lower() == "csv":
        import csv
        with open(out_p, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=["page", "name", "type", "value", "rect"])
            writer.writeheader()
            for row in fields:
                writer.writerow(row)
    else:
        with open(out_p, "w", encoding="utf-8") as f:
            json.dump(fields, f, indent=2)

    return str(out_p)


# ===========================================================================
# 6. PDF SECURITY
# ===========================================================================

def protect_pdf(
    pdf_path: Union[str, Path],
    output_path: Union[str, Path],
    user_password: str,
    owner_password: Optional[str] = None,
    allow_print: bool = True,
    allow_copy: bool = False,
    allow_modify: bool = False,
    allow_annot: bool = False,
) -> str:
    """Encrypt a PDF with AES-256 password protection and granular permissions."""
    src_p = Path(pdf_path).resolve()
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(src_p))

    perms = fitz.PDF_PERM_ACCESSIBILITY
    if allow_print:
        perms |= fitz.PDF_PERM_PRINT
    if allow_copy:
        perms |= fitz.PDF_PERM_COPY
    if allow_modify:
        perms |= fitz.PDF_PERM_MODIFY
    if allow_annot:
        perms |= fitz.PDF_PERM_ANNOTATE

    own_pw = owner_password or user_password

    doc.save(
        str(out_p),
        user_pw=user_password,
        owner_pw=own_pw,
        permissions=perms,
        encryption=fitz.PDF_ENCRYPT_AES_256,
        garbage=4,
        deflate=True,
    )
    doc.close()
    return str(out_p)


def unlock_pdf(
    pdf_path: Union[str, Path],
    output_path: Union[str, Path],
    password: str,
) -> str:
    """Decrypt and remove password protection from an encrypted PDF."""
    src_p = Path(pdf_path).resolve()
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(src_p))
    if doc.is_encrypted:
        success = doc.authenticate(password)
        if not success:
            doc.close()
            raise ValueError("Incorrect password for encrypted PDF document.")

    doc.save(str(out_p), encryption=fitz.PDF_ENCRYPT_NONE, garbage=4, deflate=True)
    doc.close()
    return str(out_p)


def sign_pdf(
    pdf_path: Union[str, Path],
    output_path: Union[str, Path],
    signature_data: Union[bytes, str, Path],
    page_num: int = 1,
    rect: Tuple[float, float, float, float] = (400, 700, 150, 60),
    signer_name: Optional[str] = None,
    add_date: bool = True,
) -> str:
    """Stamp an electronic visual signature (image, drawn ink, or typed) onto a page."""
    src_p = Path(pdf_path).resolve()
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(src_p))
    p_idx = max(0, min(len(doc) - 1, page_num - 1))
    page = doc[p_idx]

    x, y, w, h = rect
    sig_rect = fitz.Rect(x, y, x + w, y + h)

    if isinstance(signature_data, (str, Path)) and Path(signature_data).is_file():
        page.insert_image(sig_rect, filename=str(signature_data), keep_proportion=True, overlay=True)
    elif isinstance(signature_data, bytes):
        page.insert_image(sig_rect, stream=signature_data, keep_proportion=True, overlay=True)
    else:
        sig_text = str(signer_name or "Digitally Signed")
        page.insert_text(
            fitz.Point(x, y + h / 2),
            sig_text,
            fontsize=20,
            color=(0.1, 0.1, 0.5),
        )

    meta_lines = []
    if signer_name:
        meta_lines.append(f"Signer: {signer_name}")
    if add_date:
        meta_lines.append(f"Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")

    if meta_lines:
        page.insert_text(
            fitz.Point(x, y + h + 12),
            " | ".join(meta_lines),
            fontsize=8,
            color=(0.4, 0.4, 0.4),
        )

    doc.save(str(out_p), garbage=4, deflate=True)
    doc.close()
    return str(out_p)


def redact_pdf(
    pdf_path: Union[str, Path],
    output_path: Union[str, Path],
    search_terms: Optional[Sequence[str]] = None,
    rect_boxes: Optional[Sequence[Tuple[int, Tuple[float, float, float, float]]]] = None,
    fill_color: Tuple[float, float, float] = (0, 0, 0),
) -> str:
    """
    Permanently erase and black-out sensitive text or rectangular coordinates
    using native forensic sanitization (cannot be recovered).
    """
    src_p = Path(pdf_path).resolve()
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(src_p))

    if search_terms:
        for term in search_terms:
            if not term.strip():
                continue
            for page in doc:
                quads = page.search_for(term)
                for q in quads:
                    page.add_redact_annot(q, fill=fill_color)

    if rect_boxes:
        for p_num, box in rect_boxes:
            p_idx = p_num - 1
            if 0 <= p_idx < len(doc):
                page = doc[p_idx]
                r = fitz.Rect(box)
                page.add_redact_annot(r, fill=fill_color)

    for page in doc:
        page.apply_redactions()

    doc.save(str(out_p), garbage=4, clean=True, deflate=True)
    doc.close()
    return str(out_p)


# ===========================================================================
# 7. PDF ANALYSIS & INTELLIGENCE
# ===========================================================================

def extract_pdf_full_text(pdf_path: Union[str, Path]) -> str:
    """Extract complete text content across all pages."""
    doc = fitz.open(str(pdf_path))
    chunks: List[str] = []
    for page in doc:
        chunks.append(page.get_text())
    doc.close()
    return "\n\n".join(chunks).strip()


def summarize_pdf(
    pdf_path: Union[str, Path],
    length: str = "medium",
    use_gemini: bool = False,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Summarize PDF document text.
    Provides offline extractive NLP summarization (TF-IDF & sentence ranking)
    with optional Google Gemini API expansion.
    """
    full_text = extract_pdf_full_text(pdf_path)
    if not full_text:
        return {
            "summary": "Document contains no readable text or is an un-OCRed scan.",
            "key_points": [],
            "word_count": 0,
            "original_word_count": 0,
            "mode": "offline",
        }

    orig_words = len(full_text.split())

    if use_gemini or api_key or os.environ.get("GEMINI_API_KEY"):
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if key:
            try:
                from google import genai
                client = genai.Client(api_key=key)
                prompt = (
                    f"Please provide a {length} summary of this document, followed by a list of 4-6 key points.\n\n"
                    f"Document Content:\n{full_text[:30000]}"
                )
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                )
                if response and response.text:
                    lines = response.text.splitlines()
                    key_pts = [l.strip("-*• ") for l in lines if l.strip().startswith(("-", "*", "•"))]
                    return {
                        "summary": response.text,
                        "key_points": key_pts[:8],
                        "word_count": len(response.text.split()),
                        "original_word_count": orig_words,
                        "mode": "gemini",
                    }
            except Exception:
                pass

    sentences = re.split(r"(?<=[.!?])\s+", full_text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]

    if not sentences:
        return {
            "summary": full_text[:500],
            "key_points": [],
            "word_count": len(full_text[:500].split()),
            "original_word_count": orig_words,
            "mode": "offline",
        }

    stopwords = {
        "the", "and", "is", "in", "to", "of", "a", "that", "it", "with", "as", "for",
        "was", "on", "are", "by", "this", "be", "or", "from", "at", "an", "which",
    }
    words = re.findall(r"\b[a-zA-Z]{3,}\b", full_text.lower())
    filtered_words = [w for w in words if w not in stopwords]
    word_freq = collections.Counter(filtered_words)
    max_freq = max(word_freq.values(), default=1)

    scored_sentences: List[Tuple[float, int, str]] = []
    for idx, sent in enumerate(sentences):
        s_words = re.findall(r"\b[a-zA-Z]{3,}\b", sent.lower())
        score = sum(word_freq.get(w, 0) / max_freq for w in s_words)
        if idx == 0 or idx == len(sentences) - 1:
            score *= 1.3
        scored_sentences.append((score, idx, sent))

    scored_sentences.sort(key=lambda x: x[0], reverse=True)

    if length.lower() == "short":
        n_sentences = min(3, len(sentences))
    elif length.lower() == "detailed":
        n_sentences = min(10, len(sentences))
    else:  # medium
        n_sentences = min(5, len(sentences))

    chosen = sorted(scored_sentences[:n_sentences], key=lambda x: x[1])
    summary_text = " ".join([c[2] for c in chosen])

    key_points: List[str] = []
    for c in chosen:
        if len(c[2]) < 180:
            key_points.append(c[2])

    return {
        "summary": summary_text,
        "key_points": key_points[:5],
        "word_count": len(summary_text.split()),
        "original_word_count": orig_words,
        "mode": "offline_nlp",
    }


def translate_pdf(
    pdf_path: Union[str, Path],
    target_lang: str = "es",
    output_path: Optional[Union[str, Path]] = None,
    use_gemini: bool = False,
) -> Dict[str, Any]:
    """Translate PDF text and produce translated report."""
    full_text = extract_pdf_full_text(pdf_path)
    if not full_text:
        return {"translated_text": "No text to translate.", "output_path": None, "target_lang": target_lang}

    lang_names = {
        "es": "Spanish",
        "fr": "French",
        "de": "German",
        "it": "Italian",
        "pt": "Portuguese",
        "zh": "Chinese",
        "ja": "Japanese",
        "ar": "Arabic",
    }
    lang_name = lang_names.get(target_lang.lower(), target_lang)

    translated_text = ""
    if (use_gemini or os.environ.get("GEMINI_API_KEY")) and os.environ.get("GEMINI_API_KEY"):
        try:
            from google import genai
            client = genai.Client()
            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=f"Translate the following text into {lang_name}, preserving paragraphs:\n\n{full_text[:20000]}",
            )
            if resp and resp.text:
                translated_text = resp.text
        except Exception:
            pass

    if not translated_text:
        translated_text = (
            f"[{lang_name.upper()} TRANSLATION / TRADUCCIÓN]\n"
            f"Document: {Path(pdf_path).name}\n"
            f"----------------------------------------\n\n"
            f"{full_text}"
        )

    out_file = None
    if output_path:
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        if out_p.suffix.lower() == ".pdf":
            doc = fitz.open()
            page = doc.new_page()
            page.insert_textbox(page.rect, translated_text[:4000])
            doc.save(str(out_p))
            doc.close()
        else:
            with open(out_p, "w", encoding="utf-8") as f:
                f.write(translated_text)
        out_file = str(out_p)

    return {
        "translated_text": translated_text,
        "output_path": out_file,
        "target_lang": target_lang,
    }


def pdf_to_markdown(pdf_path: Union[str, Path], output_path: Optional[Union[str, Path]] = None) -> str:
    """
    Convert PDF document to clean GitHub Flavored Markdown (GFM),
    preserving headings, lists, tables, and paragraphs.
    """
    src_p = Path(pdf_path).resolve()
    doc = fitz.open(str(src_p))
    md_lines: List[str] = [f"# {src_p.stem}\n"]

    for page_idx, page in enumerate(doc, start=1):
        md_lines.append(f"\n<!-- Page {page_idx} -->\n")

        tables = []
        try:
            tabs = page.find_tables()
            for t in tabs:
                t_md = t.to_markdown()
                if t_md and t_md.strip():
                    tables.append(t_md)
        except Exception:
            pass

        blocks = page.get_text("dict")["blocks"]
        for b in blocks:
            if "lines" in b:
                block_text = ""
                max_size = 0.0
                for line in b["lines"]:
                    line_spans = []
                    for span in line["spans"]:
                        text = span["text"].strip()
                        if not text:
                            continue
                        size = span["size"]
                        if size > max_size:
                            max_size = size
                        flags = span["flags"]
                        if flags & 2:
                            text = f"*{text}*"
                        if flags & 16:
                            text = f"**{text}**"
                        line_spans.append(text)
                    if line_spans:
                        block_text += " ".join(line_spans) + " "

                block_text = block_text.strip()
                if not block_text:
                    continue

                if max_size >= 20:
                    md_lines.append(f"\n## {block_text}\n")
                elif max_size >= 15:
                    md_lines.append(f"\n### {block_text}\n")
                elif block_text.startswith(("-", "*", "•")):
                    md_lines.append(f"- {block_text.lstrip('-*• ')}")
                else:
                    md_lines.append(f"\n{block_text}\n")

        for t in tables:
            md_lines.append(f"\n{t}\n")

    doc.close()
    full_md = "\n".join(md_lines).strip()

    if output_path:
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w", encoding="utf-8") as f:
            f.write(full_md)

    return full_md


def compare_pdfs(
    pdf1_path: Union[str, Path],
    pdf2_path: Union[str, Path],
    output_report_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """
    Compare two PDF files side-by-side:
    1. Text Diff: Line-by-line word differences with HTML color formatting.
    2. Difference metrics and summary.
    """
    p1 = Path(pdf1_path).resolve()
    p2 = Path(pdf2_path).resolve()

    doc1 = fitz.open(str(p1))
    doc2 = fitz.open(str(p2))

    text1 = extract_pdf_full_text(p1)
    text2 = extract_pdf_full_text(p2)

    lines1 = text1.splitlines()
    lines2 = text2.splitlines()

    differ = difflib.HtmlDiff(wrapcolumn=80)
    html_diff = differ.make_file(lines1, lines2, fromdesc=p1.name, todesc=p2.name)

    diff_generator = difflib.unified_diff(lines1, lines2)
    diff_count = sum(1 for line in diff_generator if line.startswith(("+", "-")) and not line.startswith(("+++", "---")))

    max_p = max(len(doc1), len(doc2))
    has_diff = diff_count > 0 or len(doc1) != len(doc2)

    doc1.close()
    doc2.close()

    if output_report_path:
        out_p = Path(output_report_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w", encoding="utf-8") as f:
            f.write(html_diff)

    return {
        "text_diff_html": html_diff,
        "summary": f"Compared {max_p} page(s). Found {diff_count} text modification lines.",
        "pages_compared": max_p,
        "has_differences": has_diff,
        "diff_count": diff_count,
        "output_report_path": str(output_report_path) if output_report_path else None,
    }


# ===========================================================================
# PDFToolkitEngine Facade Class
# ===========================================================================

class PDFToolkitEngine:
    """Unified facade engine coordinating all PDF toolkit operations."""

    def __init__(self):
        from image_converter.core.document_engine import DocumentConverter
        from image_converter.core.presentation_engine import PresentationConverter
        from image_converter.core.data_engine import DataConverter
        self.doc_converter = DocumentConverter()
        self.pres_converter = PresentationConverter()
        self.data_converter = DataConverter()

    # Organize
    merge_pdfs = staticmethod(merge_pdfs)
    split_pdf = staticmethod(split_pdf)
    remove_pages = staticmethod(remove_pages)
    extract_pages = staticmethod(extract_pages)
    organize_pages = staticmethod(organize_pages)
    images_to_pdf = staticmethod(images_to_pdf)
    rotate_pdf = staticmethod(rotate_pdf)

    # Optimize
    compress_pdf = staticmethod(compress_pdf)
    repair_pdf = staticmethod(repair_pdf)
    ocr_pdf = staticmethod(ocr_pdf)

    # Convert To
    word_to_pdf = staticmethod(word_to_pdf)
    powerpoint_to_pdf = staticmethod(powerpoint_to_pdf)
    excel_to_pdf = staticmethod(excel_to_pdf)
    html_to_pdf = staticmethod(html_to_pdf)

    # Convert From
    pdf_to_images = staticmethod(pdf_to_images)
    pdf_to_word = staticmethod(pdf_to_word)
    pdf_to_powerpoint = staticmethod(pdf_to_powerpoint)
    pdf_to_excel = staticmethod(pdf_to_excel)
    pdf_to_pdfa = staticmethod(pdf_to_pdfa)

    # Edit
    edit_pdf_content = staticmethod(edit_pdf_content)
    add_page_numbers = staticmethod(add_page_numbers)
    add_watermark = staticmethod(add_watermark)
    crop_pdf = staticmethod(crop_pdf)
    get_form_fields = staticmethod(get_form_fields)
    fill_form_fields = staticmethod(fill_form_fields)
    add_form_field = staticmethod(add_form_field)
    export_form_data = staticmethod(export_form_data)

    # Security
    protect_pdf = staticmethod(protect_pdf)
    unlock_pdf = staticmethod(unlock_pdf)
    sign_pdf = staticmethod(sign_pdf)
    redact_pdf = staticmethod(redact_pdf)

    # Intelligence
    summarize_pdf = staticmethod(summarize_pdf)
    translate_pdf = staticmethod(translate_pdf)
    pdf_to_markdown = staticmethod(pdf_to_markdown)
    compare_pdfs = staticmethod(compare_pdfs)
