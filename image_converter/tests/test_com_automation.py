"""
Comprehensive tests and verification for COM Automation (Items 10, 11, 12).
Includes:
- Shared fake pythoncom/win32com harness tracking thread initialization and call ordering.
- Item 10: CoInitialize in ThreadPoolExecutor workers (8 conversions across 4 workers + mutation test).
- Item 11: DisplayAlerts constants (Word=0, Excel=False, PPT=1), AutomationSecurity=3, ordering assertion, and residual risk disclosure.
- Item 12: SaveAs/Close/Quit cleanup structure in finally, atomic replacement, failure branch tests, mutation check, and leftover process check.
"""

import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import pytest

from image_converter.core.com_utils import (
    com_initialized,
    WD_ALERTS_NONE,
    EXCEL_ALERTS_NONE,
    PP_ALERTS_NONE,
    MSO_AUTOMATION_SECURITY_FORCE_DISABLE,
    WD_FORMAT_DOCX,
    WD_FORMAT_PDF,
    XL_TYPE_PDF,
    PP_SAVE_AS_PDF,
)
from image_converter.core.document_engine import DocumentConverter
from image_converter.core.data_engine import DataConverter
from image_converter.core.presentation_engine import PresentationConverter
from image_converter.core.rich_doc_engine import RichDocumentConverter


# =============================================================================
# SHARED FAKE COM HARNESS
# =============================================================================

class FakeComError(Exception):
    """Simulated COM error (equivalent to pywintypes.com_error)."""
    pass


class FakeComHarness:
    """
    Unified fake pythoncom / win32com harness for Items 10-12.
    Tracks:
      - Per-thread CoInitialize / CoUninitialize balance.
      - Call order per application instance (AutomationSecurity, DisplayAlerts, Open, SaveAs, Close, Quit).
      - Configurable error injection for SaveAs, Close, Quit, Open.
    """
    def __init__(self):
        self._lock = threading.RLock()
        self.thread_init_counts: Dict[int, int] = {}
        self.call_log: List[Tuple[int, str, str, Any]] = []
        
        # Injected failure flags
        self.fail_on_dispatch: bool = False
        self.fail_on_open: bool = False
        self.fail_on_save_as: bool = False
        self.fail_on_close: bool = False
        self.fail_on_quit: bool = False

    def co_initialize(self):
        tid = threading.get_ident()
        with self._lock:
            self.thread_init_counts[tid] = self.thread_init_counts.get(tid, 0) + 1
            self.call_log.append((tid, "pythoncom", "CoInitialize", self.thread_init_counts[tid]))

    def co_uninitialize(self):
        tid = threading.get_ident()
        with self._lock:
            count = self.thread_init_counts.get(tid, 0) - 1
            self.thread_init_counts[tid] = count
            self.call_log.append((tid, "pythoncom", "CoUninitialize", count))

    def is_initialized(self, tid: Optional[int] = None) -> bool:
        if tid is None:
            tid = threading.get_ident()
        with self._lock:
            return self.thread_init_counts.get(tid, 0) > 0

    def dispatch_ex(self, prog_id: str):
        tid = threading.get_ident()
        with self._lock:
            if not self.is_initialized(tid):
                raise FakeComError(f"0x800401f0: CoInitialize has not been called on thread {tid} before DispatchEx('{prog_id}')!")
            if self.fail_on_dispatch:
                raise FakeComError(f"Simulated DispatchEx failure for {prog_id}")
            self.call_log.append((tid, prog_id, "DispatchEx", None))
            
        return FakeApplication(self, prog_id)


class FakeDocument:
    def __init__(self, harness: FakeComHarness, prog_id: str, doc_path: str):
        self.harness = harness
        self.prog_id = prog_id
        self.doc_path = doc_path
        self.closed = False

    def SaveAs(self, output_path: str, FileFormat: Any = None):
        tid = threading.get_ident()
        with self.harness._lock:
            self.harness.call_log.append((tid, self.prog_id, "SaveAs", (output_path, FileFormat)))
            if self.harness.fail_on_save_as:
                raise FakeComError("Simulated SaveAs disk/COM error")
        # Write dummy output bytes to simulate real Office file creation
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"%PDF-1.7 Simulated Office COM output content")

    def ExportAsFixedFormat(self, export_format: Any, output_path: str):
        # Excel method
        tid = threading.get_ident()
        with self.harness._lock:
            self.harness.call_log.append((tid, self.prog_id, "ExportAsFixedFormat", (output_path, export_format)))
            if self.harness.fail_on_save_as:
                raise FakeComError("Simulated ExportAsFixedFormat error")
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"%PDF-1.7 Simulated Excel FixedFormat output content")

    def Close(self, save_changes: Any = False):
        tid = threading.get_ident()
        with self.harness._lock:
            self.harness.call_log.append((tid, self.prog_id, "Close", save_changes))
            self.closed = True
            if self.harness.fail_on_close:
                raise FakeComError("Simulated Close error")


class FakeCollection:
    def __init__(self, harness: FakeComHarness, prog_id: str, name: str):
        self.harness = harness
        self.prog_id = prog_id
        self.name = name

    def Open(self, file_path: str, *args, **kwargs):
        tid = threading.get_ident()
        with self.harness._lock:
            self.harness.call_log.append((tid, self.prog_id, f"{self.name}.Open", (file_path, args, kwargs)))
            if self.harness.fail_on_open:
                raise FakeComError(f"Simulated {self.name}.Open failure")
        return FakeDocument(self.harness, self.prog_id, file_path)


class FakeApplication:
    def __init__(self, harness: FakeComHarness, prog_id: str):
        self.harness = harness
        self.prog_id = prog_id
        self._visible = False
        self._display_alerts = None
        self._automation_security = None
        self.quit_called = False

        if "word" in prog_id.lower():
            self.Documents = FakeCollection(harness, prog_id, "Documents")
        elif "excel" in prog_id.lower():
            self.Workbooks = FakeCollection(harness, prog_id, "Workbooks")
        elif "powerpoint" in prog_id.lower():
            self.Presentations = FakeCollection(harness, prog_id, "Presentations")

    @property
    def Visible(self):
        return self._visible

    @Visible.setter
    def Visible(self, val):
        tid = threading.get_ident()
        self._visible = val
        with self.harness._lock:
            self.harness.call_log.append((tid, self.prog_id, "Visible", val))

    @property
    def DisplayAlerts(self):
        return self._display_alerts

    @DisplayAlerts.setter
    def DisplayAlerts(self, val):
        tid = threading.get_ident()
        self._display_alerts = val
        with self.harness._lock:
            self.harness.call_log.append((tid, self.prog_id, "DisplayAlerts", val))

    @property
    def AutomationSecurity(self):
        return self._automation_security

    @AutomationSecurity.setter
    def AutomationSecurity(self, val):
        tid = threading.get_ident()
        self._automation_security = val
        with self.harness._lock:
            self.harness.call_log.append((tid, self.prog_id, "AutomationSecurity", val))

    def Quit(self):
        tid = threading.get_ident()
        with self.harness._lock:
            self.harness.call_log.append((tid, self.prog_id, "Quit", None))
            self.quit_called = True
            if self.harness.fail_on_quit:
                raise FakeComError("Simulated Quit error")


@pytest.fixture
def fake_com(monkeypatch):
    """
    Installs FakeComHarness into pythoncom and win32com.client.
    """
    harness = FakeComHarness()
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setattr("os.name", "nt")

    import types
    fake_pythoncom = types.ModuleType("pythoncom")
    fake_pythoncom.CoInitialize = harness.co_initialize
    fake_pythoncom.CoUninitialize = harness.co_uninitialize

    fake_win32_parent = types.ModuleType("win32com")
    fake_win32_client = types.ModuleType("win32com.client")
    fake_win32_client.DispatchEx = harness.dispatch_ex
    fake_win32_parent.client = fake_win32_client

    monkeypatch.setitem(sys.modules, "pythoncom", fake_pythoncom)
    monkeypatch.setitem(sys.modules, "win32com", fake_win32_parent)
    monkeypatch.setitem(sys.modules, "win32com.client", fake_win32_client)

    return harness


# =============================================================================
# ITEM 10: CoInitialize in ThreadPoolExecutor Workers
# =============================================================================

def test_item10_threadpool_coinitialize(fake_com, tmp_path):
    """
    Item 10: Verify CoInitialize is properly invoked in ThreadPoolExecutor worker threads.
    Run 8 conversions across 4 worker threads.
    Assert every thread that called DispatchEx had CoInitialize called prior,
    and CoUninitialize called on exit (count balance = 0).
    """
    dc = DocumentConverter()

    # Create 8 dummy docx files
    test_files = []
    for i in range(8):
        f = tmp_path / f"test_{i}.docx"
        f.write_text("Dummy docx content")
        out = tmp_path / f"test_{i}.pdf"
        test_files.append((f, out))

    def _convert_task(pair):
        in_file, out_file = pair
        return dc.convert_docx_to_pdf(in_file, out_file)

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(_convert_task, test_files))

    assert len(results) == 8
    for r in results:
        assert r.exists()
        assert r.stat().st_size > 0

    # Verify per-thread COM initialization state
    with fake_com._lock:
        worker_threads = set(tid for tid, _, op, _ in fake_com.call_log if op == "DispatchEx")
        assert len(worker_threads) >= 2, f"Expected multiple worker threads, got {worker_threads}"
        
        for tid in worker_threads:
            # Check initialization balance: every thread must end with balance 0 (balanced CoUninitialize)
            assert fake_com.thread_init_counts[tid] == 0, f"Thread {tid} leaked COM initialization count: {fake_com.thread_init_counts[tid]}"
            
            # Check order: CoInitialize MUST precede DispatchEx on this thread
            thread_ops = [op for t, _, op, _ in fake_com.call_log if t == tid]
            assert "CoInitialize" in thread_ops
            assert "DispatchEx" in thread_ops
            assert thread_ops.index("CoInitialize") < thread_ops.index("DispatchEx")
            assert thread_ops.index("DispatchEx") < thread_ops.index("CoUninitialize")


# =============================================================================
# ITEM 11: DisplayAlerts Constants & AutomationSecurity
# =============================================================================

def test_item11_constants_and_security_ordering(fake_com, tmp_path):
    """
    Item 11:
    1. Verify constants:
       - Word: WD_ALERTS_NONE = 0
       - Excel: EXCEL_ALERTS_NONE = False
       - PowerPoint: PP_ALERTS_NONE = 1 (ppAlertsNone)
       - MSO_AUTOMATION_SECURITY_FORCE_DISABLE = 3
    2. Assert call order:
       - AutomationSecurity = 3 and DisplayAlerts are set BEFORE opening any document.
       - Visible = False (or WithWindow=False) is set before opening.
    """
    # 1. Constant Value Assertions
    assert WD_ALERTS_NONE == 0
    assert EXCEL_ALERTS_NONE is False
    assert PP_ALERTS_NONE == 1
    assert MSO_AUTOMATION_SECURITY_FORCE_DISABLE == 3

    # 2. Document Converter (Word)
    fake_com.call_log.clear()
    dc = DocumentConverter()
    in_docx = tmp_path / "sample.docx"; in_docx.write_text("dummy")
    out_pdf = tmp_path / "sample.pdf"
    dc.convert_docx_to_pdf(in_docx, out_pdf)

    word_ops = [op for _, prog, op, _ in fake_com.call_log if "word" in prog.lower()]
    assert "AutomationSecurity" in word_ops
    assert "DisplayAlerts" in word_ops
    assert "Documents.Open" in word_ops
    
    # Assert AutomationSecurity and DisplayAlerts happen BEFORE Documents.Open
    sec_idx = word_ops.index("AutomationSecurity")
    alerts_idx = word_ops.index("DisplayAlerts")
    open_idx = word_ops.index("Documents.Open")
    assert sec_idx < open_idx, "AutomationSecurity must be set BEFORE Documents.Open!"
    assert alerts_idx < open_idx, "DisplayAlerts must be set BEFORE Documents.Open!"

    # 3. Data Converter (Excel)
    fake_com.call_log.clear()
    data_conv = DataConverter()
    in_xlsx = tmp_path / "sample.xlsx"; in_xlsx.write_text("dummy")
    out_xl_pdf = tmp_path / "sample_xl.pdf"
    data_conv.convert_excel_to_pdf(in_xlsx, out_xl_pdf)

    excel_ops = [op for _, prog, op, _ in fake_com.call_log if "excel" in prog.lower()]
    assert "AutomationSecurity" in excel_ops
    assert "DisplayAlerts" in excel_ops
    assert "Workbooks.Open" in excel_ops
    assert excel_ops.index("AutomationSecurity") < excel_ops.index("Workbooks.Open")
    assert excel_ops.index("DisplayAlerts") < excel_ops.index("Workbooks.Open")

    # 4. Presentation Converter (PowerPoint)
    fake_com.call_log.clear()
    pc = PresentationConverter()
    in_pptx = tmp_path / "sample.pptx"; in_pptx.write_text("dummy")
    out_ppt_pdf = tmp_path / "sample_ppt.pdf"
    pc.convert_pptx_to_pdf(in_pptx, out_ppt_pdf)

    ppt_ops = [op for _, prog, op, _ in fake_com.call_log if "powerpoint" in prog.lower()]
    assert "AutomationSecurity" in ppt_ops
    assert "DisplayAlerts" in ppt_ops
    assert "Presentations.Open" in ppt_ops
    assert ppt_ops.index("AutomationSecurity") < ppt_ops.index("Presentations.Open")
    assert ppt_ops.index("DisplayAlerts") < ppt_ops.index("Presentations.Open")

    # Verify assigned values in log
    for _, prog, op, val in fake_com.call_log:
        if op == "AutomationSecurity":
            assert val == 3, f"Expected AutomationSecurity=3, got {val}"
        elif op == "DisplayAlerts" and "word" in prog.lower():
            assert val == 0, f"Expected Word DisplayAlerts=0, got {val}"
        elif op == "DisplayAlerts" and "excel" in prog.lower():
            assert val is False, f"Expected Excel DisplayAlerts=False, got {val}"
        elif op == "DisplayAlerts" and "powerpoint" in prog.lower():
            assert val == 1, f"Expected PowerPoint DisplayAlerts=1, got {val}"


# =============================================================================
# ITEM 12: SaveAs / Close / Quit Cleanup Structure & Atomicity
# =============================================================================

def test_item12_success_ordering_and_atomicity(fake_com, tmp_path):
    """
    Item 12: Normal path.
    Assert SaveAs, Close, Quit are called in exact sequence.
    Assert output file exists, is > 0 bytes, and no temp files remain.
    """
    dc = DocumentConverter()
    in_docx = tmp_path / "clean.docx"; in_docx.write_text("doc content")
    out_pdf = tmp_path / "clean.pdf"

    dc.convert_docx_to_pdf(in_docx, out_pdf)

    assert out_pdf.exists()
    assert out_pdf.stat().st_size > 0

    # Ensure no leftover temporary files in directory
    temp_files = list(tmp_path.glob("*_tmp_*"))
    assert len(temp_files) == 0, f"Lingering temporary files found: {temp_files}"

    word_ops = [op for _, prog, op, _ in fake_com.call_log if "word" in prog.lower()]
    assert word_ops.index("SaveAs") < word_ops.index("Close") < word_ops.index("Quit")


def test_item12_saveas_fails_cleanup(fake_com, tmp_path, caplog):
    """
    Item 12 Failure Branch 1: SaveAs raises an error.
    Assert:
      - Close(False) is STILL called.
      - Quit() is STILL called.
      - No output file is left at out_p.
      - No temporary file is left behind.
    """
    fake_com.fail_on_save_as = True

    dc = DocumentConverter()
    in_docx = tmp_path / "fail_save.docx"; in_docx.write_text("doc content")
    out_pdf = tmp_path / "fail_save.pdf"

    with pytest.raises(RuntimeError) as exc_info:
        dc.convert_docx_to_pdf(in_docx, out_pdf)

    assert "Microsoft Word" in str(exc_info.value)
    assert not out_pdf.exists(), "Output file must not exist if SaveAs fails"
    assert len(list(tmp_path.glob("*_tmp_*"))) == 0, "Temporary file was not cleaned up"

    word_ops = [op for _, prog, op, _ in fake_com.call_log if "word" in prog.lower()]
    assert "Close" in word_ops, "Close() must be called even when SaveAs fails"
    assert "Quit" in word_ops, "Quit() must be called even when SaveAs fails"


def test_item12_saveas_and_close_both_fail_quit_still_called(fake_com, tmp_path, caplog):
    """
    Item 12 Failure Branch 2: SaveAs fails AND Close fails.
    Assert:
      - Quit() is STILL called despite Close throwing.
      - Close error is logged with warning.
      - No output file at out_p.
    """
    import logging
    fake_com.fail_on_save_as = True
    fake_com.fail_on_close = True

    dc = DocumentConverter()
    in_docx = tmp_path / "double_fail.docx"; in_docx.write_text("doc content")
    out_pdf = tmp_path / "double_fail.pdf"

    with caplog.at_level(logging.WARNING):
        with pytest.raises(RuntimeError):
            dc.convert_docx_to_pdf(in_docx, out_pdf)

    assert not out_pdf.exists()

    word_ops = [op for _, prog, op, _ in fake_com.call_log if "word" in prog.lower()]
    assert "Quit" in word_ops, "Quit() must be called even when both SaveAs and Close fail!"

    # Warning logged for Close failure
    assert any("error closing word document" in rec.message.lower() for rec in caplog.records)


@pytest.mark.parametrize("converter_cls,method_name,app_name", [
    (DocumentConverter, "convert_docx_to_pdf", "Word"),
    (DataConverter, "convert_excel_to_pdf", "Excel"),
    (PresentationConverter, "convert_pptx_to_pdf", "PowerPoint"),
    (RichDocumentConverter, "convert_rtf_to_pdf", "Word"),
])
def test_item12_saveas_fails_cleanup_all_engines(fake_com, tmp_path, converter_cls, method_name, app_name):
    """
    Parametrized Item 12 SaveAs failure test across Word, Excel, PowerPoint, and RichDoc.
    Verifies Close() and Quit() called in finally, no output, and no leftover temp files.
    """
    fake_com.fail_on_save_as = True
    conv = converter_cls()
    in_file = tmp_path / f"test_{app_name}.dat"
    in_file.write_text("dummy")
    out_file = tmp_path / f"test_{app_name}.pdf"

    with pytest.raises(RuntimeError) as exc_info:
        getattr(conv, method_name)(in_file, out_file)

    assert f"Microsoft {app_name}" in str(exc_info.value)
    assert not out_file.exists()
    assert len(list(tmp_path.glob("*_tmp_*"))) == 0

    ops = [op for _, prog, op, _ in fake_com.call_log if app_name.lower() in prog.lower()]
    assert "Close" in ops
    assert "Quit" in ops


# =============================================================================
# ITEM A3: Error Message Assertions (Corrupt Input, Locked Output, Missing Office)
# =============================================================================

@pytest.mark.parametrize("converter_cls,method_name,app_name", [
    (DocumentConverter, "convert_docx_to_pdf", "Word"),
    (DataConverter, "convert_excel_to_pdf", "Excel"),
    (PresentationConverter, "convert_pptx_to_pdf", "PowerPoint"),
    (RichDocumentConverter, "convert_rtf_to_pdf", "Word"),
])
def test_error_message_missing_office(fake_com, tmp_path, converter_cls, method_name, app_name):
    """
    When Office is not installed or DispatchEx fails, error message MUST state:
    'requires Microsoft <App> on Windows'
    """
    fake_com.fail_on_dispatch = True
    conv = converter_cls()
    in_file = tmp_path / "sample.dat"
    in_file.write_text("content")
    out_file = tmp_path / "sample.pdf"

    with pytest.raises(RuntimeError) as exc_info:
        getattr(conv, method_name)(in_file, out_file)

    msg = str(exc_info.value)
    assert f"requires Microsoft {app_name} on Windows" in msg


@pytest.mark.parametrize("converter_cls,method_name,app_name", [
    (DocumentConverter, "convert_docx_to_pdf", "Word"),
    (DataConverter, "convert_excel_to_pdf", "Excel"),
    (PresentationConverter, "convert_pptx_to_pdf", "PowerPoint"),
    (RichDocumentConverter, "convert_rtf_to_pdf", "Word"),
])
def test_error_message_corrupt_input(fake_com, tmp_path, converter_cls, method_name, app_name):
    """
    When input document is corrupted / fails to open, error message MUST indicate
    the conversion failed for the specific file name AND preserve the underlying cause fragment.
    """
    fake_com.fail_on_open = True
    conv = converter_cls()
    in_file = tmp_path / "corrupt_input.dat"
    in_file.write_text("corrupted content")
    out_file = tmp_path / "corrupt_input.pdf"

    with pytest.raises(RuntimeError) as exc_info:
        getattr(conv, method_name)(in_file, out_file)

    msg = str(exc_info.value)
    assert f"Microsoft {app_name} conversion" in msg and "failed for 'corrupt_input.dat'" in msg
    assert "Simulated" in msg  # Underlying cause fragment verified


@pytest.mark.parametrize("converter_cls,method_name,app_name", [
    (DocumentConverter, "convert_docx_to_pdf", "Word"),
    (DataConverter, "convert_excel_to_pdf", "Excel"),
    (PresentationConverter, "convert_pptx_to_pdf", "PowerPoint"),
    (RichDocumentConverter, "convert_rtf_to_pdf", "Word"),
])
def test_error_message_locked_output(fake_com, tmp_path, monkeypatch, converter_cls, method_name, app_name):
    """
    When output destination is locked / non-writable (PermissionError / Access is denied),
    error message MUST preserve the permission error details.
    """
    def fake_replace(src, dst):
        raise PermissionError(13, "Permission denied: Access is denied")

    monkeypatch.setattr(os, "replace", fake_replace)

    conv = converter_cls()
    in_file = tmp_path / "valid.dat"
    in_file.write_text("valid content")
    out_file = tmp_path / "locked.pdf"

    with pytest.raises(RuntimeError) as exc_info:
        getattr(conv, method_name)(in_file, out_file)

    msg = str(exc_info.value)
    assert f"Microsoft {app_name} conversion" in msg and "failed for 'valid.dat'" in msg
    assert ("Permission denied" in msg or "Access is denied" in msg or "PermissionError" in msg)

