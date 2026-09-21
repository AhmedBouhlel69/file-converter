import os
from pathlib import Path
import pytest
import fitz
from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog

os.environ["QT_QPA_PLATFORM"] = "offscreen"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_merge_dialog_surfaces_error_and_preserves_output(qapp, tmp_path: Path, monkeypatch):
    from image_converter.ui.tool_dialogs import MergeDialog

    # Create one valid PDF and one unsupported text file
    pdf_path = tmp_path / "valid.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((50, 50), "Sample Page")
    doc.save(str(pdf_path))
    doc.close()

    bad_file = tmp_path / "notes.txt"
    bad_file.write_text("unsupported format", encoding="utf-8")

    out_pdf = tmp_path / "merged_out.pdf"

    critical_messages = []
    warning_messages = []
    monkeypatch.setattr(QMessageBox, "critical", lambda parent, title, text, *args, **kwargs: critical_messages.append((title, text)))
    monkeypatch.setattr(QMessageBox, "warning", lambda parent, title, text, *args, **kwargs: warning_messages.append((title, text)))
    monkeypatch.setattr(QMessageBox, "information", lambda parent, title, text, *args, **kwargs: QMessageBox.StandardButton.Ok)

    dlg = MergeDialog(initial_files=[pdf_path, bad_file])
    dlg.txt_output.setText(str(out_pdf))

    # Trigger merge action
    dlg._execute_merge()

    assert len(critical_messages) == 1, "Expected exactly one critical error message dialog"
    title, text = critical_messages[0]
    assert title == "Merge Failed"
    assert "Unsupported file format for merge" in text
    assert "notes.txt" in text
    assert not out_pdf.exists(), "Output PDF must not be created on error"


def test_split_dialog_surfaces_error_and_preserves_output(qapp, tmp_path: Path, monkeypatch):
    from image_converter.ui.tool_dialogs import SplitDialog

    pdf_path = tmp_path / "sample_split.pdf"
    doc = fitz.open()
    for _ in range(3):
        doc.new_page().insert_text((50, 50), "Page")
    doc.save(str(pdf_path))
    doc.close()

    out_dir = tmp_path / "split_output"
    out_dir.mkdir()

    critical_messages = []
    warning_messages = []
    monkeypatch.setattr(QMessageBox, "critical", lambda parent, title, text, *args, **kwargs: critical_messages.append((title, text)))
    monkeypatch.setattr(QMessageBox, "warning", lambda parent, title, text, *args, **kwargs: warning_messages.append((title, text)))
    monkeypatch.setattr(QMessageBox, "information", lambda parent, title, text, *args, **kwargs: QMessageBox.StandardButton.Ok)

    dlg = SplitDialog(initial_file=pdf_path)
    dlg.txt_output_dir.setText(str(out_dir))
    dlg.rb_ranges.setChecked(True)
    dlg.txt_ranges.setText("1-99")  # Exceeds total pages (3)

    dlg._execute_split()

    assert len(critical_messages) == 1
    title, text = critical_messages[0]
    assert title == "Split Failed"
    assert "exceeds total pages" in text
    assert len(list(out_dir.iterdir())) == 0, "Output directory must remain empty on error"


def test_organize_dialog_surfaces_error_and_preserves_output(qapp, tmp_path: Path, monkeypatch):
    from image_converter.ui.tool_dialogs import OrganizePagesDialog

    pdf_path = tmp_path / "sample_org.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((50, 50), "Page 1")
    doc.save(str(pdf_path))
    doc.close()

    out_pdf = tmp_path / "organized_out.pdf"

    critical_messages = []
    warning_messages = []
    monkeypatch.setattr(QMessageBox, "critical", lambda parent, title, text, *args, **kwargs: critical_messages.append((title, text)))
    monkeypatch.setattr(QMessageBox, "warning", lambda parent, title, text, *args, **kwargs: warning_messages.append((title, text)))
    monkeypatch.setattr(QMessageBox, "information", lambda parent, title, text, *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(out_pdf), "PDF"))

    dlg = OrganizePagesDialog(initial_file=pdf_path)
    # Set page index out of range so organize_pages throws Item 2 / ValueError naming index
    dlg.pages = [{"src_page": 999, "rotation": 0}]

    dlg._save_pdf()

    assert len(critical_messages) == 1
    title, text = critical_messages[0]
    assert title == "Save Failed"
    assert "Invalid page index 999" in text
    assert not out_pdf.exists(), "Output file must not be created on error"


def test_organize_dialog_mixed_indices_surfaces_specific_error(qapp, tmp_path: Path, monkeypatch):
    from image_converter.ui.tool_dialogs import OrganizePagesDialog

    pdf_path = tmp_path / "multi.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((50, 50), "P1")
    doc.new_page().insert_text((50, 50), "P2")
    doc.save(str(pdf_path))
    doc.close()

    out_pdf = tmp_path / "out.pdf"

    critical_messages = []
    warning_messages = []
    monkeypatch.setattr(QMessageBox, "critical", lambda parent, title, text, *args, **kwargs: critical_messages.append((title, text)))
    monkeypatch.setattr(QMessageBox, "warning", lambda parent, title, text, *args, **kwargs: warning_messages.append((title, text)))
    monkeypatch.setattr(QMessageBox, "information", lambda parent, title, text, *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(out_pdf), "PDF"))

    dlg = OrganizePagesDialog(initial_file=pdf_path)
    # Mixed valid (0) and invalid (999)
    dlg.pages = [{"src_page": 0, "rotation": 0}, {"src_page": 999, "rotation": 0}]

    dlg._save_pdf()

    assert len(critical_messages) == 1
    title, text = critical_messages[0]
    assert title == "Save Failed"
    assert "Invalid page index 999 at position 1" in text
    assert not out_pdf.exists()


def test_compress_dialog_surfaces_error_on_corrupt_file(qapp, tmp_path: Path, monkeypatch):
    from image_converter.ui.tool_dialogs import CompressDialog

    corrupt_pdf = tmp_path / "corrupt.pdf"
    corrupt_pdf.write_bytes(b"not a valid pdf header")

    out_pdf = tmp_path / "compressed_out.pdf"

    critical_messages = []
    warning_messages = []
    monkeypatch.setattr(QMessageBox, "critical", lambda parent, title, text, *args, **kwargs: critical_messages.append((title, text)))
    monkeypatch.setattr(QMessageBox, "warning", lambda parent, title, text, *args, **kwargs: warning_messages.append((title, text)))
    monkeypatch.setattr(QMessageBox, "information", lambda parent, title, text, *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(out_pdf), "PDF"))

    dlg = CompressDialog(initial_file=corrupt_pdf)
    dlg._execute_compress()

    assert len(critical_messages) == 1
    title, text = critical_messages[0]
    assert title == "Compression Failed"
    assert "not a valid PDF" in text or "missing %PDF-" in text
    assert not out_pdf.exists(), "Output file must not exist on failure"


def test_compress_dialog_already_optimal_reports_no_reduction(qapp, tmp_path: Path, monkeypatch):
    from image_converter.ui.tool_dialogs import CompressDialog

    from image_converter.core.pdf_tools import compress_pdf

    # Create a small clean PDF and optimize it once so it is already optimal
    raw_pdf = tmp_path / "raw.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((50, 50), "Optimal minimal PDF text")
    doc.save(str(raw_pdf))
    doc.close()

    opt_pdf = tmp_path / "already_optimal.pdf"
    compress_pdf(raw_pdf, opt_pdf, level="medium")

    out_pdf = tmp_path / "comp_out.pdf"

    info_messages = []
    crit_messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda parent, title, text, *args, **kwargs: info_messages.append((title, text)) or QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "critical", lambda parent, title, text, *args, **kwargs: crit_messages.append((title, text)))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(out_pdf), "PDF"))

    dlg = CompressDialog(initial_file=opt_pdf)
    dlg._execute_compress()

    assert len(crit_messages) == 0, "Should not fail with critical error"
    assert len(info_messages) == 1, "Expected exactly one information dialog"
    title, text = info_messages[0]
    assert title == "No Reduction Achieved"
    assert "No reduction was achieved" in text
    assert "Original file preserved" in text
    assert "ℹ️ No reduction was achieved" in dlg.lbl_result.text()
