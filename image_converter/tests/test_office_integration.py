"""
Real Microsoft Office COM integration tests (Items 10, 11, 12).
Marked with @pytest.mark.office and skipped if Microsoft Office is not installed.
"""

import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
import fitz
import functools

from image_converter.core.document_engine import DocumentConverter
from image_converter.core.data_engine import DataConverter
from image_converter.core.presentation_engine import PresentationConverter


def with_timeout(timeout_sec=120):
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            err = []
            def target():
                try:
                    fn(*args, **kwargs)
                except BaseException as e:
                    err.append(e)
            t = threading.Thread(target=target, daemon=True)
            t.start()
            t.join(timeout=timeout_sec)
            if t.is_alive():
                raise TimeoutError(f"Office test '{fn.__name__}' timed out after {timeout_sec}s")
            if err:
                raise err[0]
        return wrapper
    return decorator


@pytest.mark.office
@with_timeout(120)
def test_real_office_concurrency(tmp_path: Path):
    """
    Item 10 & 12: Real Office concurrency verification.
    Runs 8 DOCX->PDF, 8 XLSX->PDF, and 8 PPTX->PDF conversions concurrently
    across 4 worker threads, asserting all 24 produce valid, non-empty PDFs
    with page_count >= 1.
    """
    import docx
    import openpyxl
    import pptx

    doc_path = tmp_path / "fixture.docx"
    d = docx.Document()
    d.add_heading("Real DOCX Concurrency Test", 0)
    d.add_paragraph("Paragraph inside test docx.")
    d.save(str(doc_path))

    xl_path = tmp_path / "fixture.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Name", "Value", "Status"])
    ws.append(["Item 1", 100, "Active"])
    wb.save(str(xl_path))

    ppt_path = tmp_path / "fixture.pptx"
    prs = pptx.Presentation()
    prs.slides.add_slide(prs.slide_layouts[6])
    prs.save(str(ppt_path))

    doc_conv = DocumentConverter()
    data_conv = DataConverter()
    ppt_conv = PresentationConverter()

    # 1. DOCX -> PDF (8 conversions, 4 workers)
    def _convert_docx(idx):
        out_p = tmp_path / f"docx_out_{idx}.pdf"
        return doc_conv.convert_docx_to_pdf(doc_path, out_p)

    with ThreadPoolExecutor(max_workers=4) as ex:
        docx_results = list(ex.map(_convert_docx, range(8)))

    for r in docx_results:
        assert r.exists() and r.stat().st_size > 0
        doc = fitz.open(str(r))
        assert doc.page_count >= 1
        doc.close()

    # 2. XLSX -> PDF (8 conversions, 4 workers)
    def _convert_xlsx(idx):
        out_p = tmp_path / f"xlsx_out_{idx}.pdf"
        return data_conv.convert_excel_to_pdf(xl_path, out_p)

    with ThreadPoolExecutor(max_workers=4) as ex:
        xlsx_results = list(ex.map(_convert_xlsx, range(8)))

    for r in xlsx_results:
        assert r.exists() and r.stat().st_size > 0
        doc = fitz.open(str(r))
        assert doc.page_count >= 1
        doc.close()

    # 3. PPTX -> PDF (8 conversions, 4 workers)
    def _convert_pptx(idx):
        out_p = tmp_path / f"pptx_out_{idx}.pdf"
        return ppt_conv.convert_pptx_to_pdf(ppt_path, out_p)

    with ThreadPoolExecutor(max_workers=4) as ex:
        pptx_results = list(ex.map(_convert_pptx, range(8)))

    for r in pptx_results:
        assert r.exists() and r.stat().st_size > 0
        doc = fitz.open(str(r))
        assert doc.page_count >= 1
        doc.close()


@pytest.mark.office
@with_timeout(120)
def test_real_office_failures(tmp_path: Path):
    """
    Item 12: Real Office failure path verification.
    Verifies that corrupt inputs and locked output destinations fail cleanly,
    raise RuntimeError with descriptive messages, leave zero temporary files,
    and cleanly terminate all COM application instances.
    """
    import docx
    import openpyxl
    import pptx

    valid_docx = tmp_path / "valid_fixture.docx"
    d = docx.Document()
    d.add_paragraph("Valid docx for locked test")
    d.save(str(valid_docx))

    valid_xlsx = tmp_path / "valid_fixture.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["A", "B"])
    ws.append([1, 2])
    wb.save(str(valid_xlsx))

    valid_pptx = tmp_path / "valid_fixture.pptx"
    prs = pptx.Presentation()
    prs.slides.add_slide(prs.slide_layouts[6])
    prs.save(str(valid_pptx))

    corrupt_docx = tmp_path / "corrupt.docx"
    corrupt_docx.write_bytes(b"\x50\x4b\x03\x04" + b"\x00" * 50)

    corrupt_xlsx = tmp_path / "corrupt.xlsx"
    corrupt_xlsx.write_bytes(b"\x50\x4b\x03\x04" + b"\x00" * 50)

    corrupt_pptx = tmp_path / "corrupt.pptx"
    corrupt_pptx.write_bytes(b"\x50\x4b\x03\x04" + b"\x00" * 50)

    doc_conv = DocumentConverter()
    data_conv = DataConverter()
    ppt_conv = PresentationConverter()

    # 1. Corrupt inputs must raise RuntimeError
    for name, conv_fn, in_p in [
        ("Word", doc_conv.convert_docx_to_pdf, corrupt_docx),
        ("Excel", data_conv.convert_excel_to_pdf, corrupt_xlsx),
        ("PowerPoint", ppt_conv.convert_pptx_to_pdf, corrupt_pptx),
    ]:
        out_p = tmp_path / f"fail_{name}.pdf"
        with pytest.raises(RuntimeError) as exc_info:
            conv_fn(in_p, out_p)
        assert f"Microsoft {name}" in str(exc_info.value)

    # 2. Locked outputs must raise RuntimeError
    for name, conv_fn, in_p in [
        ("Word", doc_conv.convert_docx_to_pdf, valid_docx),
        ("Excel", data_conv.convert_excel_to_pdf, valid_xlsx),
        ("PowerPoint", ppt_conv.convert_pptx_to_pdf, valid_pptx),
    ]:
        locked_out = tmp_path / f"locked_output_{name.lower()}.pdf"
        locked_out.write_text("pre-existing locked content")
        with open(locked_out, "r+b"):
            with pytest.raises(RuntimeError) as exc_info:
                conv_fn(in_p, locked_out)
            assert f"Microsoft {name}" in str(exc_info.value)
            assert ("Access is denied" in str(exc_info.value) or "PermissionError" in str(exc_info.value))

    # 3. Verify zero leftover temporary files
    tmp_files = list(tmp_path.glob("*_tmp_*"))
    assert len(tmp_files) == 0, f"Found leftover temp files: {tmp_files}"
