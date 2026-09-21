"""
Document conversion engine for PDF and Word (.docx) files.
Supports converting between PDF, Word, Images, Plain Text, HTML, CSV, and XLSX.
"""

from __future__ import annotations

import html
import logging
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import fitz  # PyMuPDF
from PIL import Image

logger = logging.getLogger(__name__)

# Check optional pdf2docx
_PDF2DOCX_AVAILABLE = False
try:
    from pdf2docx import Converter as PDF2DocxConverter
    _PDF2DOCX_AVAILABLE = True
except ImportError:
    pass

# Check python-docx
_DOCX_AVAILABLE = False
try:
    import docx
    from docx.shared import Inches, Pt, RGBColor
    _DOCX_AVAILABLE = True
except ImportError:
    pass

# Check reportlab for pure-python PDF generation
_REPORTLAB_AVAILABLE = False
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table as RLTable,
        TableStyle as RLTableStyle,
    )
    _REPORTLAB_AVAILABLE = True
except ImportError:
    pass


def open_pdf_with_password(pdf_path: str | Path, password: Optional[str] = None) -> fitz.Document:
    """Open a PDF document, authenticating with password if encrypted."""
    p = Path(pdf_path).resolve()
    doc = fitz.open(str(p))
    if doc.is_encrypted:
        if password is not None:
            if not doc.authenticate(password):
                doc.close()
                raise ValueError("Incorrect password for encrypted PDF document.")
        else:
            doc.close()
            raise ValueError("PDF document is encrypted / password-protected. Please provide a password.")
    return doc


def check_docx_encryption(file_path: str | Path) -> None:
    """Detect if DOCX is an encrypted OLE package."""
    p = Path(file_path).resolve()
    try:
        with open(p, "rb") as f:
            header = f.read(8)
            if header == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
                f.seek(0)
                data = f.read(4096)
                if b"EncryptedPackage" in data or b"EncryptionInfo" in data:
                    raise ValueError("Word document is encrypted / password-protected.")
    except ValueError:
        raise
    except Exception as e:
        logger.warning(f"Error checking Word document encryption for {p.name}: {e}", exc_info=True)


def get_pdf_metadata(file_path: str | Path, password: Optional[str] = None) -> Dict[str, Any]:
    """Extract metadata, page count, and dimensions from a PDF document."""
    p = Path(file_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"PDF file not found: {file_path}")

    doc = fitz.open(str(p))
    is_enc = doc.is_encrypted
    if is_enc and password:
        doc.authenticate(password)

    page_count = len(doc)
    w, h = 0, 0
    if page_count > 0:
        try:
            first_page = doc[0]
            rect = first_page.rect
            w = int(rect.width)
            h = int(rect.height)
        except Exception as e:
            logger.warning(f"Error reading page dimensions for PDF {p.name}: {e}", exc_info=True)

    meta = doc.metadata or {}
    file_size = p.stat().st_size
    doc.close()

    return {
        "file_name": p.name,
        "file_path": str(p),
        "file_size": file_size,
        "width": w,
        "height": h,
        "page_count": page_count,
        "format": "PDF",
        "title": meta.get("title") or "",
        "author": meta.get("author") or "",
        "is_encrypted": is_enc,
        "has_alpha": False,
    }


def get_docx_metadata(file_path: str | Path) -> Dict[str, Any]:
    """Extract metadata, paragraph count, and word estimate from a DOCX document."""
    p = Path(file_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"DOCX file not found: {file_path}")

    check_docx_encryption(p)

    file_size = p.stat().st_size
    para_count = 0
    table_count = 0
    word_count = 0

    if _DOCX_AVAILABLE:
        try:
            doc = docx.Document(str(p))
            para_count = len(doc.paragraphs)
            table_count = len(doc.tables)
            for para in doc.paragraphs:
                word_count += len(para.text.split())
            for tbl in doc.tables:
                for row in tbl.rows:
                    for cell in row.cells:
                        word_count += len(cell.text.split())
        except Exception as e:
            logger.warning(f"Error reading DOCX structure for {p.name}: {e}", exc_info=True)

    return {
        "file_name": p.name,
        "file_path": str(p),
        "file_size": file_size,
        "width": 612,  # standard 8.5" letter points
        "height": 792,
        "page_count": max(1, para_count // 30 + 1),
        "paragraphs": para_count,
        "tables": table_count,
        "word_count": word_count,
        "format": "DOCX",
        "has_alpha": False,
    }


class DocumentConverter:
    """Core document conversion engine handling PDF and Word documents."""

    def __init__(self):
        self.has_pdf2docx = _PDF2DOCX_AVAILABLE
        self.has_docx = _DOCX_AVAILABLE
        self.has_reportlab = _REPORTLAB_AVAILABLE

    # -------------------------------------------------------------------------
    # PDF Input Conversions
    # -------------------------------------------------------------------------

    def convert_pdf_to_images(
        self,
        pdf_path: str | Path,
        output_path: str | Path,
        target_format: str = "PNG",
        dpi: int = 150,
        page_numbers: Optional[List[int]] = None,
        password: Optional[str] = None,
    ) -> List[Path]:
        """
        Convert PDF pages to image files (PNG, JPG, WEBP, etc.).
        If output_path has a suffix, writes page 1 to output_path and additional pages as
        {stem}_page_{n}{suffix}.
        Returns list of written image file paths.
        """
        in_p = Path(pdf_path).resolve()
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)

        doc = open_pdf_with_password(in_p, password=password)
        total_pages = len(doc)
        pages_to_render = page_numbers if page_numbers else list(range(total_pages))
        generated_files: List[Path] = []

        scale = dpi / 72.0
        matrix = fitz.Matrix(scale, scale)
        ext = f".{target_format.lower()}"
        if ext == ".jpeg":
            ext = ".jpg"

        # Determine base stem
        if out_p.suffix:
            base_stem = out_p.stem
            out_dir = out_p.parent
        else:
            base_stem = in_p.stem
            out_dir = out_p

        for idx, page_idx in enumerate(pages_to_render):
            if 0 <= page_idx < total_pages:
                page = doc[page_idx]
                pix = page.get_pixmap(matrix=matrix, alpha=False)

                if len(pages_to_render) == 1 and out_p.suffix:
                    dest = out_p
                elif idx == 0 and out_p.suffix and len(pages_to_render) == 1:
                    dest = out_p
                else:
                    dest = out_dir / f"{base_stem}_page_{page_idx + 1}{ext}"

                # Save directly via PyMuPDF or Pillow for format versatility
                if target_format.upper() in ("PNG", "JPG", "JPEG"):
                    pix.save(str(dest))
                else:
                    # Use PIL for other formats like WEBP, BMP, TIFF
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    img.save(str(dest), format=target_format.upper())

                generated_files.append(dest)

        doc.close()
        return generated_files

    def convert_pdf_to_docx(
        self,
        pdf_path: str | Path,
        output_path: str | Path,
        password: Optional[str] = None,
        enable_ocr: bool = False,
    ) -> Path:
        """
        Convert PDF to DOCX using pdf2docx or native MS Word COM for layout fidelity.
        Fails if native conversion is unavailable instead of making a fake text-only document.
        """
        in_p = Path(pdf_path).resolve()
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)

        # Primary: pdf2docx Converter
        if self.has_pdf2docx and not password:
            try:
                cv = PDF2DocxConverter(str(in_p))
                cv.convert(str(out_p))
                cv.close()
                if out_p.is_file() and out_p.stat().st_size > 0:
                    return out_p
            except Exception as e:
                logger.warning(f"pdf2docx conversion failed for {in_p.name}: {e}", exc_info=True)

        # Fallback: MS Word COM (Word can open PDF and convert to DOCX natively)
        if sys.platform == "win32":
            from image_converter.core.com_utils import (
                com_initialized,
                WD_ALERTS_NONE,
                MSO_AUTOMATION_SECURITY_FORCE_DISABLE,
                WD_FORMAT_DOCX,
            )
            with com_initialized():
                import win32com.client
                try:
                    word = win32com.client.DispatchEx("Word.Application")
                except Exception as dispatch_err:
                    logger.warning(f"Word COM not available: {dispatch_err}")
                    word = None

                if word is not None:
                    try:
                        word.Visible = False
                        word.DisplayAlerts = WD_ALERTS_NONE
                        word.AutomationSecurity = MSO_AUTOMATION_SECURITY_FORCE_DISABLE
                        doc = None
                        tmp_out = out_p.with_name(f"{out_p.stem}_tmp_{os.getpid()}_{time.time_ns()}.docx")
                        try:
                            try:
                                # Open PDF in Word (performs native PDF reflow conversion)
                                doc = word.Documents.Open(str(in_p), ReadOnly=True, ConfirmConversions=False)
                                doc.SaveAs(str(tmp_out), FileFormat=WD_FORMAT_DOCX)
                            finally:
                                if doc is not None:
                                    try:
                                        doc.Close(False)
                                    except Exception as close_err:
                                        logger.warning(f"Error closing Word document: {close_err}")
                            if tmp_out.is_file() and tmp_out.stat().st_size > 0:
                                os.replace(tmp_out, out_p)
                        finally:
                            if tmp_out.exists():
                                try:
                                    tmp_out.unlink()
                                except Exception as unlink_err:
                                    logger.warning(f"Could not remove temporary file {tmp_out}: {unlink_err}")
                    except Exception as e:
                        logger.warning(f"MS Word COM PDF-to-DOCX conversion failed for {in_p.name}: {e}", exc_info=True)
                        raise RuntimeError(f"Microsoft Word PDF-to-DOCX conversion failed for '{in_p.name}': {e}") from e
                    finally:
                        try:
                            word.Quit()
                        except Exception as quit_err:
                            logger.warning(f"Error quitting Word application: {quit_err}")
                    if out_p.is_file() and out_p.stat().st_size > 0:
                        return out_p

        raise RuntimeError("True PDF to DOCX conversion failed. Ensure 'pdf2docx' is installed or Microsoft Word is available.")

    def convert_pdf_to_text(
        self,
        pdf_path: str | Path,
        output_path: str | Path,
        password: Optional[str] = None,
        enable_ocr: bool = False,
    ) -> Path:
        """Extract all textual content from a PDF into a UTF-8 text file, with optional OCR fallback."""
        in_p = Path(pdf_path).resolve()
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)

        doc = open_pdf_with_password(in_p, password=password)
        full_text: List[str] = []

        for idx, page in enumerate(doc, 1):
            page_text = page.get_text("text").strip()
            if not page_text and enable_ocr:
                try:
                    from image_converter.core.ocr_engine import is_ocr_available, ocr_pdf_page
                    if is_ocr_available():
                        page_text = ocr_pdf_page(page).strip()
                except Exception as e:
                    logger.warning(f"OCR failed on page {idx} of {in_p.name}: {e}", exc_info=True)
            if page_text:
                full_text.append(f"--- Page {idx} ---\n{page_text}\n")

        doc.close()
        out_p.write_text("\n".join(full_text), encoding="utf-8")
        return out_p

    def convert_pdf_to_tables(
        self,
        pdf_path: str | Path,
        output_path: str | Path,
        target_format: str = "CSV",
        password: Optional[str] = None,
    ) -> Path:
        """Extract structured tables from PDF into CSV or XLSX format."""
        import pandas as pd

        in_p = Path(pdf_path).resolve()
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)

        self.last_table_warning: Optional[str] = None
        doc = open_pdf_with_password(in_p, password=password)
        total_pages = len(doc)
        raw_tables: List[pd.DataFrame] = []
        page_errors: List[Tuple[int, str]] = []

        for page_idx, page in enumerate(doc, 1):
            if hasattr(page, "find_tables"):
                try:
                    tabs = page.find_tables()
                    for tab in tabs:
                        raw_rows = tab.extract()
                        if not raw_rows or not any(any(c for c in r) for r in raw_rows):
                            continue
                        df = tab.to_pandas()
                        if not df.empty:
                            df.attrs["raw_rows"] = raw_rows
                            df.attrs["page_idx"] = page_idx
                            df.attrs["bbox"] = tab.bbox
                            if tab.rows and hasattr(tab.rows[0], "cells"):
                                df.attrs["col_x_boundaries"] = [(cell[0], cell[2]) for cell in tab.rows[0].cells]
                            else:
                                df.attrs["col_x_boundaries"] = None
                            raw_tables.append(df)
                except Exception as e:
                    logger.warning(
                        f"Table extraction failed on page {page_idx} of '{in_p.name}': {e}, skipping this page.",
                        exc_info=True,
                    )
                    page_errors.append((page_idx, str(e)))
                    continue

        doc.close()

        if not raw_tables:
            if page_errors:
                err_details = "; ".join(f"page {p}: {err}" for p, err in page_errors)
                raise RuntimeError(f"Table extraction failed across document '{in_p.name}': {err_details}")
            raise ValueError(f"No structured tables found in PDF '{in_p.name}' to extract.")

        if page_errors:
            extracted_pages = sorted(set(df.attrs.get("page_idx") for df in raw_tables))
            failed_pages = sorted(set(p for p, _ in page_errors))
            self.last_table_warning = (
                f"extracted {len(extracted_pages)} of {total_pages} pages; "
                f"page(s) {', '.join(str(p) for p in failed_pages)} failed"
            )
        else:
            self.last_table_warning = None

        def _norm_headers(cols):
            return [str(c).strip().lower() for c in cols]

        def _geom_matches(geom1, geom2, tol=5.0):
            if not geom1 or not geom2:
                return False
            if len(geom1) != len(geom2):
                return False
            return all(abs(g1[0] - g2[0]) <= tol and abs(g1[1] - g2[1]) <= tol for g1, g2 in zip(geom1, geom2))

        table_groups: List[pd.DataFrame] = []
        current_group: Optional[pd.DataFrame] = None

        for df in raw_tables:
            if df.empty:
                continue

            if current_group is None:
                current_group = df.copy()
                current_group.attrs["last_page_idx"] = df.attrs.get("page_idx")
                current_group.attrs["col_x_boundaries"] = df.attrs.get("col_x_boundaries")
                continue

            is_next_page = (df.attrs.get("page_idx") == current_group.attrs.get("last_page_idx", 0) + 1)
            same_col_count = (len(df.columns) == len(current_group.columns))
            geom_matches = _geom_matches(current_group.attrs.get("col_x_boundaries"), df.attrs.get("col_x_boundaries"))

            curr_cols = [str(c).strip() for c in current_group.columns]
            row0_vals = [str(v).strip() for v in df.iloc[0].values] if len(df) > 0 else []

            # Case 1: Repeated header as first row of continuation table
            if same_col_count and is_next_page and geom_matches and (curr_cols == row0_vals or _norm_headers(curr_cols) == _norm_headers(row0_vals)):
                df_clean = df.iloc[1:].copy()
                df_clean.columns = current_group.columns
                current_group = pd.concat([current_group, df_clean], ignore_index=True)
                current_group.attrs["last_page_idx"] = df.attrs.get("page_idx")

            # Case 2: Matching column headers (pure continuation)
            elif same_col_count and is_next_page and geom_matches and _norm_headers(current_group.columns) == _norm_headers(df.columns):
                df_clean = df.copy()
                df_clean.columns = current_group.columns
                current_group = pd.concat([current_group, df_clean], ignore_index=True)
                current_group.attrs["last_page_idx"] = df.attrs.get("page_idx")

            # Case 3: Headerless continuation (different header text promoted from data, but geometry & continuity match)
            elif same_col_count and is_next_page and geom_matches:
                raw_rows = df.attrs.get("raw_rows")
                if raw_rows and len(raw_rows) > 0:
                    df_reconstructed = pd.DataFrame(raw_rows, columns=current_group.columns)
                else:
                    full_data = [list(df.columns)] + df.values.tolist()
                    df_reconstructed = pd.DataFrame(full_data, columns=current_group.columns)
                current_group = pd.concat([current_group, df_reconstructed], ignore_index=True)
                current_group.attrs["last_page_idx"] = df.attrs.get("page_idx")

            else:
                # Criteria not met -> keep separate and log a warning
                logger.warning(
                    f"Table on page {df.attrs.get('page_idx')} was kept separate from previous table: "
                    f"same_col_count={same_col_count}, is_next_page={is_next_page}, geom_matches={geom_matches}."
                )
                table_groups.append(current_group)
                current_group = df.copy()
                current_group.attrs["last_page_idx"] = df.attrs.get("page_idx")
                current_group.attrs["col_x_boundaries"] = df.attrs.get("col_x_boundaries")

        if current_group is not None:
            table_groups.append(current_group)

        is_xlsx = target_format.upper() in ("XLSX", "EXCEL")

        if is_xlsx:
            if len(table_groups) == 1:
                table_groups[0].to_excel(str(out_p), index=False, sheet_name="Table_1")
            else:
                with pd.ExcelWriter(str(out_p), engine="openpyxl") as writer:
                    for idx, grp_df in enumerate(table_groups, 1):
                        sheet_name = f"Table_{idx}"
                        grp_df.to_excel(writer, sheet_name=sheet_name, index=False)
        else:
            # CSV export with atomic write, side files, and manifest-based stale file cleanup (C3)
            # 1. Clear ONLY side files recorded in the manifest from earlier runs of this tool
            import json
            manifest_file = out_p.parent / f".{out_p.stem}_tables_manifest.json"
            if manifest_file.is_file():
                try:
                    with open(manifest_file, "r", encoding="utf-8") as mf:
                        stale_names = json.load(mf)
                    for sname in stale_names:
                        if sname != out_p.name:
                            sp = out_p.parent / sname
                            if sp.is_file():
                                try:
                                    sp.unlink()
                                except Exception as unlink_err:
                                    logger.warning(f"Could not remove stale side file {sp}: {unlink_err}")
                except Exception as e:
                    logger.warning(f"Error reading tables manifest {manifest_file}: {e}")

            # 2. Atomic write for all CSV files (primary + side files)
            import time
            temp_files: List[Tuple[Path, Path]] = []
            pid = os.getpid()
            ts = time.time_ns()
            side_manifest: List[str] = [out_p.name]

            try:
                # Primary file temp
                temp_primary = out_p.with_name(f".tmp_tab_{pid}_{ts}_{out_p.name}")
                table_groups[0].to_csv(str(temp_primary), index=False, encoding="utf-8-sig")
                temp_files.append((temp_primary, out_p))

                # Side files if multiple tables
                if len(table_groups) > 1:
                    for idx, grp_df in enumerate(table_groups, 1):
                        side_p = out_p.parent / f"{out_p.stem}_table{idx}.csv"
                        side_manifest.append(side_p.name)
                        temp_side = side_p.with_name(f".tmp_tab_{pid}_{ts}_{side_p.name}")
                        grp_df.to_csv(str(temp_side), index=False, encoding="utf-8-sig")
                        temp_files.append((temp_side, side_p))

                # Atomically replace all files
                for tmp_f, final_f in temp_files:
                    os.replace(str(tmp_f), str(final_f))

                # Record manifest of side files written
                try:
                    manifest_file.write_text(json.dumps(side_manifest), encoding="utf-8")
                except Exception as e:
                    logger.warning(f"Failed to write tables manifest {manifest_file}: {e}")

                if len(table_groups) > 1:
                    side_msg = f"Extracted {len(table_groups)} tables. Side files: {', '.join(side_manifest[1:])}"
                    logger.info(
                        f"Extracted {len(table_groups)} tables from '{in_p.name}'. "
                        f"Produced primary '{out_p.name}' and side files: {side_manifest[1:]}."
                    )
                    if self.last_table_warning:
                        self.last_table_warning = f"{self.last_table_warning}; {side_msg}"
                    else:
                        self.last_table_warning = side_msg
            except Exception:
                # Mid-write failure cleanup: unlink all temporary files
                for tmp_f, _ in temp_files:
                    if tmp_f.exists():
                        try:
                            tmp_f.unlink()
                        except Exception as unlink_err:
                            logger.warning(f"Could not remove temporary file {tmp_f}: {unlink_err}")
                raise

        return out_p

    # -------------------------------------------------------------------------
    # Word (DOCX) Input Conversions
    # -------------------------------------------------------------------------

    def convert_docx_to_pdf(
        self,
        docx_path: str | Path,
        output_path: str | Path,
    ) -> Path:
        """Convert DOCX to PDF using native MS Word COM automation."""
        in_p = Path(docx_path).resolve()
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)

        check_docx_encryption(in_p)

        if sys.platform == "win32":
            from image_converter.core.com_utils import (
                com_initialized,
                WD_ALERTS_NONE,
                MSO_AUTOMATION_SECURITY_FORCE_DISABLE,
                WD_FORMAT_PDF,
            )
            with com_initialized():
                import win32com.client
                try:
                    word = win32com.client.DispatchEx("Word.Application")
                except Exception as dispatch_err:
                    logger.warning(f"Word COM not available: {dispatch_err}")
                    word = None

                if word is not None:
                    try:
                        word.Visible = False
                        word.DisplayAlerts = WD_ALERTS_NONE
                        word.AutomationSecurity = MSO_AUTOMATION_SECURITY_FORCE_DISABLE
                        doc = None
                        tmp_out = out_p.with_name(f"{out_p.stem}_tmp_{os.getpid()}_{time.time_ns()}.pdf")
                        try:
                            try:
                                doc = word.Documents.Open(str(in_p), ReadOnly=True)
                                doc.SaveAs(str(tmp_out), FileFormat=WD_FORMAT_PDF)
                            finally:
                                if doc is not None:
                                    try:
                                        doc.Close(False)
                                    except Exception as close_err:
                                        logger.warning(f"Error closing Word document: {close_err}")
                            if tmp_out.is_file() and tmp_out.stat().st_size > 0:
                                os.replace(tmp_out, out_p)
                        finally:
                            if tmp_out.exists():
                                try:
                                    tmp_out.unlink()
                                except Exception as unlink_err:
                                    logger.warning(f"Could not remove temporary file {tmp_out}: {unlink_err}")
                    except Exception as e:
                        logger.warning(f"MS Word COM DOCX-to-PDF conversion failed for {in_p.name}: {e}", exc_info=True)
                        raise RuntimeError(f"Microsoft Word conversion failed for '{in_p.name}': {e}") from e
                    finally:
                        doc = None
                        try:
                            word.Quit()
                        except Exception as quit_err:
                            logger.warning(f"Error quitting Word application: {quit_err}")
                        word = None
                        import gc
                        gc.collect()
                    if out_p.is_file() and out_p.stat().st_size > 0:
                        return out_p

        raise RuntimeError("Native DOCX to PDF conversion requires Microsoft Word on Windows.")

    def convert_docx_to_text(
        self,
        docx_path: str | Path,
        output_path: str | Path,
    ) -> Path:
        """Extract plain text from DOCX document."""
        if not self.has_docx:
            raise RuntimeError("python-docx is required for DOCX to text conversion.")

        in_p = Path(docx_path).resolve()
        check_docx_encryption(in_p)
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)

        doc = docx.Document(str(in_p))
        lines: List[str] = []

        for p in doc.paragraphs:
            txt = p.text.strip()
            if txt:
                lines.append(txt)

        for tbl in doc.tables:
            lines.append("\n[Table]")
            for row in tbl.rows:
                row_str = " | ".join(cell.text.strip() for cell in row.cells)
                lines.append(row_str)
            lines.append("")

        out_p.write_text("\n\n".join(lines), encoding="utf-8")
        return out_p

    def convert_docx_to_html(
        self,
        docx_path: str | Path,
        output_path: str | Path,
    ) -> Path:
        """Convert DOCX structure into a clean, modern HTML document."""
        if not self.has_docx:
            raise RuntimeError("python-docx is required for DOCX to HTML conversion.")

        in_p = Path(docx_path).resolve()
        check_docx_encryption(in_p)
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)

        doc = docx.Document(str(in_p))
        body_elements: List[str] = []

        for p in doc.paragraphs:
            txt = html.escape(p.text.strip())
            if not txt:
                continue
            style_name = (p.style.name if p.style else "").lower()
            if "heading 1" in style_name:
                body_elements.append(f"<h1>{txt}</h1>")
            elif "heading 2" in style_name:
                body_elements.append(f"<h2>{txt}</h2>")
            elif "heading 3" in style_name:
                body_elements.append(f"<h3>{txt}</h3>")
            else:
                body_elements.append(f"<p>{txt}</p>")

        for tbl in doc.tables:
            tbl_html = ['<table border="1" cellpadding="6" cellspacing="0" style="border-collapse: collapse; margin: 16px 0;">']
            for r_idx, row in enumerate(tbl.rows):
                tbl_html.append("  <tr>")
                tag = "th" if r_idx == 0 else "td"
                for cell in row.cells:
                    c_txt = html.escape(cell.text.strip())
                    tbl_html.append(f"    <{tag}>{c_txt}</{tag}>")
                tbl_html.append("  </tr>")
            tbl_html.append("</table>")
            body_elements.append("\n".join(tbl_html))

        doc_title = html.escape(in_p.stem)
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{doc_title}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      line-height: 1.6;
      color: #1f2937;
      max-width: 800px;
      margin: 40px auto;
      padding: 0 20px;
    }}
    h1, h2, h3 {{ color: #111827; }}
    table {{ width: 100%; border-color: #e5e7eb; }}
    th {{ background: #f3f4f6; text-align: left; }}
    p {{ margin: 0.8em 0; }}
  </style>
</head>
<body>
  {chr(10).join(body_elements)}
</body>
</html>"""

        out_p.write_text(html_content, encoding="utf-8")
        return out_p

    def convert_docx_to_images(
        self,
        docx_path: str | Path,
        output_path: str | Path,
        target_format: str = "PNG",
        dpi: int = 150,
    ) -> List[Path]:
        """Convert DOCX to images by rendering through PDF intermediary."""
        in_p = Path(docx_path).resolve()
        check_docx_encryption(in_p)
        with tempfile.TemporaryDirectory() as td:
            temp_pdf = Path(td) / "temp_render.pdf"
            self.convert_docx_to_pdf(in_p, temp_pdf)
            return self.convert_pdf_to_images(
                temp_pdf,
                output_path,
                target_format=target_format,
                dpi=dpi,
            )
