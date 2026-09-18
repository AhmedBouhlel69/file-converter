"""
Unit tests for edge cases: corrupted files, encrypted documents, 0-byte files,
and non-UTF-8 CSV encodings.
"""

from pathlib import Path
import fitz
import pandas as pd
import pytest

from image_converter.core.engine import (
    ConversionConfig,
    ImageConverterEngine,
)
from image_converter.core.document_engine import (
    open_pdf_with_password,
    check_docx_encryption,
)


@pytest.fixture
def engine():
    return ImageConverterEngine()


def test_empty_zero_byte_file_rejected(engine, tmp_path: Path):
    empty_file = tmp_path / "empty.pdf"
    empty_file.touch()  # 0 bytes

    out_file = tmp_path / "out.txt"
    res = engine.convert_single(empty_file, out_file, ConversionConfig(target_format="TXT"))

    assert res.success is False
    assert "empty (0 bytes)" in res.error_message.lower()


def test_corrupted_pdf_header_rejected(engine, tmp_path: Path):
    corrupt_pdf = tmp_path / "bad.pdf"
    corrupt_pdf.write_bytes(b"CORRUPT HEADER NOT A REAL PDF FILE")

    out_file = tmp_path / "out.txt"
    res = engine.convert_single(corrupt_pdf, out_file, ConversionConfig(target_format="TXT"))

    assert res.success is False
    assert "corrupted or invalid pdf" in res.error_message.lower()


def test_encrypted_pdf_handling(engine, tmp_path: Path):
    pdf_path = tmp_path / "locked.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Confidential Protected Content")

    # Encrypt with owner and user passwords
    # Perm 0, encryption standard
    perm = fitz.PDF_PERM_ACCESSIBILITY | fitz.PDF_PERM_PRINT
    doc.save(
        str(pdf_path),
        encryption=fitz.PDF_ENCRYPT_AES_256,
        owner_pw="secret_owner",
        user_pw="secret123",
        permissions=perm,
    )
    doc.close()

    # 1. Attempt conversion without password -> should fail with encryption message
    out_fail = tmp_path / "fail.txt"
    res_fail = engine.convert_single(pdf_path, out_fail, ConversionConfig(target_format="TXT"))
    assert res_fail.success is False
    assert "encrypted" in res_fail.error_message.lower() or "password" in res_fail.error_message.lower()

    # 2. Attempt with wrong password -> should fail
    res_wrong = engine.convert_single(
        pdf_path,
        out_fail,
        ConversionConfig(target_format="TXT", password="wrong_password"),
    )
    assert res_wrong.success is False
    assert "incorrect password" in res_wrong.error_message.lower()

    # 3. Attempt with correct password -> should succeed!
    out_ok = tmp_path / "unlocked.txt"
    res_ok = engine.convert_single(
        pdf_path,
        out_ok,
        ConversionConfig(target_format="TXT", password="secret123"),
    )
    assert res_ok.success is True
    assert out_ok.is_file()
    assert "Confidential Protected Content" in out_ok.read_text(encoding="utf-8")


def test_encrypted_docx_detection(tmp_path: Path):
    # Construct a synthetic OLE compound header with EncryptedPackage marker
    fake_enc_docx = tmp_path / "encrypted.docx"
    ole_header = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    ole_body = b"Padding " * 20 + b"EncryptedPackage" + b" " * 100
    fake_enc_docx.write_bytes(ole_header + ole_body)

    with pytest.raises(ValueError, match="encrypted / password-protected"):
        check_docx_encryption(fake_enc_docx)


def test_non_utf8_csv_latin1_and_cp1252(engine, tmp_path: Path):
    # Write a CSV with accented French/German characters encoded in Latin-1 / CP1252
    csv_latin1 = tmp_path / "data_latin1.csv"
    raw_content = "Name,City,Price\nRené,Zürich,€50\nÉlise,München,€75\n"
    # Encode with cp1252
    csv_latin1.write_bytes(raw_content.encode("cp1252"))

    # Convert to Excel
    out_xlsx = tmp_path / "converted_latin1.xlsx"
    res_xlsx = engine.convert_single(
        csv_latin1,
        out_xlsx,
        ConversionConfig(target_format="XLSX"),
    )
    assert res_xlsx.success is True
    assert out_xlsx.is_file()

    # Convert to TXT
    out_txt = tmp_path / "converted_latin1.txt"
    res_txt = engine.convert_single(
        csv_latin1,
        out_txt,
        ConversionConfig(target_format="TXT"),
    )
    assert res_txt.success is True
    assert "René" in out_txt.read_text(encoding="utf-8")


def test_non_utf8_csv_utf16(engine, tmp_path: Path):
    csv_utf16 = tmp_path / "data_utf16.csv"
    raw_content = "Product,Qty,Notes\nWidget,100,Sample UTF-16\nGadget,200,Verified\n"
    csv_utf16.write_bytes(raw_content.encode("utf-16"))

    out_xlsx = tmp_path / "converted_utf16.xlsx"
    res = engine.convert_single(csv_utf16, out_xlsx, ConversionConfig(target_format="XLSX"))
    assert res.success is True
    assert out_xlsx.is_file()


def test_oversized_file_limit(engine, tmp_path: Path):
    sample = tmp_path / "oversized.txt"
    sample.write_bytes(b"A" * 1024)

    out = tmp_path / "out.pdf"
    # Set max_file_size to 512 bytes
    cfg = ConversionConfig(target_format="PDF", max_file_size=512)
    res = engine.convert_single(sample, out, cfg)

    assert res.success is False
    assert "exceeds maximum allowed limit" in res.error_message.lower()
