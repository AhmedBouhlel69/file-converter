"""
Security and validation module for Universal File Converter.
Guards against path traversal, zip bombs, corrupted headers, and oversized files.
"""

from __future__ import annotations

import os
import zipfile
from pathlib import Path
from typing import Optional, Set


class SecurityError(Exception):
    """Raised when a security validation check fails."""
    pass


# Magic byte signatures for known file formats
MAGIC_SIGNATURES = {
    "PDF": [b"%PDF-"],
    "PNG": [b"\x89PNG\r\n\x1a\n"],
    "JPEG": [b"\xff\xd8\xff"],
    "GIF": [b"GIF87a", b"GIF89a"],
    "BMP": [b"BM"],
    "TIFF": [b"II*\x00", b"MM\x00*"],
    "RTF": [b"{\\rtf", b"{\\urtf"],
    "ZIP": [b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"],
}

# Suffixes that represent ZIP-based OpenPackaging formats
ZIP_BASED_EXTENSIONS: Set[str] = {
    ".docx", ".xlsx", ".pptx", ".odt",
}

# Image extensions mapped to magic types
IMAGE_MAGIC_MAP = {
    ".png": "PNG",
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".jpe": "JPEG",
    ".gif": "GIF",
    ".bmp": "BMP",
    ".dib": "BMP",
    ".tiff": "TIFF",
    ".tif": "TIFF",
}


def validate_output_path(output_path: Path | str, base_dir: Optional[Path | str] = None) -> Path:
    """
    Validate that the destination path is safe and does not perform path traversal.
    If base_dir is supplied, ensures output_path is strictly within base_dir.
    """
    path_str = str(output_path)
    if "\x00" in path_str:
        raise SecurityError("Null byte detected in output path.")

    out_p = Path(output_path).resolve()

    if base_dir:
        base_p = Path(base_dir).resolve()
        try:
            out_p.relative_to(base_p)
        except ValueError:
            raise SecurityError(f"Path traversal detected: {out_p} escapes base directory {base_p}")

    return out_p


def sniff_file_type(file_path: Path | str) -> Optional[str]:
    """
    Inspect initial magic bytes to determine actual file format.
    Returns format string (e.g. 'PDF', 'PNG', 'ZIP', 'WEBP', 'RTF') or None if unknown.
    """
    p = Path(file_path)
    if not p.is_file() or p.stat().st_size == 0:
        return None

    with open(p, "rb") as f:
        header = f.read(32)

    if header.startswith(b"RIFF") and len(header) >= 12 and header[8:12] == b"WEBP":
        return "WEBP"

    for fmt_name, signatures in MAGIC_SIGNATURES.items():
        for sig in signatures:
            if header.startswith(sig):
                return fmt_name

    # Check for HEIF / HEIC container (ftypheic or ftypmif1 or ftypmsf1)
    if len(header) >= 12 and header[4:8] == b"ftyp":
        brand = header[8:12]
        if brand in (b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1"):
            return "HEIC"

    return None


def validate_zip_container(
    file_path: Path | str,
    max_ratio: float = 100.0,
    max_uncompressed_bytes: int = 500 * 1024 * 1024,
    max_entries: int = 50000,
) -> bool:
    """
    Inspect a ZIP-based document (.docx, .xlsx, .pptx, .odt) to defend against zip bombs.
    Checks compression ratio, total uncompressed size, and entry count.
    """
    p = Path(file_path)
    if not zipfile.is_zipfile(p):
        raise ValueError(f"File is not a valid ZIP archive: {p.name}")

    total_compressed = 0
    total_uncompressed = 0
    entry_count = 0

    with zipfile.ZipFile(p, "r") as zf:
        infolist = zf.infolist()
        entry_count = len(infolist)
        if entry_count > max_entries:
            raise SecurityError(
                f"Suspicious zip container: contains {entry_count} files (limit {max_entries})"
            )

        for info in infolist:
            total_compressed += info.compress_size
            total_uncompressed += info.file_size

            # Check individual entry limit
            if info.file_size > max_uncompressed_bytes:
                raise SecurityError(
                    f"Suspicious zip entry: file '{info.filename}' uncompressed size exceeds limit"
                )

        if total_uncompressed > max_uncompressed_bytes:
            raise SecurityError(
                f"Zip bomb detected: total uncompressed size ({total_uncompressed} bytes) "
                f"exceeds limit ({max_uncompressed_bytes} bytes)"
            )

        if total_compressed > 0:
            ratio = total_uncompressed / total_compressed
            if ratio > max_ratio and total_uncompressed > 10 * 1024 * 1024:
                raise SecurityError(
                    f"Zip bomb detected: decompression ratio {ratio:.1f}:1 exceeds threshold {max_ratio}:1"
                )

    return True


def validate_input_file(
    file_path: Path | str,
    max_size_bytes: int = 500 * 1024 * 1024,
) -> None:
    """
    Run comprehensive security and integrity validation on an input file before processing:
    1. Existence
    2. Non-zero size
    3. Maximum size threshold
    4. Magic byte signature matching
    5. Zip bomb inspection for container formats
    """
    p = Path(file_path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"Input file not found: {p}")

    if not p.is_file():
        raise ValueError(f"Input path is not a file: {p}")

    size = p.stat().st_size
    if size == 0:
        raise ValueError("Input file is empty (0 bytes).")

    if size > max_size_bytes:
        raise ValueError(
            f"Input file size ({size / (1024 * 1024):.1f} MB) exceeds maximum allowed limit "
            f"({max_size_bytes / (1024 * 1024):.1f} MB)."
        )

    ext = p.suffix.lower()

    # Verify zip-based documents
    if ext in ZIP_BASED_EXTENSIONS:
        try:
            with open(p, "rb") as f:
                head = f.read(8)
                if head == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
                    f.seek(0)
                    data = f.read(4096)
                    if b"EncryptedPackage" in data or b"EncryptionInfo" in data:
                        raise ValueError(f"{ext.lstrip('.').upper()} document is encrypted / password-protected.")
        except ValueError:
            raise
        except Exception:
            pass

        sniffed = sniff_file_type(p)
        if sniffed != "ZIP":
            raise ValueError(f"Corrupted or invalid {ext.upper()} file (missing ZIP header signature).")
        validate_zip_container(p)

    # Verify PDF
    elif ext == ".pdf":
        sniffed = sniff_file_type(p)
        if sniffed != "PDF":
            raise ValueError("Corrupted or invalid PDF file (missing %PDF- header).")

    # Verify RTF
    elif ext == ".rtf":
        sniffed = sniff_file_type(p)
        if sniffed != "RTF":
            raise ValueError("Corrupted or invalid RTF file (missing {\\rtf header).")

    # Verify recognized image formats
    elif ext in IMAGE_MAGIC_MAP:
        expected = IMAGE_MAGIC_MAP[ext]
        sniffed = sniff_file_type(p)
        if sniffed and sniffed != expected:
            raise ValueError(
                f"File signature mismatch: file has extension '{ext}' but signature indicates '{sniffed}'."
            )
