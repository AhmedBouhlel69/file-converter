"""
Core conversion engine supporting Images, PDF, Word, CSV, and XLSX.
Supports HEIC, JPG, PNG, WEBP, BMP, TIFF, GIF, ICO, PDF, DOCX, XLSX, CSV, TXT, JSON, and HTML.
"""

from __future__ import annotations

import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from PIL import Image, ImageOps

from .data_engine import (
    DataConverter,
    get_csv_metadata,
    get_excel_metadata,
)
from .document_engine import (
    DocumentConverter,
    get_docx_metadata,
    get_pdf_metadata,
)
from .presentation_engine import (
    PresentationConverter,
    get_pptx_metadata,
)
from .rich_doc_engine import (
    RichDocumentConverter,
    get_odt_metadata,
    get_rtf_metadata,
)
from .security import (
    SecurityError,
    validate_input_file,
    validate_output_path,
)
from .ocr_engine import (
    is_ocr_available,
    ocr_image_to_text,
)

# Safely register HEIC/HEIF support
_HEIF_AVAILABLE = False
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    _HEIF_AVAILABLE = True
except ImportError:
    pass

# Supported formats mapping
SUPPORTED_INPUT_FORMATS = {
    "JPEG": [".jpg", ".jpeg", ".jpe"],
    "PNG": [".png"],
    "HEIC": [".heic", ".heif"],
    "WEBP": [".webp"],
    "BMP": [".bmp", ".dib"],
    "TIFF": [".tiff", ".tif"],
    "GIF": [".gif"],
    "ICO": [".ico"],
    "PPM": [".ppm", ".pgm", ".pbm", ".pnm"],
    "TGA": [".tga"],
    "EPS": [".eps"],
    "PDF": [".pdf"],
    "WORD": [".docx", ".doc"],
    "CSV": [".csv"],
    "EXCEL": [".xlsx", ".xls"],
    "PRESENTATION": [".pptx"],
    "ODT": [".odt"],
    "RTF": [".rtf"],
    "TEXT": [".txt"],
}

SUPPORTED_OUTPUT_FORMATS = [
    "JPG",
    "PNG",
    "WEBP",
    "HEIC",
    "BMP",
    "TIFF",
    "GIF",
    "ICO",
    "PDF",
    "DOCX",
    "XLSX",
    "CSV",
    "TXT",
    "JSON",
    "HTML",
    "PPTX",
    "ODT",
    "RTF",
]

FORMAT_EXTENSIONS: Dict[str, str] = {
    "JPG": ".jpg",
    "JPEG": ".jpg",
    "PNG": ".png",
    "WEBP": ".webp",
    "HEIC": ".heic",
    "HEIF": ".heic",
    "BMP": ".bmp",
    "TIFF": ".tiff",
    "GIF": ".gif",
    "ICO": ".ico",
    "PDF": ".pdf",
    "DOCX": ".docx",
    "XLSX": ".xlsx",
    "CSV": ".csv",
    "TXT": ".txt",
    "JSON": ".json",
    "HTML": ".html",
    "PPTX": ".pptx",
    "ODT": ".odt",
    "RTF": ".rtf",
    "STRIP_METADATA": "",
    "CLEAN": "",
}

# Pillow save format identifier mapping
PILLOW_FORMAT_MAP: Dict[str, str] = {
    "JPG": "JPEG",
    "JPEG": "JPEG",
    "PNG": "PNG",
    "WEBP": "WEBP",
    "HEIC": "HEIF",
    "HEIF": "HEIF",
    "BMP": "BMP",
    "TIFF": "TIFF",
    "GIF": "GIF",
    "ICO": "ICO",
    "PDF": "PDF",
}

# Formats that do not support transparency / alpha channel
NON_ALPHA_FORMATS = {"JPEG", "JPG", "BMP"}

IMAGE_INPUT_EXTS = {
    ".jpg", ".jpeg", ".jpe", ".png", ".heic", ".heif", ".webp",
    ".bmp", ".dib", ".tiff", ".tif", ".gif", ".ico", ".ppm",
    ".pgm", ".pbm", ".pnm", ".tga", ".eps",
}


def get_supported_input_extensions() -> List[str]:
    """Return all valid input extensions in lowercase."""
    extensions = []
    for ext_list in SUPPORTED_INPUT_FORMATS.values():
        extensions.extend(ext_list)
    return sorted(list(set(extensions)))


def get_supported_output_formats() -> List[str]:
    """Return available output format identifiers."""
    formats = list(SUPPORTED_OUTPUT_FORMATS)
    if not _HEIF_AVAILABLE and "HEIC" in formats:
        formats.remove("HEIC")
    return formats


def get_image_metadata(file_path: str | Path) -> Dict[str, any]:
    """
    Read dimensions, mode, and metadata for images, PDFs, Word, CSV, Excel, PPTX, ODT, RTF, or TXT files.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = path.suffix.lower()

    if ext == ".pdf":
        return get_pdf_metadata(path)
    elif ext in (".docx", ".doc"):
        return get_docx_metadata(path)
    elif ext == ".csv":
        return get_csv_metadata(path)
    elif ext in (".xlsx", ".xls"):
        return get_excel_metadata(path)
    elif ext == ".pptx":
        return get_pptx_metadata(path)
    elif ext == ".odt":
        return get_odt_metadata(path)
    elif ext == ".rtf":
        return get_rtf_metadata(path)
    elif ext == ".txt":
        size = path.stat().st_size
        text = path.read_text(encoding="utf-8", errors="ignore")
        return {
            "file_name": path.name,
            "file_path": str(path.resolve()),
            "file_size": size,
            "format": "TXT",
            "lines": len(text.splitlines()),
            "words": len(text.split()),
            "has_alpha": False,
        }

    # Standard image metadata extraction
    file_size = path.stat().st_size
    with Image.open(path) as img:
        width, height = img.size
        img_format = img.format or path.suffix.lstrip(".").upper()
        mode = img.mode
        has_alpha = mode in ("RGBA", "LA", "PA") or (
            mode == "P" and "transparency" in img.info
        )

    return {
        "file_name": path.name,
        "file_path": str(path.resolve()),
        "file_size": file_size,
        "width": width,
        "height": height,
        "format": img_format,
        "mode": mode,
        "has_alpha": has_alpha,
    }


get_file_metadata = get_image_metadata


@dataclass
class ConversionConfig:
    """Configuration options for file conversion."""

    target_format: str = "JPG"
    quality: int = 90  # 1 - 100 for JPG, WEBP, HEIC
    lossless: bool = False  # WEBP lossless option
    preserve_metadata: bool = True  # EXIF metadata preservation
    auto_orient: bool = True  # Apply EXIF rotation transpose
    resize_mode: str = "none"  # "none", "percentage", "custom", "fit_box"
    resize_percent: float = 100.0  # Percentage scale
    custom_width: Optional[int] = None
    custom_height: Optional[int] = None
    keep_aspect_ratio: bool = True
    background_color: Tuple[int, int, int] = (255, 255, 255)  # Alpha composite RGB
    ico_sizes: Tuple[Tuple[int, int], ...] = (
        (16, 16),
        (32, 32),
        (48, 48),
        (64, 64),
        (128, 128),
        (256, 256),
    )
    tiff_compression: str = "tiff_deflate"  # "none", "tiff_lzw", "tiff_deflate", "packbits"
    dpi: int = 150  # DPI for PDF page rendering
    sheet_name: Optional[str] = None  # Specific sheet for Excel conversion
    password: Optional[str] = None  # Password for encrypted PDF/Office files
    enable_ocr: bool = False  # Enable OCR fallback for scanned PDFs/images
    max_workers: Optional[int] = None  # Worker threads for batch conversion
    max_file_size: int = 500 * 1024 * 1024  # Max allowed input file size (default 500MB)
    strip_metadata: bool = False  # Strip all personal, device, and tracking metadata

    def __post_init__(self):
        if self.strip_metadata:
            self.preserve_metadata = False
        elif not self.preserve_metadata:
            self.strip_metadata = True


@dataclass
class ConversionResult:
    """Outcome and statistics of a file conversion."""

    success: bool
    input_path: str
    output_path: str = ""
    input_format: str = ""
    output_format: str = ""
    input_dimensions: Tuple[int, int] = (0, 0)
    output_dimensions: Tuple[int, int] = (0, 0)
    input_size_bytes: int = 0
    output_size_bytes: int = 0
    duration_seconds: float = 0.0
    error_message: Optional[str] = None


class ImageConverterEngine:
    """High-performance conversion engine supporting Images, PDF, Word, CSV, Excel, PPTX, ODT, and RTF."""

    def __init__(self):
        self.heif_supported = _HEIF_AVAILABLE
        self.doc_converter = DocumentConverter()
        self.data_converter = DataConverter()
        self.pres_converter = PresentationConverter()
        self.rich_converter = RichDocumentConverter()

    def is_format_supported(self, fmt: str) -> bool:
        """Check if output format is currently supported."""
        fmt_upper = fmt.upper()
        if fmt_upper == "HEIC" and not self.heif_supported:
            return False
        return fmt_upper in FORMAT_EXTENSIONS

    def calculate_dimensions(
        self,
        orig_w: int,
        orig_h: int,
        config: ConversionConfig,
    ) -> Tuple[int, int]:
        """Calculate target width and height according to resize settings."""
        if config.resize_mode == "percentage":
            ratio = max(0.01, config.resize_percent / 100.0)
            target_w = max(1, int(round(orig_w * ratio)))
            target_h = max(1, int(round(orig_h * ratio)))
            return target_w, target_h

        elif config.resize_mode == "custom":
            req_w = config.custom_width
            req_h = config.custom_height

            if req_w and req_h:
                if config.keep_aspect_ratio:
                    ratio = min(req_w / orig_w, req_h / orig_h)
                    return max(1, int(round(orig_w * ratio))), max(1, int(round(orig_h * ratio)))
                return max(1, req_w), max(1, req_h)
            elif req_w and not req_h:
                ratio = req_w / orig_w
                return max(1, req_w), max(1, int(round(orig_h * ratio)))
            elif req_h and not req_w:
                ratio = req_h / orig_h
                return max(1, int(round(orig_w * ratio))), max(1, req_h)
            return orig_w, orig_h

        elif config.resize_mode == "fit_box":
            box_w = config.custom_width or orig_w
            box_h = config.custom_height or orig_h
            ratio = min(box_w / orig_w, box_h / orig_h)
            if ratio < 1.0:  # Only downscale to fit
                return max(1, int(round(orig_w * ratio))), max(1, int(round(orig_h * ratio)))
            return orig_w, orig_h

        return orig_w, orig_h

    def composite_alpha(
        self,
        img: Image.Image,
        bg_color: Tuple[int, int, int] = (255, 255, 255),
    ) -> Image.Image:
        """Composite image with alpha onto a solid background color."""
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            img_rgba = img.convert("RGBA")
            bg = Image.new("RGBA", img_rgba.size, (*bg_color, 255))
            alpha_composited = Image.alpha_composite(bg, img_rgba)
            return alpha_composited.convert("RGB")
        elif img.mode == "CMYK":
            return img.convert("RGB")
        elif img.mode != "RGB":
            return img.convert("RGB")
        return img

    def convert_single(
        self,
        input_path: str | Path,
        output_path: str | Path,
        config: ConversionConfig,
    ) -> ConversionResult:
        """
        Convert a single file with specified configuration.
        Intelligently routes between Images, PDF, Word, CSV, Excel, PPTX, ODT, and RTF converters.
        """
        t_start = time.perf_counter()
        in_p = Path(input_path).resolve()
        out_p = Path(output_path).resolve()

        if in_p == out_p:
            return ConversionResult(
                success=False,
                input_path=str(in_p),
                output_path=str(out_p),
                duration_seconds=0.0,
                error_message="Input and output paths must be different.",
            )

        # Input and output validation and security checks
        try:
            validate_input_file(in_p, max_size_bytes=config.max_file_size)
            validate_output_path(out_p)
        except Exception as sec_err:
            return ConversionResult(
                success=False,
                input_path=str(in_p),
                output_path=str(out_p),
                duration_seconds=time.perf_counter() - t_start,
                error_message=str(sec_err),
            )

        target_fmt_upper = config.target_format.upper()
        if target_fmt_upper not in FORMAT_EXTENSIONS:
            return ConversionResult(
                success=False,
                input_path=str(in_p),
                output_path=str(out_p),
                duration_seconds=0.0,
                error_message=f"Unsupported target format: {config.target_format}",
            )

        in_ext = in_p.suffix.lower()
        input_size = in_p.stat().st_size
        out_p.parent.mkdir(parents=True, exist_ok=True)

        # Direct metadata stripping / sanitation without format change
        if (
            target_fmt_upper in ("STRIP_METADATA", "CLEAN")
            or (config.strip_metadata and (in_ext == out_p.suffix.lower() or target_fmt_upper == in_ext.lstrip(".").upper()))
        ):
            from .metadata_engine import strip_file_metadata
            strip_res = strip_file_metadata(in_p, out_p, password=config.password)
            if not strip_res["success"]:
                return ConversionResult(
                    success=False,
                    input_path=str(in_p),
                    output_path=str(out_p),
                    duration_seconds=time.perf_counter() - t_start,
                    error_message=strip_res.get("error_message") or "Failed to strip metadata",
                )
            out_size = out_p.stat().st_size if out_p.exists() else 0
            return ConversionResult(
                success=True,
                input_path=str(in_p),
                output_path=str(out_p),
                input_format=in_ext.lstrip(".").upper(),
                output_format=out_p.suffix.lstrip(".").upper(),
                input_size_bytes=input_size,
                output_size_bytes=out_size,
                duration_seconds=time.perf_counter() - t_start,
            )

        try:
            # -----------------------------------------------------------------
            # 1. PDF Input
            # -----------------------------------------------------------------
            if in_ext == ".pdf":
                in_format = "PDF"
                if target_fmt_upper in ("PNG", "JPG", "JPEG", "WEBP", "BMP", "TIFF"):
                    files = self.doc_converter.convert_pdf_to_images(
                        in_p,
                        out_p,
                        target_format=target_fmt_upper,
                        dpi=config.dpi,
                        password=config.password,
                    )
                    final_out = files[0] if files else out_p
                elif target_fmt_upper == "DOCX":
                    final_out = self.doc_converter.convert_pdf_to_docx(
                        in_p, out_p, password=config.password, enable_ocr=config.enable_ocr
                    )
                elif target_fmt_upper == "TXT":
                    final_out = self.doc_converter.convert_pdf_to_text(
                        in_p, out_p, password=config.password, enable_ocr=config.enable_ocr
                    )
                elif target_fmt_upper in ("CSV", "XLSX"):
                    final_out = self.doc_converter.convert_pdf_to_tables(
                        in_p, out_p, target_format=target_fmt_upper, password=config.password
                    )
                elif target_fmt_upper == "PPTX":
                    txt_tmp = out_p.with_suffix(".tmp.txt")
                    self.doc_converter.convert_pdf_to_text(
                        in_p, txt_tmp, password=config.password, enable_ocr=config.enable_ocr
                    )
                    final_out = self.pres_converter.convert_text_to_pptx(txt_tmp, out_p)
                    txt_tmp.unlink(missing_ok=True)
                else:
                    return ConversionResult(
                        success=False,
                        input_path=str(in_p),
                        output_path=str(out_p),
                        duration_seconds=time.perf_counter() - t_start,
                        error_message=f"Cannot convert PDF to {target_fmt_upper}",
                    )

                out_size = final_out.stat().st_size if final_out.exists() else 0
                return ConversionResult(
                    success=True,
                    input_path=str(in_p),
                    output_path=str(final_out),
                    input_format=in_format,
                    output_format=target_fmt_upper,
                    input_size_bytes=input_size,
                    output_size_bytes=out_size,
                    duration_seconds=time.perf_counter() - t_start,
                )

            # -----------------------------------------------------------------
            # 2. Word Input (.docx, .doc)
            # -----------------------------------------------------------------
            elif in_ext in (".docx", ".doc"):
                in_format = in_ext.lstrip(".").upper()
                if target_fmt_upper == "PDF":
                    final_out = self.doc_converter.convert_docx_to_pdf(in_p, out_p)
                elif target_fmt_upper == "TXT":
                    final_out = self.doc_converter.convert_docx_to_text(in_p, out_p)
                elif target_fmt_upper == "HTML":
                    final_out = self.doc_converter.convert_docx_to_html(in_p, out_p)
                elif target_fmt_upper in ("PNG", "JPG", "JPEG", "WEBP"):
                    files = self.doc_converter.convert_docx_to_images(
                        in_p, out_p, target_format=target_fmt_upper, dpi=config.dpi
                    )
                    final_out = files[0] if files else out_p
                elif target_fmt_upper == "ODT":
                    final_out = self.rich_converter.convert_docx_to_odt(in_p, out_p)
                elif target_fmt_upper == "RTF":
                    txt_tmp = out_p.with_suffix(".tmp.txt")
                    self.doc_converter.convert_docx_to_text(in_p, txt_tmp)
                    final_out = self.rich_converter.convert_text_to_rtf(txt_tmp, out_p)
                    txt_tmp.unlink(missing_ok=True)
                elif target_fmt_upper == "PPTX":
                    txt_tmp = out_p.with_suffix(".tmp.txt")
                    self.doc_converter.convert_docx_to_text(in_p, txt_tmp)
                    final_out = self.pres_converter.convert_text_to_pptx(txt_tmp, out_p)
                    txt_tmp.unlink(missing_ok=True)
                else:
                    return ConversionResult(
                        success=False,
                        input_path=str(in_p),
                        output_path=str(out_p),
                        duration_seconds=time.perf_counter() - t_start,
                        error_message=f"Cannot convert Word document to {target_fmt_upper}",
                    )

                out_size = final_out.stat().st_size if final_out.exists() else 0
                return ConversionResult(
                    success=True,
                    input_path=str(in_p),
                    output_path=str(final_out),
                    input_format=in_format,
                    output_format=target_fmt_upper,
                    input_size_bytes=input_size,
                    output_size_bytes=out_size,
                    duration_seconds=time.perf_counter() - t_start,
                )

            # -----------------------------------------------------------------
            # 3. Presentation Input (.pptx)
            # -----------------------------------------------------------------
            elif in_ext == ".pptx":
                in_format = "PPTX"
                if target_fmt_upper == "PDF":
                    final_out = self.pres_converter.convert_pptx_to_pdf(in_p, out_p)
                elif target_fmt_upper == "TXT":
                    final_out = self.pres_converter.convert_pptx_to_text(in_p, out_p)
                elif target_fmt_upper == "HTML":
                    final_out = self.pres_converter.convert_pptx_to_html(in_p, out_p)
                elif target_fmt_upper in ("PNG", "JPG", "JPEG", "WEBP"):
                    files = self.pres_converter.convert_pptx_to_images(
                        in_p, out_p, target_format=target_fmt_upper, dpi=config.dpi
                    )
                    final_out = files[0] if files else out_p
                elif target_fmt_upper == "DOCX":
                    txt_tmp = out_p.with_suffix(".tmp.txt")
                    self.pres_converter.convert_pptx_to_text(in_p, txt_tmp)
                    import docx
                    d = docx.Document()
                    for line in txt_tmp.read_text(encoding="utf-8").splitlines():
                        if line.strip():
                            d.add_paragraph(line.strip())
                    d.save(str(out_p))
                    txt_tmp.unlink(missing_ok=True)
                    final_out = out_p
                else:
                    return ConversionResult(
                        success=False,
                        input_path=str(in_p),
                        output_path=str(out_p),
                        duration_seconds=time.perf_counter() - t_start,
                        error_message=f"Cannot convert PowerPoint presentation to {target_fmt_upper}",
                    )

                out_size = final_out.stat().st_size if final_out.exists() else 0
                return ConversionResult(
                    success=True,
                    input_path=str(in_p),
                    output_path=str(final_out),
                    input_format=in_format,
                    output_format=target_fmt_upper,
                    input_size_bytes=input_size,
                    output_size_bytes=out_size,
                    duration_seconds=time.perf_counter() - t_start,
                )

            # -----------------------------------------------------------------
            # 4. OpenDocument (.odt)
            # -----------------------------------------------------------------
            elif in_ext == ".odt":
                in_format = "ODT"
                if target_fmt_upper == "PDF":
                    final_out = self.rich_converter.convert_odt_to_pdf(in_p, out_p)
                elif target_fmt_upper == "DOCX":
                    final_out = self.rich_converter.convert_odt_to_docx(in_p, out_p)
                elif target_fmt_upper == "TXT":
                    final_out = self.rich_converter.convert_odt_to_text(in_p, out_p)
                elif target_fmt_upper == "RTF":
                    txt_tmp = out_p.with_suffix(".tmp.txt")
                    self.rich_converter.convert_odt_to_text(in_p, txt_tmp)
                    final_out = self.rich_converter.convert_text_to_rtf(txt_tmp, out_p)
                    txt_tmp.unlink(missing_ok=True)
                else:
                    return ConversionResult(
                        success=False,
                        input_path=str(in_p),
                        output_path=str(out_p),
                        duration_seconds=time.perf_counter() - t_start,
                        error_message=f"Cannot convert ODT to {target_fmt_upper}",
                    )

                out_size = final_out.stat().st_size if final_out.exists() else 0
                return ConversionResult(
                    success=True,
                    input_path=str(in_p),
                    output_path=str(final_out),
                    input_format=in_format,
                    output_format=target_fmt_upper,
                    input_size_bytes=input_size,
                    output_size_bytes=out_size,
                    duration_seconds=time.perf_counter() - t_start,
                )

            # -----------------------------------------------------------------
            # 5. Rich Text Format (.rtf)
            # -----------------------------------------------------------------
            elif in_ext == ".rtf":
                in_format = "RTF"
                if target_fmt_upper == "PDF":
                    final_out = self.rich_converter.convert_rtf_to_pdf(in_p, out_p)
                elif target_fmt_upper == "DOCX":
                    final_out = self.rich_converter.convert_rtf_to_docx(in_p, out_p)
                elif target_fmt_upper == "TXT":
                    final_out = self.rich_converter.convert_rtf_to_text(in_p, out_p)
                elif target_fmt_upper == "ODT":
                    docx_tmp = out_p.with_suffix(".tmp.docx")
                    self.rich_converter.convert_rtf_to_docx(in_p, docx_tmp)
                    final_out = self.rich_converter.convert_docx_to_odt(docx_tmp, out_p)
                    docx_tmp.unlink(missing_ok=True)
                else:
                    return ConversionResult(
                        success=False,
                        input_path=str(in_p),
                        output_path=str(out_p),
                        duration_seconds=time.perf_counter() - t_start,
                        error_message=f"Cannot convert RTF to {target_fmt_upper}",
                    )

                out_size = final_out.stat().st_size if final_out.exists() else 0
                return ConversionResult(
                    success=True,
                    input_path=str(in_p),
                    output_path=str(final_out),
                    input_format=in_format,
                    output_format=target_fmt_upper,
                    input_size_bytes=input_size,
                    output_size_bytes=out_size,
                    duration_seconds=time.perf_counter() - t_start,
                )

            # -----------------------------------------------------------------
            # 6. Plain Text Input (.txt)
            # -----------------------------------------------------------------
            elif in_ext == ".txt":
                in_format = "TXT"
                content = in_p.read_text(encoding="utf-8", errors="ignore")
                if target_fmt_upper == "PDF":
                    final_out = self.rich_converter._text_to_pdf(content, out_p, title=in_p.stem)
                elif target_fmt_upper == "DOCX":
                    import docx
                    d = docx.Document()
                    for line in content.splitlines():
                        if line.strip():
                            d.add_paragraph(line.strip())
                    d.save(str(out_p))
                    final_out = out_p
                elif target_fmt_upper == "PPTX":
                    final_out = self.pres_converter.convert_text_to_pptx(in_p, out_p)
                elif target_fmt_upper == "RTF":
                    final_out = self.rich_converter.convert_text_to_rtf(in_p, out_p)
                elif target_fmt_upper == "HTML":
                    safe_body = html.escape(content).replace("\n", "<br>\n")
                    html_str = f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{html.escape(in_p.stem)}</title></head><body style='font-family:sans-serif;line-height:1.6;padding:20px;max-width:800px;margin:auto;'><pre>{safe_body}</pre></body></html>"
                    out_p.write_text(html_str, encoding="utf-8")
                    final_out = out_p
                else:
                    return ConversionResult(
                        success=False,
                        input_path=str(in_p),
                        output_path=str(out_p),
                        duration_seconds=time.perf_counter() - t_start,
                        error_message=f"Cannot convert TXT to {target_fmt_upper}",
                    )

                out_size = final_out.stat().st_size if final_out.exists() else 0
                return ConversionResult(
                    success=True,
                    input_path=str(in_p),
                    output_path=str(final_out),
                    input_format=in_format,
                    output_format=target_fmt_upper,
                    input_size_bytes=input_size,
                    output_size_bytes=out_size,
                    duration_seconds=time.perf_counter() - t_start,
                )

            # -----------------------------------------------------------------
            # 7. CSV Input
            # -----------------------------------------------------------------
            elif in_ext == ".csv":
                in_format = "CSV"
                if target_fmt_upper in ("XLSX", "EXCEL"):
                    final_out = self.data_converter.convert_csv_to_excel(in_p, out_p)
                elif target_fmt_upper == "PDF":
                    final_out = self.data_converter.convert_csv_to_pdf(in_p, out_p)
                elif target_fmt_upper == "JSON":
                    final_out = self.data_converter.convert_csv_to_json(in_p, out_p)
                elif target_fmt_upper == "HTML":
                    final_out = self.data_converter.convert_csv_to_html(in_p, out_p)
                elif target_fmt_upper == "TXT":
                    final_out = self.data_converter.convert_csv_to_text(in_p, out_p)
                else:
                    return ConversionResult(
                        success=False,
                        input_path=str(in_p),
                        output_path=str(out_p),
                        duration_seconds=time.perf_counter() - t_start,
                        error_message=f"Cannot convert CSV to {target_fmt_upper}",
                    )

                out_size = final_out.stat().st_size if final_out.exists() else 0
                return ConversionResult(
                    success=True,
                    input_path=str(in_p),
                    output_path=str(final_out),
                    input_format=in_format,
                    output_format=target_fmt_upper,
                    input_size_bytes=input_size,
                    output_size_bytes=out_size,
                    duration_seconds=time.perf_counter() - t_start,
                )

            # -----------------------------------------------------------------
            # 8. Excel Input (.xlsx, .xls)
            # -----------------------------------------------------------------
            elif in_ext in (".xlsx", ".xls"):
                in_format = in_ext.lstrip(".").upper()
                if target_fmt_upper == "CSV":
                    final_out = self.data_converter.convert_excel_to_csv(
                        in_p, out_p, sheet_name=config.sheet_name
                    )
                elif target_fmt_upper == "PDF":
                    final_out = self.data_converter.convert_excel_to_pdf(
                        in_p, out_p, sheet_name=config.sheet_name
                    )
                elif target_fmt_upper == "JSON":
                    final_out = self.data_converter.convert_excel_to_json(
                        in_p, out_p, sheet_name=config.sheet_name
                    )
                elif target_fmt_upper == "HTML":
                    final_out = self.data_converter.convert_excel_to_html(
                        in_p, out_p, sheet_name=config.sheet_name
                    )
                else:
                    return ConversionResult(
                        success=False,
                        input_path=str(in_p),
                        output_path=str(out_p),
                        duration_seconds=time.perf_counter() - t_start,
                        error_message=f"Cannot convert Excel to {target_fmt_upper}",
                    )

                out_size = final_out.stat().st_size if final_out.exists() else 0
                return ConversionResult(
                    success=True,
                    input_path=str(in_p),
                    output_path=str(final_out),
                    input_format=in_format,
                    output_format=target_fmt_upper,
                    input_size_bytes=input_size,
                    output_size_bytes=out_size,
                    duration_seconds=time.perf_counter() - t_start,
                )

            # -----------------------------------------------------------------
            # 9. Image Input (Pillow + pillow-heif or OCR)
            # -----------------------------------------------------------------
            else:
                # Check for OCR text extraction from image to TXT or DOCX
                if target_fmt_upper in ("TXT", "DOCX"):
                    in_format = in_p.suffix.lstrip(".").upper()
                    extracted_text = ocr_image_to_text(in_p)
                    if target_fmt_upper == "TXT":
                        out_p.write_text(extracted_text, encoding="utf-8")
                        final_out = out_p
                    else:
                        import docx
                        d = docx.Document()
                        for line in extracted_text.splitlines():
                            if line.strip():
                                d.add_paragraph(line.strip())
                        d.save(str(out_p))
                        final_out = out_p

                    out_size = final_out.stat().st_size if final_out.exists() else 0
                    return ConversionResult(
                        success=True,
                        input_path=str(in_p),
                        output_path=str(final_out),
                        input_format=in_format,
                        output_format=target_fmt_upper,
                        input_size_bytes=input_size,
                        output_size_bytes=out_size,
                        duration_seconds=time.perf_counter() - t_start,
                    )

                if target_fmt_upper not in PILLOW_FORMAT_MAP:
                    return ConversionResult(
                        success=False,
                        input_path=str(in_p),
                        output_path=str(out_p),
                        duration_seconds=0.0,
                        error_message=f"Cannot convert image to non-image format {target_fmt_upper}",
                    )

                pillow_fmt = PILLOW_FORMAT_MAP[target_fmt_upper]
                if pillow_fmt == "HEIF" and not self.heif_supported:
                    return ConversionResult(
                        success=False,
                        input_path=str(in_p),
                        output_path=str(out_p),
                        duration_seconds=0.0,
                        error_message="HEIC/HEIF encoding requires pillow-heif package.",
                    )

                with Image.open(in_p) as src_img:
                    in_format = src_img.format or in_p.suffix.lstrip(".").upper()
                    orig_w, orig_h = src_img.size

                    # Auto-orient based on EXIF tag if requested
                    if config.auto_orient:
                        try:
                            work_img = ImageOps.exif_transpose(src_img)
                        except Exception:
                            work_img = src_img.copy()
                    else:
                        work_img = src_img.copy()

                    # Preserve EXIF bytes if requested and present
                    exif_data = None
                    if config.preserve_metadata:
                        exif_data = work_img.info.get("exif")

                    # Resize if necessary
                    target_w, target_h = self.calculate_dimensions(
                        work_img.width, work_img.height, config
                    )
                    if (target_w, target_h) != (work_img.width, work_img.height):
                        work_img = work_img.resize(
                            (target_w, target_h),
                            resample=Image.Resampling.LANCZOS,
                        )

                    out_w, out_h = work_img.size

                    # Save options per target format
                    save_kwargs = {}

                    if target_fmt_upper in ("JPG", "JPEG"):
                        work_img = self.composite_alpha(work_img, config.background_color)
                        save_kwargs["quality"] = max(1, min(100, config.quality))
                        save_kwargs["optimize"] = True
                        save_kwargs["progressive"] = True
                        if exif_data:
                            save_kwargs["exif"] = exif_data

                    elif target_fmt_upper == "PNG":
                        if work_img.mode not in ("RGB", "RGBA", "L", "LA"):
                            work_img = work_img.convert("RGBA")
                        save_kwargs["optimize"] = True
                        save_kwargs["compress_level"] = 6
                        if exif_data:
                            save_kwargs["exif"] = exif_data

                    elif target_fmt_upper == "WEBP":
                        if work_img.mode not in ("RGB", "RGBA"):
                            work_img = work_img.convert("RGBA")
                        save_kwargs["quality"] = max(1, min(100, config.quality))
                        save_kwargs["lossless"] = config.lossless
                        save_kwargs["method"] = 6
                        if exif_data:
                            save_kwargs["exif"] = exif_data

                    elif target_fmt_upper in ("HEIC", "HEIF"):
                        if work_img.mode not in ("RGB", "RGBA"):
                            work_img = work_img.convert("RGB")
                        save_kwargs["quality"] = max(1, min(100, config.quality))
                        if exif_data:
                            save_kwargs["exif"] = exif_data

                    elif target_fmt_upper == "BMP":
                        work_img = self.composite_alpha(work_img, config.background_color)

                    elif target_fmt_upper == "TIFF":
                        if config.tiff_compression != "none":
                            save_kwargs["compression"] = config.tiff_compression
                        if exif_data:
                            save_kwargs["exif"] = exif_data

                    elif target_fmt_upper == "GIF":
                        if work_img.mode not in ("P", "L"):
                            work_img = work_img.convert("P", palette=Image.Palette.ADAPTIVE)

                    elif target_fmt_upper == "ICO":
                        if work_img.mode != "RGBA":
                            work_img = work_img.convert("RGBA")
                        save_kwargs["sizes"] = config.ico_sizes

                    elif target_fmt_upper == "PDF":
                        work_img = self.composite_alpha(work_img, config.background_color)
                        save_kwargs["resolution"] = 100.0

                    # Atomic save
                    temp_path = None
                    try:
                        with tempfile.NamedTemporaryFile(
                            dir=out_p.parent,
                            prefix=f".{out_p.stem}-",
                            suffix=out_p.suffix,
                            delete=False,
                        ) as temp_file:
                            temp_path = Path(temp_file.name)
                        work_img.save(temp_path, format=pillow_fmt, **save_kwargs)
                        os.replace(temp_path, out_p)
                        temp_path = None
                    finally:
                        if temp_path and temp_path.exists():
                            temp_path.unlink()

                output_size = out_p.stat().st_size
                duration = time.perf_counter() - t_start

                return ConversionResult(
                    success=True,
                    input_path=str(in_p),
                    output_path=str(out_p),
                    input_format=in_format,
                    output_format=target_fmt_upper,
                    input_dimensions=(orig_w, orig_h),
                    output_dimensions=(out_w, out_h),
                    input_size_bytes=input_size,
                    output_size_bytes=output_size,
                    duration_seconds=duration,
                )

        except Exception as e:
            duration = time.perf_counter() - t_start
            return ConversionResult(
                success=False,
                input_path=str(in_p),
                output_path=str(out_p),
                duration_seconds=duration,
                error_message=f"Conversion error: {str(e)}",
            )

    def convert_batch(
        self,
        tasks: List[Tuple[str | Path, str | Path, ConversionConfig]],
        progress_callback: Optional[Callable[[int, int, ConversionResult], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        max_workers: Optional[int] = None,
    ) -> List[ConversionResult]:
        """
        Process a list of conversion tasks concurrently using ThreadPoolExecutor
        with thread-safe progress updates and mid-batch cancellation.
        """
        import concurrent.futures
        import threading

        total = len(tasks)
        if total == 0:
            return []

        if total == 1:
            in_path, out_path, config = tasks[0]
            if cancel_check and cancel_check():
                return []
            try:
                res = self.convert_single(in_path, out_path, config)
            except Exception as e:
                res = ConversionResult(
                    success=False,
                    input_path=str(in_path),
                    output_path=str(out_path),
                    error_message=f"Single conversion failure: {str(e)}",
                )
            if progress_callback:
                try:
                    progress_callback(1, 1, res)
                except Exception:
                    pass
            return [res]

        workers = max_workers
        if workers is None:
            for _, _, cfg in tasks:
                if cfg.max_workers:
                    workers = cfg.max_workers
                    break
        if workers is None:
            workers = min(8, max(1, os.cpu_count() or 4))

        results: List[ConversionResult] = [None] * total  # type: ignore
        completed_count = 0
        lock = threading.Lock()

        def _worker(idx: int, task: Tuple[str | Path, str | Path, ConversionConfig]):
            nonlocal completed_count
            if cancel_check and cancel_check():
                return idx, None

            in_p_task, out_p_task, cfg_task = task
            try:
                res_item = self.convert_single(in_p_task, out_p_task, cfg_task)
            except Exception as e:
                res_item = ConversionResult(
                    success=False,
                    input_path=str(in_p_task),
                    output_path=str(out_p_task),
                    error_message=f"Worker exception: {str(e)}",
                )

            with lock:
                completed_count += 1
                current_completed = completed_count

            if progress_callback:
                try:
                    progress_callback(current_completed, total, res_item)
                except Exception:
                    pass

            return idx, res_item

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_idx = {
                executor.submit(_worker, idx, task): idx
                for idx, task in enumerate(tasks)
            }

            for future in concurrent.futures.as_completed(future_to_idx):
                if cancel_check and cancel_check():
                    for f in future_to_idx:
                        f.cancel()
                    break
                try:
                    idx, res_item = future.result()
                    if res_item is not None:
                        results[idx] = res_item
                except Exception as e:
                    idx = future_to_idx[future]
                    in_p_task, out_p_task, _ = tasks[idx]
                    fail_res = ConversionResult(
                        success=False,
                        input_path=str(in_p_task),
                        output_path=str(out_p_task),
                        error_message=f"Batch execution error: {str(e)}",
                    )
                    results[idx] = fail_res
                    with lock:
                        completed_count += 1
                        current_completed = completed_count
                    if progress_callback:
                        try:
                            progress_callback(current_completed, total, fail_res)
                        except Exception:
                            pass

        return [r for r in results if r is not None]

    def strip_metadata(
        self,
        input_path: str | Path,
        output_path: Optional[str | Path] = None,
        password: Optional[str] = None,
    ) -> ConversionResult:
        """Strip all personal, device, and tracking metadata from a file."""
        t_start = time.perf_counter()
        in_p = Path(input_path).resolve()
        if not in_p.is_file():
            return ConversionResult(
                success=False,
                input_path=str(in_p),
                output_path=str(output_path or in_p),
                duration_seconds=0.0,
                error_message=f"Input file not found: {in_p}",
            )

        from .metadata_engine import strip_file_metadata

        res = strip_file_metadata(in_p, output_path, password=password)
        out_p = Path(res["output_path"])
        return ConversionResult(
            success=res["success"],
            input_path=str(in_p),
            output_path=str(out_p),
            input_format=in_p.suffix.lstrip(".").upper(),
            output_format=out_p.suffix.lstrip(".").upper(),
            input_size_bytes=res.get("original_size", in_p.stat().st_size),
            output_size_bytes=res.get("sanitized_size", out_p.stat().st_size if out_p.exists() else 0),
            duration_seconds=time.perf_counter() - t_start,
            error_message=res.get("error_message"),
        )


# Export UniversalConverterEngine alias
UniversalConverterEngine = ImageConverterEngine
