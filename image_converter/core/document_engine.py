"""
Document conversion engine for PDF and Word (.docx) files.
Supports converting between PDF, Word, Images, Plain Text, HTML, CSV, and XLSX.
"""

from __future__ import annotations

import html
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import fitz  # PyMuPDF
from PIL import Image

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


def get_pdf_metadata(file_path: str | Path) -> Dict[str, Any]:
    """Extract metadata, page count, and dimensions from a PDF document."""
    p = Path(file_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"PDF file not found: {file_path}")

    doc = fitz.open(str(p))
    page_count = len(doc)
    w, h = 0, 0
    if page_count > 0:
        first_page = doc[0]
        rect = first_page.rect
        w = int(rect.width)
        h = int(rect.height)

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
        "has_alpha": False,
    }


def get_docx_metadata(file_path: str | Path) -> Dict[str, Any]:
    """Extract metadata, paragraph count, and word estimate from a DOCX document."""
    p = Path(file_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"DOCX file not found: {file_path}")

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
        except Exception:
            pass

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

        doc = fitz.open(str(in_p))
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
    ) -> Path:
        """
        Convert PDF to DOCX using pdf2docx with PyMuPDF/python-docx fallback.
        """
        in_p = Path(pdf_path).resolve()
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)

        # Primary: pdf2docx Converter
        if self.has_pdf2docx:
            try:
                cv = PDF2DocxConverter(str(in_p))
                cv.convert(str(out_p))
                cv.close()
                if out_p.is_file() and out_p.stat().st_size > 0:
                    return out_p
            except Exception:
                pass

        # Fallback: extract text & tables using PyMuPDF and assemble docx
        if not self.has_docx:
            raise RuntimeError("python-docx is required for PDF to DOCX conversion.")

        doc = fitz.open(str(in_p))
        docx_doc = docx.Document()

        for page in doc:
            # Extract tables first if available
            table_rects = []
            if hasattr(page, "find_tables"):
                try:
                    tabs = page.find_tables()
                    for tab in tabs:
                        df = tab.to_pandas()
                        if not df.empty:
                            table_rects.append(tab.bbox)
                            t = docx_doc.add_table(rows=len(df) + 1, cols=len(df.columns))
                            t.style = "Table Grid"
                            for col_idx, col_name in enumerate(df.columns):
                                t.cell(0, col_idx).text = str(col_name)
                            for row_idx, row in df.iterrows():
                                for col_idx, val in enumerate(row):
                                    t.cell(row_idx + 1, col_idx).text = "" if str(val) == "nan" else str(val)
                            docx_doc.add_paragraph()
                except Exception:
                    pass

            # Extract paragraphs / blocks
            blocks = page.get_text("blocks")
            for b in blocks:
                text = b[4].strip()
                if not text:
                    continue
                # Skip if inside an extracted table
                bx0, by0, bx1, by1 = b[0], b[1], b[2], b[3]
                in_table = any(
                    bx0 >= tx0 and by0 >= ty0 and bx1 <= tx1 and by1 <= ty1
                    for (tx0, ty0, tx1, ty1) in table_rects
                )
                if not in_table:
                    docx_doc.add_paragraph(text)

        doc.close()
        docx_doc.save(str(out_p))
        return out_p

    def convert_pdf_to_text(
        self,
        pdf_path: str | Path,
        output_path: str | Path,
    ) -> Path:
        """Extract all textual content from a PDF into a UTF-8 text file."""
        in_p = Path(pdf_path).resolve()
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)

        doc = fitz.open(str(in_p))
        full_text: List[str] = []

        for idx, page in enumerate(doc, 1):
            page_text = page.get_text("text").strip()
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
    ) -> Path:
        """Extract structured tables from PDF into CSV or XLSX format."""
        import pandas as pd

        in_p = Path(pdf_path).resolve()
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)

        doc = fitz.open(str(in_p))
        dfs: List[pd.DataFrame] = []

        for page in doc:
            if hasattr(page, "find_tables"):
                try:
                    tabs = page.find_tables()
                    for tab in tabs:
                        df = tab.to_pandas()
                        if not df.empty:
                            dfs.append(df)
                except Exception:
                    pass

        doc.close()

        if not dfs:
            # Fallback: create single-column table from text lines
            text_lines = [line.strip() for line in in_p.read_bytes().decode("utf-8", errors="ignore").splitlines() if line.strip()]
            combined_df = pd.DataFrame({"Extracted Text": text_lines})
        elif len(dfs) == 1:
            combined_df = dfs[0]
        else:
            combined_df = pd.concat(dfs, ignore_index=True)

        if target_format.upper() in ("XLSX", "EXCEL"):
            combined_df.to_excel(str(out_p), index=False)
        else:
            combined_df.to_csv(str(out_p), index=False, encoding="utf-8-sig")

        return out_p

    # -------------------------------------------------------------------------
    # Word (DOCX) Input Conversions
    # -------------------------------------------------------------------------

    def convert_docx_to_pdf(
        self,
        docx_path: str | Path,
        output_path: str | Path,
        use_ms_word: bool = False,
    ) -> Path:
        """
        Convert DOCX to PDF.
        Uses pure-Python python-docx + ReportLab by default for fast, reliable,
        headless conversion without Microsoft Office dependencies.
        """
        in_p = Path(docx_path).resolve()
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)

        if use_ms_word and sys.platform == "win32":
            try:
                import win32com.client
                word = win32com.client.DispatchEx("Word.Application")
                word.Visible = False
                word.DisplayAlerts = 0
                try:
                    doc = word.Documents.Open(str(in_p), ReadOnly=True)
                    doc.SaveAs(str(out_p), FileFormat=17)
                    doc.Close(False)
                    if out_p.is_file() and out_p.stat().st_size > 0:
                        return out_p
                finally:
                    word.Quit()
            except Exception:
                pass

        if not self.has_docx:
            raise RuntimeError("python-docx is required for reading DOCX files.")
        if not self.has_reportlab:
            raise RuntimeError("reportlab is required for pure Python PDF generation.")

        return self._docx_to_pdf_pure_python(in_p, out_p)

    def _docx_to_pdf_pure_python(self, in_path: Path, out_path: Path) -> Path:
        """Render DOCX paragraphs, headings, and tables into a clean ReportLab PDF."""
        doc = docx.Document(str(in_path))
        styles = getSampleStyleSheet()

        normal_style = styles["Normal"]
        normal_style.fontSize = 10
        normal_style.leading = 13
        normal_style.textColor = colors.HexColor("#1e293b")

        h1_style = ParagraphStyle(
            "DocH1",
            parent=styles["Heading1"],
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#0f172a"),
            spaceAfter=10,
            spaceBefore=14,
        )
        h2_style = ParagraphStyle(
            "DocH2",
            parent=styles["Heading2"],
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#1e293b"),
            spaceAfter=6,
            spaceBefore=10,
        )

        story = []

        # Iterate through paragraphs and tables
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                story.append(Spacer(1, 6))
                continue

            style_name = (para.style.name if para.style else "").lower()
            if "heading 1" in style_name:
                p_style = h1_style
            elif "heading 2" in style_name or "heading 3" in style_name:
                p_style = h2_style
            else:
                p_style = normal_style

            # Escape HTML entities for ReportLab Paragraph
            safe_text = html.escape(text)
            story.append(Paragraph(safe_text, p_style))
            story.append(Spacer(1, 4))

        for tbl in doc.tables:
            table_data = []
            for row in tbl.rows:
                row_cells = []
                for cell in row.cells:
                    cell_text = html.escape(cell.text.strip())
                    row_cells.append(Paragraph(cell_text, normal_style))
                table_data.append(row_cells)

            if table_data:
                rl_table = RLTable(table_data)
                rl_table.setStyle(RLTableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ]))
                story.append(Spacer(1, 8))
                story.append(rl_table)
                story.append(Spacer(1, 10))

        if not story:
            story.append(Paragraph("Empty Document", normal_style))

        pdf_doc = SimpleDocTemplate(
            str(out_path),
            pagesize=letter,
            leftMargin=40,
            rightMargin=40,
            topMargin=40,
            bottomMargin=40,
        )
        pdf_doc.build(story)
        return out_path

    def convert_docx_to_text(
        self,
        docx_path: str | Path,
        output_path: str | Path,
    ) -> Path:
        """Extract plain text from DOCX document."""
        if not self.has_docx:
            raise RuntimeError("python-docx is required for DOCX to text conversion.")

        in_p = Path(docx_path).resolve()
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
        with tempfile.TemporaryDirectory() as td:
            temp_pdf = Path(td) / "temp_render.pdf"
            self.convert_docx_to_pdf(docx_path, temp_pdf)
            return self.convert_pdf_to_images(
                temp_pdf,
                output_path,
                target_format=target_format,
                dpi=dpi,
            )
