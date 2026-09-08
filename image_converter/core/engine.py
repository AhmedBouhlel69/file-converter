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
    Read dimensions, mode, and metadata for images, PDFs, Word, CSV, or Excel files.
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
    """High-performance conversion engine supporting Images, PDF, Word, CSV, and Excel."""

    def __init__(self):
        self.heif_supported = _HEIF_AVAILABLE
        self.doc_converter = DocumentConverter()
        self.data_converter = DataConverter()

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
        Intelligently routes between Images, PDF, Word, CSV, and Excel converters.
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

        if not in_p.is_file():
            return ConversionResult(
                success=False,
                input_path=str(in_p),
                output_path=str(out_p),
                duration_seconds=0.0,
                error_message=f"Input file not found: {in_p}",
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
                    )
                    final_out = files[0] if files else out_p
                elif target_fmt_upper == "DOCX":
                    final_out = self.doc_converter.convert_pdf_to_docx(in_p, out_p)
                elif target_fmt_upper == "TXT":
                    final_out = self.doc_converter.convert_pdf_to_text(in_p, out_p)
                elif target_fmt_upper in ("CSV", "XLSX"):
                    final_out = self.doc_converter.convert_pdf_to_tables(
                        in_p, out_p, target_format=target_fmt_upper
                    )
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
            # 3. CSV Input
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
            # 4. Excel Input (.xlsx, .xls)
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
            # 5. Image Input (Pillow + pillow-heif)
            # -----------------------------------------------------------------
            else:
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
    ) -> List[ConversionResult]:
        """
        Process a list of conversion tasks sequentially with progress updates.
        """
        results: List[ConversionResult] = []
        total = len(tasks)

        for idx, (in_path, out_path, config) in enumerate(tasks):
            if cancel_check and cancel_check():
                break

            res = self.convert_single(in_path, out_path, config)
            results.append(res)

            if progress_callback:
                progress_callback(idx + 1, total, res)

        return results


# Export UniversalConverterEngine alias
UniversalConverterEngine = ImageConverterEngine
