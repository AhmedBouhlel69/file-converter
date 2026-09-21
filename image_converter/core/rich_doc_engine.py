"""
Rich document conversion engine for OpenDocument (.odt) and Rich Text Format (.rtf) files.
Supports converting between ODT, RTF, PDF, Word (DOCX), and Plain Text.
"""

from __future__ import annotations

import html
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

# striprtf for RTF reading
_STRIPRTF_AVAILABLE = False
try:
    from striprtf.striprtf import rtf_to_text
    _STRIPRTF_AVAILABLE = True
except ImportError:
    pass

# odfpy for ODT reading and writing
_ODFPY_AVAILABLE = False
try:
    from odf import opendocument, teletype, text as odf_text
    _ODFPY_AVAILABLE = True
except ImportError:
    pass

# python-docx for DOCX interoperability
_DOCX_AVAILABLE = False
try:
    import docx
    _DOCX_AVAILABLE = True
except ImportError:
    pass

# ReportLab for PDF generation
_REPORTLAB_AVAILABLE = False
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    _REPORTLAB_AVAILABLE = True
except ImportError:
    pass


def get_rtf_metadata(file_path: str | Path) -> Dict[str, Any]:
    """Extract metadata and word count estimate from an RTF document."""
    p = Path(file_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"RTF file not found: {file_path}")

    file_size = p.stat().st_size
    word_count = 0
    line_count = 0

    if _STRIPRTF_AVAILABLE:
        try:
            raw = p.read_text(encoding="utf-8", errors="ignore")
            plain = rtf_to_text(raw)
            words = plain.split()
            word_count = len(words)
            line_count = len(plain.splitlines())
        except Exception as e:
            logger.warning(f"Error extracting RTF metadata for {p.name}: {e}", exc_info=True)

    return {
        "file_name": p.name,
        "file_path": str(p),
        "file_size": file_size,
        "format": "RTF",
        "word_count": word_count,
        "line_count": line_count,
        "page_count": max(1, word_count // 250 + 1),
        "has_alpha": False,
    }


def get_odt_metadata(file_path: str | Path) -> Dict[str, Any]:
    """Extract metadata and paragraph count from an OpenDocument Text (ODT) file."""
    p = Path(file_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"ODT file not found: {file_path}")

    file_size = p.stat().st_size
    para_count = 0
    word_count = 0

    if _ODFPY_AVAILABLE:
        try:
            doc = opendocument.load(str(p))
            paras = doc.getElementsByType(odf_text.P)
            para_count = len(paras)
            all_text = " ".join(teletype.extractText(p) for p in paras)
            word_count = len(all_text.split())
        except Exception as e:
            logger.warning(f"Error extracting ODT metadata for {p.name}: {e}", exc_info=True)

    return {
        "file_name": p.name,
        "file_path": str(p),
        "file_size": file_size,
        "format": "ODT",
        "paragraphs": para_count,
        "word_count": word_count,
        "page_count": max(1, word_count // 250 + 1),
        "has_alpha": False,
    }


class RichDocumentConverter:
    """Conversion engine for ODT and RTF documents."""

    def __init__(self):
        self.has_striprtf = _STRIPRTF_AVAILABLE
        self.has_odfpy = _ODFPY_AVAILABLE
        self.has_docx = _DOCX_AVAILABLE
        self.has_reportlab = _REPORTLAB_AVAILABLE

    # -------------------------------------------------------------------------
    # RTF Conversions
    # -------------------------------------------------------------------------

    def convert_rtf_to_text(
        self,
        rtf_path: str | Path,
        output_path: str | Path,
    ) -> Path:
        """Extract plain text from RTF file."""
        if not self.has_striprtf:
            raise RuntimeError("striprtf is required for reading RTF files.")

        in_p = Path(rtf_path).resolve()
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)

        raw = in_p.read_text(encoding="utf-8", errors="ignore")
        plain = rtf_to_text(raw).strip()
        out_p.write_text(plain, encoding="utf-8")
        return out_p

    def convert_rtf_to_pdf(
        self,
        rtf_path: str | Path,
        output_path: str | Path,
    ) -> Path:
        """Convert RTF document to PDF natively via MS Word COM."""
        return self._word_com_convert(rtf_path, output_path, format_code=17, format_name="PDF")

    def convert_rtf_to_docx(
        self,
        rtf_path: str | Path,
        output_path: str | Path,
    ) -> Path:
        """Convert RTF document to DOCX natively via MS Word COM."""
        return self._word_com_convert(rtf_path, output_path, format_code=16, format_name="DOCX")

    def convert_text_to_rtf(
        self,
        text_or_path: Union[str, Path],
        output_path: str | Path,
    ) -> Path:
        """Create an RTF file from plain text."""
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(text_or_path, (str, Path)) and Path(text_or_path).is_file():
            content = Path(text_or_path).read_text(encoding="utf-8", errors="ignore")
        else:
            content = str(text_or_path)

        # Basic RTF envelope
        escaped_lines = []
        for line in content.splitlines():
            clean = line.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
            escaped_lines.append(f"{clean}\\par")

        rtf_body = "\n".join(escaped_lines)
        rtf_doc = f"{{\\rtf1\\ansi\\deff0\n{{\\fonttbl{{\\f0\\fnil\\fcharset0 Calibri;}}}}\n\\viewkind4\\uc1\\pard\\f0\\fs22 {rtf_body}\n}}"

        out_p.write_text(rtf_doc, encoding="utf-8")
        return out_p

    # -------------------------------------------------------------------------
    # ODT Conversions
    # -------------------------------------------------------------------------

    def convert_odt_to_text(
        self,
        odt_path: str | Path,
        output_path: str | Path,
    ) -> Path:
        """Extract plain text from an ODT file."""
        if not self.has_odfpy:
            raise RuntimeError("odfpy is required for reading ODT files.")

        in_p = Path(odt_path).resolve()
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)

        doc = opendocument.load(str(in_p))
        paragraphs = doc.getElementsByType(odf_text.P)
        lines = [teletype.extractText(p).strip() for p in paragraphs if teletype.extractText(p).strip()]

        out_p.write_text("\n\n".join(lines), encoding="utf-8")
        return out_p

    def convert_odt_to_pdf(
        self,
        odt_path: str | Path,
        output_path: str | Path,
    ) -> Path:
        """Convert ODT document to PDF natively via MS Word COM."""
        return self._word_com_convert(odt_path, output_path, format_code=17, format_name="PDF")

    def convert_odt_to_docx(
        self,
        odt_path: str | Path,
        output_path: str | Path,
    ) -> Path:
        """Convert ODT document to DOCX natively via MS Word COM."""
        return self._word_com_convert(odt_path, output_path, format_code=16, format_name="DOCX")

    def convert_docx_to_odt(
        self,
        docx_path: str | Path,
        output_path: str | Path,
    ) -> Path:
        """Convert DOCX document to ODT format natively via MS Word COM."""
        return self._word_com_convert(docx_path, output_path, format_code=23, format_name="ODT")

    def convert_docx_to_rtf(
        self,
        docx_path: str | Path,
        output_path: str | Path,
    ) -> Path:
        """Convert DOCX document to RTF format natively via MS Word COM."""
        return self._word_com_convert(docx_path, output_path, format_code=6, format_name="RTF")

    def convert_odt_to_rtf(
        self,
        odt_path: str | Path,
        output_path: str | Path,
    ) -> Path:
        """Convert ODT document to RTF format natively via MS Word COM."""
        return self._word_com_convert(odt_path, output_path, format_code=6, format_name="RTF")

    def convert_rtf_to_odt(
        self,
        rtf_path: str | Path,
        output_path: str | Path,
    ) -> Path:
        """Convert RTF document to ODT format natively via MS Word COM."""
        return self._word_com_convert(rtf_path, output_path, format_code=23, format_name="ODT")
        
    def _word_com_convert(self, input_path: str | Path, output_path: str | Path, format_code: int, format_name: str) -> Path:
        """Helper to use Word COM for conversions."""
        in_p = Path(input_path).resolve()
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        
        import os
        import time
        if os.name == "nt":
            from image_converter.core.com_utils import (
                com_initialized,
                WD_ALERTS_NONE,
                MSO_AUTOMATION_SECURITY_FORCE_DISABLE,
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
                        tmp_out = out_p.with_name(f"{out_p.stem}_tmp_{os.getpid()}_{time.time_ns()}{out_p.suffix}")
                        try:
                            try:
                                doc = word.Documents.Open(str(in_p), ReadOnly=True, ConfirmConversions=False)
                                doc.SaveAs(str(tmp_out), FileFormat=format_code)
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
                        logger.warning(f"MS Word COM conversion to {format_name} failed for {in_p.name}: {e}", exc_info=True)
                        raise RuntimeError(f"Microsoft Word conversion to {format_name} failed for '{in_p.name}': {e}") from e
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

        raise RuntimeError(f"Native conversion to {format_name} requires Microsoft Word on Windows.")

    def _text_to_pdf(self, text: str, out_path: Path, title: str) -> Path:
        """Render raw text into styled PDF."""
        styles = getSampleStyleSheet()
        normal = styles["Normal"]
        normal.fontSize = 10
        normal.leading = 14
        normal.textColor = colors.HexColor("#1e293b")

        h1 = ParagraphStyle(
            "DocTitle",
            parent=styles["Heading1"],
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#0f172a"),
            spaceAfter=12,
        )

        story = [Paragraph(html.escape(title), h1), Spacer(1, 8)]
        for para in text.splitlines():
            t = para.strip()
            if t:
                story.append(Paragraph(html.escape(t), normal))
                story.append(Spacer(1, 4))

        doc = SimpleDocTemplate(
            str(out_path),
            pagesize=letter,
            leftMargin=36,
            rightMargin=36,
            topMargin=36,
            bottomMargin=36,
        )
        doc.build(story)
        return out_path
