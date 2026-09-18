"""
Tests for security protections: path traversal, zip bombs, and magic byte sniffing.
"""

import io
import zipfile
from pathlib import Path
import pytest

from image_converter.core.security import (
    SecurityError,
    validate_output_path,
    sniff_file_type,
    validate_zip_container,
    validate_input_file,
)


def test_validate_output_path_safe(tmp_path: Path):
    safe_out = tmp_path / "sub" / "output.png"
    validated = validate_output_path(safe_out, base_dir=tmp_path)
    assert validated.resolve() == safe_out.resolve()


def test_validate_output_path_null_byte():
    with pytest.raises(SecurityError, match="Null byte"):
        validate_output_path("output\x00.png")


def test_validate_output_path_traversal(tmp_path: Path):
    base_dir = tmp_path / "sandbox"
    base_dir.mkdir()
    traversal_path = base_dir / ".." / "escaped.png"

    with pytest.raises(SecurityError, match="Path traversal detected"):
        validate_output_path(traversal_path, base_dir=base_dir)


def test_sniff_magic_bytes(tmp_path: Path):
    # PDF
    pdf_file = tmp_path / "test.pdf"
    pdf_file.write_bytes(b"%PDF-1.7\n%...")
    assert sniff_file_type(pdf_file) == "PDF"

    # PNG
    png_file = tmp_path / "test.png"
    png_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00")
    assert sniff_file_type(png_file) == "PNG"

    # JPEG
    jpg_file = tmp_path / "test.jpg"
    jpg_file.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF")
    assert sniff_file_type(jpg_file) == "JPEG"

    # RTF
    rtf_file = tmp_path / "test.rtf"
    rtf_file.write_bytes(b"{\\rtf1\\ansi Hello}")
    assert sniff_file_type(rtf_file) == "RTF"


def test_zip_container_safe(tmp_path: Path):
    zip_path = tmp_path / "sample.docx"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("[Content_Types].xml", b"<xml></xml>")
        zf.writestr("word/document.xml", b"<w:document></w:document>")

    assert validate_zip_container(zip_path) is True


def test_zip_bomb_entry_limit(tmp_path: Path):
    zip_path = tmp_path / "too_many_files.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for i in range(15):
            zf.writestr(f"file_{i}.txt", b"A")

    # Limit to 10 entries
    with pytest.raises(SecurityError, match="Suspicious zip container: contains 15 files"):
        validate_zip_container(zip_path, max_entries=10)


def test_zip_bomb_uncompressed_limit(tmp_path: Path):
    zip_path = tmp_path / "oversized.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("big.txt", b"0" * 1000)

    # Max 500 bytes uncompressed (triggers entry limit or total uncompressed limit)
    with pytest.raises(SecurityError, match="uncompressed size exceeds limit"):
        validate_zip_container(zip_path, max_uncompressed_bytes=500)


def test_file_signature_mismatch(tmp_path: Path):
    # A text file renamed to .png
    fake_png = tmp_path / "fake.png"
    fake_png.write_bytes(b"This is not a real PNG image, just plain text.")

    # validate_input_file should detect mismatch or corrupt signature
    # In this case, signature is unknown so sniffed is None, but let's test JPEG renamed to PNG
    real_jpg_as_png = tmp_path / "jpg_as_png.png"
    real_jpg_as_png.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF....")

    with pytest.raises(ValueError, match="File signature mismatch"):
        validate_input_file(real_jpg_as_png)
