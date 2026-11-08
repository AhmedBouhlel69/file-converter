"""
Core conversion engine supporting Images, PDF, Word, CSV, and XLSX.
Supports HEIC, JPG, PNG, WEBP, BMP, TIFF, GIF, ICO, PDF, DOCX, XLSX, CSV, TXT, JSON, and HTML.
"""

from __future__ import annotations

import html
import logging
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

from ..safety.security import (
    SecurityError,
    validate_input_file,
    validate_output_path,
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
        from ..documents.engine import get_pdf_metadata
        return get_pdf_metadata(path)
    elif ext in (".docx", ".doc"):
        from ..documents.engine import get_docx_metadata
        return get_docx_metadata(path)
    elif ext == ".csv":
        from ..data.engine import get_csv_metadata
        return get_csv_metadata(path)
    elif ext in (".xlsx", ".xls"):
        from ..data.engine import get_excel_metadata
        return get_excel_metadata(path)
    elif ext == ".pptx":
        from ..presentations.engine import get_pptx_metadata
        return get_pptx_metadata(path)
    elif ext == ".odt":
        from ..rich_documents.engine import get_odt_metadata
        return get_odt_metadata(path)
    elif ext == ".rtf":
        from ..rich_documents.engine import get_rtf_metadata
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
        try:
            # Report the size the picture is shown at (EXIF-rotated phone photos).
            if img.getexif().get(0x0112) in (5, 6, 7, 8):
                width, height = height, width
        except Exception:
            pass
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
    ocr_language: str = "auto"  # Tesseract language(s), e.g. "eng", "eng+fra"; "auto" = English + installed extras
    reencode: bool = False  # True: always re-encode same-format images (compression), even when stripping metadata
    png_palette: str = "auto"  # "auto": lossless 8-bit palette when <=256 colours; "reduce": 256-colour quantise; "off"

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



# ---------------------------------------------------------------------------
# Image fidelity helpers
# ---------------------------------------------------------------------------
_SRGB_PROFILE = None


def _srgb_profile():
    global _SRGB_PROFILE
    if _SRGB_PROFILE is None:
        from PIL import ImageCms
        _SRGB_PROFILE = ImageCms.createProfile("sRGB")
    return _SRGB_PROFILE


def _to_8bit(img: Image.Image) -> Image.Image:
    """Scale 16/32-bit and float images to 8-bit instead of clipping to white."""
    if img.mode in ("I;16", "I;16L", "I;16B", "I;16N", "I"):
        import numpy as np
        arr = np.asarray(img)
        if img.mode.startswith("I;16") or (arr.size and int(arr.max()) > 255):
            arr = arr.astype(np.float32) / 257.0
        return Image.fromarray(np.clip(np.rint(arr), 0, 255).astype(np.uint8), "L")
    if img.mode == "F":
        import numpy as np
        arr = np.asarray(img, dtype=np.float32)
        finite = arr[np.isfinite(arr)]
        if finite.size and float(finite.max()) <= 1.0 and float(finite.min()) >= 0.0:
            arr = arr * 255.0
        return Image.fromarray(np.clip(np.nan_to_num(np.rint(arr)), 0, 255).astype(np.uint8), "L")
    if img.mode == "1":
        return img.convert("L")
    return img


def _profile_space(icc: bytes) -> str:
    try:
        import io as _io
        from PIL import ImageCms
        return ImageCms.ImageCmsProfile(_io.BytesIO(icc)).profile.xcolor_space.strip().upper()
    except Exception:
        return ""


def _profile_is_srgb(icc: bytes) -> bool:
    try:
        import io as _io
        from PIL import ImageCms
        name = ImageCms.getProfileDescription(ImageCms.ImageCmsProfile(_io.BytesIO(icc))) or ""
        return "srgb" in name.lower().replace(" ", "")
    except Exception:
        return False


def _apply_color_profile(img: Image.Image, icc: Optional[bytes], target: str, strip: bool):
    """Return ``(image, icc_to_embed)`` so colours look the same after conversion.

    CMYK is converted through its embedded profile (or Pillow's default) for
    every target except TIFF. RGB/grey profiles are embedded again where the
    output format supports them; otherwise (GIF, BMP, ICO, PDF) or when
    metadata is stripped, pixels are converted to sRGB so they still look right.
    """
    import io as _io

    keeps_cmyk = target == "TIFF"
    embeds = target in ("JPG", "JPEG", "PNG", "WEBP", "TIFF", "HEIC", "HEIF")
    space = _profile_space(icc) if icc else ""

    if img.mode == "CMYK" and not keeps_cmyk:
        if icc and space == "CMYK":
            try:
                from PIL import ImageCms
                converted = ImageCms.profileToProfile(
                    img, _io.BytesIO(icc), _srgb_profile(), outputMode="RGB",
                    renderingIntent=ImageCms.Intent.PERCEPTUAL,
                )
                if converted is not None:
                    return converted, None
            except Exception as exc:
                logger.warning("CMYK profile conversion failed, using default: %s", exc)
        return img.convert("RGB"), None

    if not icc:
        return img, None
    rgb_like = img.mode in ("RGB", "RGBA") and space == "RGB"
    gray_like = img.mode in ("L", "LA") and space == "GRAY"
    cmyk_like = img.mode == "CMYK" and space == "CMYK"
    if not (rgb_like or gray_like or cmyk_like):
        return img, None
    if embeds and not strip:
        return img, icc
    if rgb_like and not _profile_is_srgb(icc):
        try:
            from PIL import ImageCms
            converted = ImageCms.profileToProfile(img, _io.BytesIO(icc), _srgb_profile(), outputMode=img.mode)
            if converted is not None:
                return converted, None
        except Exception as exc:
            logger.warning("Colour profile conversion to sRGB failed: %s", exc)
    return img, None


def _has_alpha(img: Image.Image) -> bool:
    return img.mode in ("RGBA", "LA", "PA", "RGBa", "La") or (img.mode == "P" and "transparency" in img.info)


def _to_gif_frame(img: Image.Image) -> Image.Image:
    """Quantise to a 256-colour palette with dithering, keeping transparency."""
    img = _to_8bit(img)
    if img.mode == "P":
        return img
    if img.mode == "L":
        return img
    if _has_alpha(img):
        rgba = img.convert("RGBA")
        paletted = rgba.convert("RGB").quantize(colors=255, dither=Image.Dither.FLOYDSTEINBERG)
        palette = (paletted.getpalette() or [])[: 255 * 3]
        palette += [0] * (255 * 3 - len(palette)) + [0, 0, 0]
        paletted.putpalette(palette)
        hidden = rgba.getchannel("A").point(lambda a: 255 if a < 128 else 0)
        paletted.paste(255, mask=hidden)
        paletted.info["transparency"] = 255
        return paletted
    return img.convert("RGB").quantize(colors=256, dither=Image.Dither.FLOYDSTEINBERG)


def _exact_palette(img: Image.Image) -> Optional[Image.Image]:
    """Lossless 8-bit palette version of an image with at most 256 colours."""
    import numpy as np

    if img.mode not in ("RGB", "RGBA", "L", "LA"):
        return None
    rgba = np.asarray(img.convert("RGBA"))
    flat = rgba.reshape(-1, 4)
    packed = flat.view(np.uint32).reshape(-1)
    colours, inverse = np.unique(packed, return_inverse=True)
    if len(colours) > 256:
        return None
    entries = colours.view(np.uint8).reshape(-1, 4)
    indexed = Image.fromarray(inverse.reshape(rgba.shape[:2]).astype(np.uint8), "L")
    paletted = indexed.convert("P")
    paletted.putpalette(entries[:, :3].reshape(-1).tolist())
    alphas = entries[:, 3]
    if (alphas < 255).any():
        paletted.info["transparency"] = bytes(alphas.tolist())
    return paletted


def _reduced_palette(img: Image.Image) -> Image.Image:
    """Lossy 256-colour palette with dithering (pngquant-style); keeps alpha."""
    from PIL import features

    if _has_alpha(img):
        rgba = img.convert("RGBA")
        method = Image.Quantize.LIBIMAGEQUANT if features.check("libimagequant") else Image.Quantize.FASTOCTREE
        return rgba.quantize(colors=256, method=method, dither=Image.Dither.FLOYDSTEINBERG)
    rgb = img.convert("RGB")
    method = Image.Quantize.LIBIMAGEQUANT if features.check("libimagequant") else Image.Quantize.MEDIANCUT
    return rgb.quantize(colors=256, method=method, dither=Image.Dither.FLOYDSTEINBERG)


def _png_palette(img: Image.Image, mode: str) -> Image.Image:
    """Apply the PNG palette policy: "auto" (lossless only), "reduce" (lossy), "off"."""
    if mode == "off" or img.mode in ("P", "1", "I", "I;16") or img.mode.startswith("I;"):
        return img
    exact = _exact_palette(img)
    if exact is not None:
        return exact
    if mode == "reduce":
        return _reduced_palette(img)
    return img


def _mode_for_target(img: Image.Image, target: str, background, engine) -> Image.Image:
    """Convert an image to a mode the target format can store without damage."""
    if target in ("JPG", "JPEG", "BMP", "PDF"):
        img = _to_8bit(img)
        if img.mode == "L":
            return img
        return engine.composite_alpha(img, background)
    if target == "PNG":
        if img.mode in ("1", "L", "LA", "P", "RGB", "RGBA", "I;16", "I"):
            return img
        img = _to_8bit(img)
        return img.convert("RGBA" if _has_alpha(img) else "RGB")
    if target in ("WEBP", "HEIC", "HEIF"):
        img = _to_8bit(img)
        if img.mode in ("RGB", "RGBA"):
            return img
        return img.convert("RGBA" if _has_alpha(img) else "RGB")
    if target == "TIFF":
        if img.mode in ("1", "L", "LA", "P", "RGB", "RGBA", "CMYK", "I;16", "I", "F"):
            return img
        return _to_8bit(img).convert("RGBA" if _has_alpha(img) else "RGB")
    if target == "GIF":
        return _to_gif_frame(img)
    if target == "ICO":
        return _to_8bit(img).convert("RGBA")
    return img


class ImageConverterEngine:
    """High-performance conversion engine supporting Images, PDF, Word, CSV, Excel, PPTX, ODT, and RTF."""

    def __init__(self):
        self.heif_supported = _HEIF_AVAILABLE
        self._doc_converter = None
        self._data_converter = None
        self._pres_converter = None
        self._rich_converter = None

    @property
    def doc_converter(self):
        if self._doc_converter is None:
            from ..documents.engine import DocumentConverter
            self._doc_converter = DocumentConverter()
        return self._doc_converter

    @property
    def data_converter(self):
        if self._data_converter is None:
            from ..data.engine import DataConverter
            self._data_converter = DataConverter()
        return self._data_converter

    @property
    def pres_converter(self):
        if self._pres_converter is None:
            from ..presentations.engine import PresentationConverter
            self._pres_converter = PresentationConverter()
        return self._pres_converter

    @property
    def rich_converter(self):
        if self._rich_converter is None:
            from ..rich_documents.engine import RichDocumentConverter
            self._rich_converter = RichDocumentConverter()
        return self._rich_converter

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
        img = _to_8bit(img)
        if img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info):
            img_rgba = img.convert("RGBA")
            bg = Image.new("RGBA", img_rgba.size, (*bg_color, 255))
            alpha_composited = Image.alpha_composite(bg, img_rgba)
            return alpha_composited.convert("RGB")
        elif img.mode == "CMYK":
            return img.convert("RGB")
        elif img.mode != "RGB":
            return img.convert("RGB")
        return img

    def _verify_and_create_result(
        self,
        in_p: Path,
        final_out: Path,
        in_format: str,
        target_fmt_upper: str,
        input_size: int,
        t_start: float,
        input_dimensions: Tuple[int, int] = (0, 0),
        output_dimensions: Tuple[int, int] = (0, 0),
        warning_message: Optional[str] = None,
    ) -> ConversionResult:
        duration = time.perf_counter() - t_start
        # Deliberate design: 0-byte output is unconditionally treated as failure/corrupt because all
        # supported target formats (PDF, DOCX, XLSX, images, HTML, etc.) require header bytes or container structures.
        if not final_out.exists() or final_out.stat().st_size == 0:
            if final_out.exists():
                try:
                    final_out.unlink()
                except Exception as e:
                    logger.warning(f"Failed to unlink empty or corrupt output '{final_out}': {e}", exc_info=True)
            return ConversionResult(
                success=False,
                input_path=str(in_p),
                output_path=str(final_out),
                input_format=in_format,
                output_format=target_fmt_upper,
                input_dimensions=input_dimensions,
                output_dimensions=(0, 0),
                input_size_bytes=input_size,
                output_size_bytes=0,
                duration_seconds=duration,
                error_message=f"Conversion failed: output file '{final_out.name}' was not created or is 0 bytes (corrupt output).",
            )

        out_size = final_out.stat().st_size
        return ConversionResult(
            success=True,
            input_path=str(in_p),
            output_path=str(final_out),
            input_format=in_format,
            output_format=target_fmt_upper,
            input_dimensions=input_dimensions,
            output_dimensions=output_dimensions,
            input_size_bytes=input_size,
            output_size_bytes=out_size,
            duration_seconds=duration,
            error_message=warning_message,
        )

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
            logger.warning(f"File validation failed for '{in_p}' -> '{out_p}': {sec_err}")
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
            or (
                config.strip_metadata
                and not config.reencode
                and (in_ext == out_p.suffix.lower() or target_fmt_upper == in_ext.lstrip(".").upper())
            )
        ):
            from ..metadata.engine import strip_file_metadata
            strip_res = strip_file_metadata(in_p, out_p, password=config.password)
            if not strip_res["success"]:
                return ConversionResult(
                    success=False,
                    input_path=str(in_p),
                    output_path=str(out_p),
                    duration_seconds=time.perf_counter() - t_start,
                    error_message=strip_res.get("error_message") or "Failed to strip metadata",
                )
            return self._verify_and_create_result(
                in_p=in_p,
                final_out=out_p,
                in_format=in_ext.lstrip(".").upper(),
                target_fmt_upper=out_p.suffix.lstrip(".").upper(),
                input_size=input_size,
                t_start=t_start,
            )

        try:
            # -----------------------------------------------------------------
            # 1. PDF Input
            # -----------------------------------------------------------------
            if in_ext == ".pdf":
                in_format = "PDF"
                self.doc_converter.last_table_warning = None
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
                        in_p, out_p, password=config.password, enable_ocr=config.enable_ocr,
                        ocr_language=config.ocr_language,
                    )
                elif target_fmt_upper in ("CSV", "XLSX"):
                    final_out = self.doc_converter.convert_pdf_to_tables(
                        in_p, out_p, target_format=target_fmt_upper, password=config.password
                    )
                elif target_fmt_upper == "PPTX":
                    final_out = self.doc_converter.convert_pdf_to_pptx(in_p, out_p, password=config.password)
                    self.doc_converter.last_table_warning = (
                        "Each page is a picture on its own slide (text is in the speaker notes), so slides are not editable as text."
                    )
                else:
                    return ConversionResult(
                        success=False,
                        input_path=str(in_p),
                        output_path=str(out_p),
                        duration_seconds=time.perf_counter() - t_start,
                        error_message=f"Cannot convert PDF to {target_fmt_upper}",
                    )

                warning_msg = getattr(self.doc_converter, "last_table_warning", None)
                return self._verify_and_create_result(
                    in_p=in_p,
                    final_out=final_out,
                    in_format=in_format,
                    target_fmt_upper=target_fmt_upper,
                    input_size=input_size,
                    t_start=t_start,
                    warning_message=warning_msg,
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
                    final_out = self.rich_converter.convert_docx_to_rtf(in_p, out_p)
                elif target_fmt_upper == "PPTX":
                    return ConversionResult(
                        success=False,
                        input_path=str(in_p),
                        output_path=str(out_p),
                        duration_seconds=time.perf_counter() - t_start,
                        error_message="Direct Word to PowerPoint conversion is not supported without layout loss.",
                    )
                else:
                    return ConversionResult(
                        success=False,
                        input_path=str(in_p),
                        output_path=str(out_p),
                        duration_seconds=time.perf_counter() - t_start,
                        error_message=f"Cannot convert Word document to {target_fmt_upper}",
                    )

                return self._verify_and_create_result(
                    in_p=in_p,
                    final_out=final_out,
                    in_format=in_format,
                    target_fmt_upper=target_fmt_upper,
                    input_size=input_size,
                    t_start=t_start,
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
                    return ConversionResult(
                        success=False,
                        input_path=str(in_p),
                        output_path=str(out_p),
                        duration_seconds=time.perf_counter() - t_start,
                        error_message="Direct PowerPoint to Word conversion is not supported without layout loss.",
                    )
                else:
                    return ConversionResult(
                        success=False,
                        input_path=str(in_p),
                        output_path=str(out_p),
                        duration_seconds=time.perf_counter() - t_start,
                        error_message=f"Cannot convert PowerPoint presentation to {target_fmt_upper}",
                    )

                return self._verify_and_create_result(
                    in_p=in_p,
                    final_out=final_out,
                    in_format=in_format,
                    target_fmt_upper=target_fmt_upper,
                    input_size=input_size,
                    t_start=t_start,
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
                    final_out = self.rich_converter.convert_odt_to_rtf(in_p, out_p)
                else:
                    return ConversionResult(
                        success=False,
                        input_path=str(in_p),
                        output_path=str(out_p),
                        duration_seconds=time.perf_counter() - t_start,
                        error_message=f"Cannot convert ODT to {target_fmt_upper}",
                    )

                return self._verify_and_create_result(
                    in_p=in_p,
                    final_out=final_out,
                    in_format=in_format,
                    target_fmt_upper=target_fmt_upper,
                    input_size=input_size,
                    t_start=t_start,
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
                    final_out = self.rich_converter.convert_rtf_to_odt(in_p, out_p)
                else:
                    return ConversionResult(
                        success=False,
                        input_path=str(in_p),
                        output_path=str(out_p),
                        duration_seconds=time.perf_counter() - t_start,
                        error_message=f"Cannot convert RTF to {target_fmt_upper}",
                    )

                return self._verify_and_create_result(
                    in_p=in_p,
                    final_out=final_out,
                    in_format=in_format,
                    target_fmt_upper=target_fmt_upper,
                    input_size=input_size,
                    t_start=t_start,
                )

            # -----------------------------------------------------------------
            # 6. Plain Text Input (.txt)
            # -----------------------------------------------------------------
            elif in_ext == ".txt":
                in_format = "TXT"
                from ..text_io import read_text_file, xml_safe
                content = read_text_file(in_p)
                if target_fmt_upper == "PDF":
                    final_out = self.rich_converter._text_to_pdf(content, out_p, title=in_p.stem)
                elif target_fmt_upper == "DOCX":
                    import docx
                    from docx.shared import Pt
                    d = docx.Document()
                    normal = d.styles["Normal"]
                    normal.paragraph_format.space_after = Pt(0)
                    normal.paragraph_format.space_before = Pt(0)
                    for line in xml_safe(content).split("\n"):
                        # Keep indentation and blank lines exactly as written.
                        d.add_paragraph(line.replace("\t", "    "))
                    d.save(str(out_p))
                    final_out = out_p
                elif target_fmt_upper == "PPTX":
                    final_out = self.pres_converter.convert_text_to_pptx(in_p, out_p)
                elif target_fmt_upper == "RTF":
                    final_out = self.rich_converter.convert_text_to_rtf(in_p, out_p)
                elif target_fmt_upper == "HTML":
                    html_str = (
                        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
                        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
                        f"<title>{html.escape(in_p.stem)}</title></head>"
                        "<body style='font-family:sans-serif;line-height:1.6;padding:20px;max-width:900px;margin:auto;'>"
                        f"<pre dir='auto' style='white-space:pre-wrap;word-wrap:break-word;font-family:inherit'>{html.escape(content)}</pre>"
                        "</body></html>"
                    )
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

                return self._verify_and_create_result(
                    in_p=in_p,
                    final_out=final_out,
                    in_format=in_format,
                    target_fmt_upper=target_fmt_upper,
                    input_size=input_size,
                    t_start=t_start,
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

                return self._verify_and_create_result(
                    in_p=in_p,
                    final_out=final_out,
                    in_format=in_format,
                    target_fmt_upper=target_fmt_upper,
                    input_size=input_size,
                    t_start=t_start,
                )

            # -----------------------------------------------------------------
            # 8. Excel Input (.xlsx, .xls)
            # -----------------------------------------------------------------
            elif in_ext in (".xlsx", ".xls"):
                in_format = in_ext.lstrip(".").upper()
                self.data_converter.last_warning = None
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

                return self._verify_and_create_result(
                    in_p=in_p,
                    final_out=final_out,
                    in_format=in_format,
                    target_fmt_upper=target_fmt_upper,
                    input_size=input_size,
                    t_start=t_start,
                    warning_message=self.data_converter.last_warning,
                )

            # -----------------------------------------------------------------
            # 9. Image Input (Pillow + pillow-heif or OCR)
            # -----------------------------------------------------------------
            else:
                if target_fmt_upper == "DOCX":
                    in_format = in_p.suffix.lstrip(".").upper()
                    import io
                    import docx
                    from docx.shared import Inches, Length

                    # 1. Open image, force load to catch corrupt/truncated files, apply EXIF orientation
                    try:
                        with Image.open(in_p) as raw_im:
                            raw_im.load()
                            # EXIF auto-orientation (tags 3, 6, 8)
                            im = ImageOps.exif_transpose(raw_im)
                            if im is None:
                                im = raw_im.copy()
                            else:
                                im = im.copy()
                    except Exception as e:
                        logger.warning(f"Image-to-DOCX failed opening image '{in_p.name}': {e}", exc_info=True)
                        return ConversionResult(
                            success=False,
                            input_path=str(in_p),
                            output_path=str(out_p),
                            duration_seconds=round(time.time() - t_start, 3),
                            error_message=f"Corrupt or unreadable image file: {e}",
                        )

                    # 2. Format normalization: normalize any format/mode to PNG
                    # Pillow cannot save CMYK or I;16 as PNG directly without conversion.
                    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                        im = im.convert("RGBA")
                    elif im.mode == "CMYK":
                        im = im.convert("RGB")
                    elif im.mode in ("I;16", "I;16L", "I;16B"):
                        im = im.point(lambda i: i * (1.0 / 256.0)).convert("L").convert("RGB")
                    elif im.mode in ("I", "F"):
                        im = im.convert("RGB")
                    elif im.mode != "RGB":
                        im = im.convert("RGB")

                    img_buf = io.BytesIO()
                    im.save(img_buf, format="PNG")
                    img_buf.seek(0)
                    iw, ih = im.size

                    # 3. Fit-to-page calculation respecting page margins in EMU
                    d = docx.Document()
                    section = d.sections[0]
                    avail_w = section.page_width - section.left_margin - section.right_margin
                    avail_h = section.page_height - section.top_margin - section.bottom_margin

                    # Determine DPI (safe default: 96.0; guard against 0, negative, invalid)
                    dpi_x, dpi_y = 96.0, 96.0
                    raw_dpi = im.info.get("dpi")
                    if raw_dpi is not None:
                        try:
                            if isinstance(raw_dpi, (int, float)):
                                if raw_dpi > 0:
                                    dpi_x = dpi_y = float(raw_dpi)
                            elif isinstance(raw_dpi, (tuple, list)) and len(raw_dpi) >= 2:
                                dx, dy = float(raw_dpi[0]), float(raw_dpi[1])
                                if dx > 0:
                                    dpi_x = dx
                                if dy > 0:
                                    dpi_y = dy
                        except (ValueError, TypeError) as dpi_err:
                            logger.warning(f"Malformed DPI metadata {raw_dpi!r} in image '{in_p.name}': {dpi_err}. Defaulting to (96.0, 96.0).")
                            dpi_x, dpi_y = 96.0, 96.0

                    # Natural dimensions in EMUs (1 inch = 914,400 EMUs)
                    nat_w = max(1, int((iw / dpi_x) * 914400))
                    nat_h = max(1, int((ih / dpi_y) * 914400))

                    # Scale down ONLY if either dimension exceeds available page area, preserving aspect ratio.
                    # Policy: Small images are NOT upscaled (scale capped at 1.0) to avoid pixelation.
                    scale_w = avail_w / nat_w if nat_w > avail_w else 1.0
                    scale_h = avail_h / nat_h if nat_h > avail_h else 1.0
                    scale = min(scale_w, scale_h)

                    target_w = max(1, int(nat_w * scale))
                    target_h = max(1, int(nat_h * scale))

                    d.add_picture(img_buf, width=Length(target_w), height=Length(target_h))
                    d.save(str(out_p))
                    final_out = out_p
                    return self._verify_and_create_result(
                        in_p=in_p,
                        final_out=final_out,
                        in_format=in_format,
                        target_fmt_upper=target_fmt_upper,
                        input_size=input_size,
                        t_start=t_start,
                    )
                elif target_fmt_upper == "TXT":
                    in_format = in_p.suffix.lstrip(".").upper()
                    from ..ocr.engine import ocr_image_to_text
                    extracted_text = ocr_image_to_text(in_p, lang=config.ocr_language)
                    if not extracted_text.strip():
                        raise ValueError("No text was found in this image.")
                    out_p.write_text(extracted_text + "\n", encoding="utf-8")
                    final_out = out_p
                    return self._verify_and_create_result(
                        in_p=in_p,
                        final_out=final_out,
                        in_format=in_format,
                        target_fmt_upper=target_fmt_upper,
                        input_size=input_size,
                        t_start=t_start,
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
                    frame_count = getattr(src_img, "n_frames", 1) or 1
                    animated = bool(getattr(src_img, "is_animated", False)) and frame_count > 1
                    keep_frames = (
                        (animated and target_fmt_upper in ("GIF", "WEBP", "PNG"))
                        or (frame_count > 1 and in_format == "TIFF" and target_fmt_upper in ("TIFF", "PDF"))
                    )
                    icc = src_img.info.get("icc_profile") or None
                    sampling = -1
                    if in_format == "JPEG":
                        try:
                            from PIL import JpegImagePlugin
                            sampling = JpegImagePlugin.get_sampling(src_img)
                        except Exception:
                            sampling = -1

                    orientation_warning = None
                    exif_data = None
                    if keep_frames:
                        frames, durations = [], []
                        for index in range(frame_count):
                            src_img.seek(index)
                            frame = src_img.copy()
                            if animated:
                                frame = frame.convert("RGBA")
                            frames.append(frame)
                            durations.append(int(src_img.info.get("duration", 100) or 100))
                        src_img.seek(0)
                    else:
                        if config.auto_orient:
                            try:
                                work_img = ImageOps.exif_transpose(src_img)
                            except Exception as orient_err:
                                work_img = None
                                orientation_warning = f"Auto-orientation failed for '{in_p.name}': {orient_err}. Preserved original orientation."
                                logger.warning(orientation_warning, exc_info=True)
                            if work_img is None or work_img is src_img:
                                work_img = src_img.copy()
                        else:
                            work_img = src_img.copy()
                        if config.preserve_metadata:
                            exif_data = work_img.info.get("exif")
                        frames, durations = [work_img], []
                    loop = src_img.info.get("loop", 0)
                    source_dpi = src_img.info.get("dpi")

                prepared = []
                out_icc = None
                for frame in frames:
                    frame, out_icc = _apply_color_profile(frame, icc, target_fmt_upper, config.strip_metadata)
                    target_w, target_h = self.calculate_dimensions(frame.width, frame.height, config)
                    if (target_w, target_h) != frame.size:
                        frame = _to_8bit(frame) if frame.mode in ("I", "F") else frame
                        frame = frame.resize((target_w, target_h), resample=Image.Resampling.LANCZOS)
                    frame = _mode_for_target(frame, target_fmt_upper, config.background_color, self)
                    if target_fmt_upper == "PNG" and len(frames) == 1:
                        frame = _png_palette(frame, config.png_palette)
                    # Pillow re-embeds profiles/EXIF found in .info for some formats;
                    # only what we pass explicitly below may be written.
                    if frame is src_img:
                        frame = frame.copy()
                    frame.info.pop("icc_profile", None)
                    frame.info.pop("exif", None)
                    if config.strip_metadata:
                        # Comments, XMP and Photoshop/IPTC blocks can carry names and places.
                        frame.info = {
                            key: value for key, value in frame.info.items()
                            if key in ("transparency", "dpi", "duration", "loop", "background")
                        }
                    prepared.append(frame)
                work_img = prepared[0]
                out_w, out_h = work_img.size

                save_kwargs: Dict[str, object] = {}
                if out_icc and target_fmt_upper in ("JPG", "JPEG", "PNG", "WEBP", "TIFF", "HEIC", "HEIF"):
                    save_kwargs["icc_profile"] = out_icc

                if target_fmt_upper in ("JPG", "JPEG"):
                    quality = max(1, min(100, config.quality))
                    save_kwargs["quality"] = quality
                    save_kwargs["optimize"] = True
                    save_kwargs["progressive"] = True
                    # Keep the source's chroma sampling; full-resolution colour
                    # at high quality keeps text and red edges crisp.
                    save_kwargs["subsampling"] = sampling if sampling >= 0 else (0 if quality >= 90 else 2)
                    if exif_data:
                        save_kwargs["exif"] = exif_data
                elif target_fmt_upper == "PNG":
                    save_kwargs["optimize"] = work_img.size[0] * work_img.size[1] <= 4_000_000
                    if work_img.mode == "P" and "transparency" in work_img.info:
                        save_kwargs["transparency"] = work_img.info["transparency"]
                    save_kwargs["compress_level"] = 6
                    if exif_data:
                        save_kwargs["exif"] = exif_data
                elif target_fmt_upper == "WEBP":
                    save_kwargs["quality"] = max(1, min(100, config.quality))
                    save_kwargs["lossless"] = config.lossless
                    save_kwargs["method"] = 6 if work_img.size[0] * work_img.size[1] <= 12_000_000 else 4
                    if exif_data:
                        save_kwargs["exif"] = exif_data
                elif target_fmt_upper in ("HEIC", "HEIF"):
                    save_kwargs["quality"] = max(1, min(100, config.quality))
                    if exif_data:
                        save_kwargs["exif"] = exif_data
                elif target_fmt_upper == "TIFF":
                    if config.tiff_compression != "none":
                        compression = config.tiff_compression
                        if compression == "tiff_jpeg" and work_img.mode not in ("RGB", "L", "CMYK"):
                            compression = "tiff_deflate"
                        save_kwargs["compression"] = compression
                    if exif_data:
                        save_kwargs["exif"] = exif_data
                elif target_fmt_upper == "GIF":
                    if "transparency" in work_img.info:
                        save_kwargs["transparency"] = work_img.info["transparency"]
                elif target_fmt_upper == "ICO":
                    save_kwargs["sizes"] = [s for s in config.ico_sizes if s[0] <= max(out_w, out_h) * 4] or [config.ico_sizes[0]]
                elif target_fmt_upper == "PDF":
                    resolution = 100.0
                    if isinstance(source_dpi, (tuple, list)) and source_dpi and float(source_dpi[0] or 0) >= 50:
                        resolution = float(source_dpi[0])
                    save_kwargs["resolution"] = resolution

                if len(prepared) > 1:
                    save_kwargs["save_all"] = True
                    save_kwargs["append_images"] = prepared[1:]
                    if target_fmt_upper in ("GIF", "WEBP", "PNG"):
                        save_kwargs["duration"] = durations
                        save_kwargs["loop"] = loop
                        if target_fmt_upper == "GIF":
                            save_kwargs["disposal"] = 2
                            save_kwargs.pop("transparency", None)

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

                warning = orientation_warning
                if frame_count > 1 and not keep_frames and target_fmt_upper not in ("ICO",):
                    note = f"Only the first of {frame_count} frames was converted; {target_fmt_upper} holds a single image."
                    warning = f"{warning} {note}" if warning else note

                return self._verify_and_create_result(
                    in_p=in_p,
                    final_out=out_p,
                    in_format=in_format,
                    target_fmt_upper=target_fmt_upper,
                    input_dimensions=(orig_w, orig_h),
                    output_dimensions=(out_w, out_h),
                    input_size=input_size,
                    t_start=t_start,
                    warning_message=warning,
                )

        except Exception as e:
            logger.error(f"Conversion error for '{in_p.name}': {e}", exc_info=True)
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
                logger.error(f"Single task conversion raised unexpected exception for '{in_path}': {e}", exc_info=True)
                res = ConversionResult(
                    success=False,
                    input_path=str(in_path),
                    output_path=str(out_path),
                    error_message=f"Single conversion failure: {str(e)}",
                )
            if progress_callback:
                try:
                    progress_callback(1, 1, res)
                except Exception as e:
                    logger.warning(f"Progress callback error in single conversion: {e}", exc_info=True)
            return [res]

        workers = max_workers
        if workers is None:
            for _, _, cfg in tasks:
                if cfg.max_workers:
                    workers = cfg.max_workers
                    break
        if workers is None:
            # Keep the desktop responsive and limit concurrent decoded images.
            # Explicit --workers/config requests still override this default.
            workers = min(2, max(1, os.cpu_count() or 1))

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
                logger.error(f"Worker task conversion raised unexpected exception for '{in_p_task}': {e}", exc_info=True)
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
                except Exception as e:
                    logger.warning(f"Progress callback error in batch worker: {e}", exc_info=True)

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
                        except Exception as e:
                            logger.warning(f"Progress callback error on future error: {e}", exc_info=True)

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

        from ..metadata.engine import strip_file_metadata

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

    def split_pdf(
        self,
        input_path: str | Path,
        output_dir: str | Path,
        mode: str = "ranges",
        ranges: Optional[str] = None,
        n: int = 1,
    ) -> ConversionResult:
        """
        Split a PDF into multiple documents according to mode and ranges.
        Validates page ranges upfront and returns ConversionResult(success=False, error_message=...)
        on any validation or processing failure.
        """
        t_start = time.perf_counter()
        in_p = Path(input_path).resolve()
        out_d = Path(output_dir).resolve()

        if not in_p.is_file():
            return ConversionResult(
                success=False,
                input_path=str(in_p),
                output_path=str(out_d),
                duration_seconds=0.0,
                error_message=f"Input file not found: {in_p}",
            )

        try:
            from ..pdf.tools import split_pdf as core_split_pdf
            generated = core_split_pdf(in_p, out_d, mode=mode, ranges=ranges, n=n)
            if not generated:
                return ConversionResult(
                    success=False,
                    input_path=str(in_p),
                    output_path=str(out_d),
                    duration_seconds=time.perf_counter() - t_start,
                    error_message="Split produced no files.",
                )
            first_out = Path(generated[0])
            res = self._verify_and_create_result(
                in_p=in_p,
                final_out=first_out,
                in_format="PDF",
                target_fmt_upper="PDF",
                input_size=in_p.stat().st_size if in_p.exists() else 0,
                t_start=t_start,
            )
            res.output_path = str(out_d)
            return res
        except Exception as e:
            logger.error(f"PDF split failed for '{in_p}': {e}", exc_info=True)
            return ConversionResult(
                success=False,
                input_path=str(in_p),
                output_path=str(out_d),
                duration_seconds=time.perf_counter() - t_start,
                error_message=str(e),
            )

    def compress_pdf(
        self,
        input_path: str | Path,
        output_path: str | Path,
        level: str = "medium",
    ) -> ConversionResult:
        """
        Compress a PDF document.
        Validates output size, page count, and returns ConversionResult.
        """
        t_start = time.perf_counter()
        in_p = Path(input_path).resolve()
        out_p = Path(output_path).resolve()

        if not in_p.is_file():
            return ConversionResult(
                success=False,
                input_path=str(in_p),
                output_path=str(out_p),
                duration_seconds=0.0,
                error_message=f"Input file not found: {in_p}",
            )

        try:
            from ..pdf.tools import compress_pdf as core_compress_pdf
            stats = core_compress_pdf(in_p, out_p, level=level)
            res = self._verify_and_create_result(
                in_p=in_p,
                final_out=out_p,
                in_format="PDF",
                target_fmt_upper="PDF",
                input_size=in_p.stat().st_size if in_p.exists() else 0,
                t_start=t_start,
            )
            return res
        except Exception as e:
            logger.error(f"PDF compression failed for '{in_p}': {e}", exc_info=True)
            return ConversionResult(
                success=False,
                input_path=str(in_p),
                output_path=str(out_p),
                duration_seconds=time.perf_counter() - t_start,
                error_message=str(e),
            )


# Export UniversalConverterEngine alias
UniversalConverterEngine = ImageConverterEngine


