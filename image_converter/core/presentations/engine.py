"""
Presentation conversion engine for PowerPoint (.pptx) files.
Supports converting between PPTX, PDF, Text, HTML, and Images.
"""

from __future__ import annotations

import html
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from PIL import Image

logger = logging.getLogger(__name__)

# Single-instance COM server protection lock for PowerPoint
_ppt_com_lock = threading.Lock()

_PPTX_AVAILABLE = False
try:
    import pptx
    from pptx import Presentation
    from pptx.util import Inches, Pt
    _PPTX_AVAILABLE = True
except ImportError:
    pass

# ReportLab for PPTX -> PDF rendering
_REPORTLAB_AVAILABLE = False
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table as RLTable,
        TableStyle as RLTableStyle,
    )
    _REPORTLAB_AVAILABLE = True
except ImportError:
    pass


def get_pptx_metadata(file_path: str | Path) -> Dict[str, Any]:
    """Extract metadata, slide count, and title from a PPTX file."""
    p = Path(file_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"PPTX file not found: {file_path}")

    file_size = p.stat().st_size
    slide_count = 0
    title = ""

    if _PPTX_AVAILABLE:
        try:
            prs = Presentation(str(p))
            slide_count = len(prs.slides)
            if slide_count > 0:
                first_slide = prs.slides[0]
                for shape in first_slide.shapes:
                    if shape.has_text_frame and shape.text.strip():
                        title = shape.text.strip().split("\n")[0]
                        break
        except Exception as e:
            logger.warning(f"Error extracting PPTX metadata for {p.name}: {e}", exc_info=True)

    return {
        "file_name": p.name,
        "file_path": str(p),
        "file_size": file_size,
        "slide_count": slide_count,
        "page_count": slide_count,
        "width": 1024,
        "height": 768,
        "format": "PPTX",
        "title": title or p.stem,
        "has_alpha": False,
    }


class PresentationConverter:
    """Core presentation conversion engine handling PowerPoint (.pptx) files."""

    def __init__(self):
        self.has_pptx = _PPTX_AVAILABLE
        self.has_reportlab = _REPORTLAB_AVAILABLE

    def _ensure_pptx(self):
        if not self.has_pptx:
            raise RuntimeError("python-pptx is required for PowerPoint presentation processing.")

    def convert_pptx_to_text(
        self,
        pptx_path: str | Path,
        output_path: str | Path,
    ) -> Path:
        """Extract all textual content from PPTX slides into a structured text file."""
        self._ensure_pptx()
        in_p = Path(pptx_path).resolve()
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)

        prs = Presentation(str(in_p))
        lines: List[str] = []

        for idx, slide in enumerate(prs.slides, 1):
            slide_texts = []
            for shape in slide.shapes:
                if shape.has_text_frame:
                    txt = shape.text.strip()
                    if txt:
                        slide_texts.append(txt)
                elif shape.has_table:
                    table_rows = []
                    for row in shape.table.rows:
                        row_str = " | ".join(c.text.strip() for c in row.cells)
                        table_rows.append(row_str)
                    if table_rows:
                        slide_texts.append("\n".join(table_rows))

            notes_text = ""
            if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
                n_txt = slide.notes_slide.notes_text_frame.text.strip()
                if n_txt:
                    notes_text = f"\n[Notes]: {n_txt}"

            joined_content = "\n".join(slide_texts)
            lines.append(f"=== Slide {idx} ===\n{joined_content}{notes_text}\n")

        out_p.write_text("\n".join(lines), encoding="utf-8")
        return out_p

    def convert_pptx_to_html(
        self,
        pptx_path: str | Path,
        output_path: str | Path,
    ) -> Path:
        """Convert PPTX presentation into a responsive slide-deck HTML view."""
        self._ensure_pptx()
        in_p = Path(pptx_path).resolve()
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)

        prs = Presentation(str(in_p))
        slide_cards = []

        for idx, slide in enumerate(prs.slides, 1):
            slide_items = []
            for shape in slide.shapes:
                if shape.has_text_frame:
                    paragraphs = []
                    for p in shape.text_frame.paragraphs:
                        p_txt = html.escape(p.text.strip())
                        if p_txt:
                            if p.level == 0 and len(p_txt) < 80 and not slide_items:
                                paragraphs.append(f"<h2>{p_txt}</h2>")
                            else:
                                paragraphs.append(f"<p>{p_txt}</p>")
                    if paragraphs:
                        slide_items.append("\n".join(paragraphs))
                elif shape.has_table:
                    tbl_lines = ['<table border="1" cellpadding="6" cellspacing="0">']
                    for row in shape.table.rows:
                        tbl_lines.append("<tr>" + "".join(f"<td>{html.escape(c.text.strip())}</td>" for c in row.cells) + "</tr>")
                    tbl_lines.append("</table>")
                    slide_items.append("\n".join(tbl_lines))

            content_html = "\n".join(slide_items) or "<p><em>(Empty Slide)</em></p>"
            card = f"""
<div class="slide-card">
  <div class="slide-number">Slide {idx}</div>
  <div class="slide-content">
    {content_html}
  </div>
</div>
"""
            slide_cards.append(card)

        doc_title = html.escape(in_p.stem)
        full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{doc_title}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background-color: #0f172a;
      color: #e2e8f0;
      padding: 30px 20px;
      margin: 0;
    }}
    .container {{ max-width: 900px; margin: 0 auto; }}
    h1 {{ text-align: center; color: #f8fafc; margin-bottom: 30px; }}
    .slide-card {{
      background-color: #1e293b;
      border-radius: 10px;
      padding: 24px;
      margin-bottom: 24px;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
      border: 1px solid #334155;
    }}
    .slide-number {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 1px;
      color: #818cf8;
      font-weight: 600;
      margin-bottom: 12px;
    }}
    h2 {{ color: #f1f5f9; margin-top: 0; }}
    table {{ width: 100%; border-collapse: collapse; border-color: #475569; margin: 12px 0; }}
    td {{ padding: 6px 10px; border: 1px solid #475569; }}
    p {{ line-height: 1.5; }}
  </style>
</head>
<body>
  <div class="container">
    <h1>{doc_title}</h1>
    {"".join(slide_cards)}
  </div>
</body>
</html>"""

        out_p.write_text(full_html, encoding="utf-8")
        return out_p

    def convert_pptx_to_pdf(
        self,
        pptx_path: str | Path,
        output_path: str | Path,
    ) -> Path:
        """Render PPTX slides into a PDF presentation natively via COM."""
        in_p = Path(pptx_path).resolve()
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)

        if os.name == "nt":
            import time
            from image_converter.core.com_utils import (
                com_initialized,
                PP_ALERTS_NONE,
                MSO_AUTOMATION_SECURITY_FORCE_DISABLE,
                PP_SAVE_AS_PDF,
            )
            with _ppt_com_lock:
                with com_initialized():
                    import win32com.client
                    try:
                        powerpoint = win32com.client.DispatchEx("Powerpoint.Application")
                    except Exception as dispatch_err:
                        logger.warning(f"PowerPoint COM not available: {dispatch_err}")
                        powerpoint = None

                    if powerpoint is not None:
                        try:
                            powerpoint.DisplayAlerts = PP_ALERTS_NONE
                            powerpoint.AutomationSecurity = MSO_AUTOMATION_SECURITY_FORCE_DISABLE
                            presentation = None
                            tmp_out = out_p.with_name(f"{out_p.stem}_tmp_{os.getpid()}_{time.time_ns()}.pdf")
                            try:
                                try:
                                    presentation = powerpoint.Presentations.Open(str(in_p), ReadOnly=True, WithWindow=False)
                                    presentation.SaveAs(str(tmp_out), PP_SAVE_AS_PDF)
                                finally:
                                    if presentation is not None:
                                        try:
                                            presentation.Close()
                                        except Exception as close_err:
                                            logger.warning(f"Error closing PowerPoint presentation: {close_err}")
                                if tmp_out.is_file() and tmp_out.stat().st_size > 0:
                                    os.replace(tmp_out, out_p)
                            finally:
                                if tmp_out.exists():
                                    try:
                                        tmp_out.unlink()
                                    except Exception as unlink_err:
                                        logger.warning(f"Could not remove temporary file {tmp_out}: {unlink_err}")
                        except Exception as e:
                            logger.warning(f"MS PowerPoint COM conversion failed for {in_p.name}: {e}", exc_info=True)
                            raise RuntimeError(f"Microsoft PowerPoint conversion failed for '{in_p.name}': {e}") from e
                        finally:
                            presentation = None
                            try:
                                powerpoint.Quit()
                            except Exception as quit_err:
                                logger.warning(f"Error quitting PowerPoint application: {quit_err}")
                            powerpoint = None
                        if out_p.is_file() and out_p.stat().st_size > 0:
                            return out_p

        raise RuntimeError("Native PPTX to PDF conversion requires Microsoft PowerPoint on Windows.")

    def convert_pptx_to_images(
        self,
        pptx_path: str | Path,
        output_path: str | Path,
        target_format: str = "PNG",
        dpi: int = 150,
    ) -> List[Path]:
        """Convert PPTX to images by rendering through PDF intermediary."""
        import fitz
        with tempfile.TemporaryDirectory() as td:
            temp_pdf = Path(td) / "temp_pptx_render.pdf"
            self.convert_pptx_to_pdf(pptx_path, temp_pdf)

            # Render PDF to images
            doc = fitz.open(str(temp_pdf))
            out_p = Path(output_path).resolve()
            out_p.parent.mkdir(parents=True, exist_ok=True)

            scale = dpi / 72.0
            matrix = fitz.Matrix(scale, scale)
            ext = f".{target_format.lower()}"
            if ext == ".jpeg":
                ext = ".jpg"

            base_stem = out_p.stem if out_p.suffix else Path(pptx_path).stem
            out_dir = out_p.parent if out_p.suffix else out_p
            generated: List[Path] = []

            for idx, page in enumerate(doc):
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                if len(doc) == 1 and out_p.suffix:
                    dest = out_p
                else:
                    dest = out_dir / f"{base_stem}_slide_{idx + 1}{ext}"
                pix.save(str(dest))
                generated.append(dest)

            doc.close()
            return generated

    def convert_text_to_pptx(
        self,
        text_or_path: Union[str, Path],
        output_path: str | Path,
    ) -> Path:
        """Create a PPTX presentation from a plain text file or string."""
        self._ensure_pptx()
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(text_or_path, (str, Path)) and Path(text_or_path).is_file():
            content = Path(text_or_path).read_text(encoding="utf-8", errors="ignore")
        else:
            content = str(text_or_path)

        prs = Presentation()
        blank_slide_layout = prs.slide_layouts[1]  # Title and Content layout

        # Split into slides by '=== Slide' or double newlines
        sections = [s.strip() for s in content.split("=== Slide") if s.strip()]
        if not sections:
            sections = [s.strip() for s in content.split("\n\n\n") if s.strip()]
        if not sections:
            sections = [content.strip()]

        for sec in sections:
            lines = [l.strip() for l in sec.splitlines() if l.strip()]
            if not lines:
                continue

            slide = prs.slides.add_slide(blank_slide_layout)
            title = lines[0].lstrip("0123456789= :.-")
            slide.shapes.title.text = title or "Slide"

            if len(lines) > 1:
                tf = slide.shapes.placeholders[1].text_frame
                tf.clear()
                for body_line in lines[1:10]:
                    p = tf.add_paragraph()
                    p.text = body_line.lstrip("•-* ")

        prs.save(str(out_p))
        return out_p
