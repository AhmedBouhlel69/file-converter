"""Truthful metadata states and measured results without changing engine behavior."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import fitz
from PIL import Image
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QAbstractButton, QLabel, QMessageBox

from image_converter.core.engine import ConversionConfig, ConversionResult
from image_converter.ui import metadata_evidence
from image_converter.ui.components import ConversionSettingsWidget, ImagePreviewWidget
from image_converter.ui.image_tools_page import ImageToolsPage
from image_converter.ui.main_window import ImageConverterMainWindow
from image_converter.ui.metadata_evidence import MetadataEvidence, inspect_metadata, metadata_check_summary
from image_converter.ui.pdf_tools_page import PdfToolsPage
from image_converter.ui.tool_dialogs import CompressDialog, ImageCompressDialog
from image_converter.ui.worker import BatchConversionWorker


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def photo(path: Path, *, with_metadata: bool = False) -> Path:
    exif = Image.Exif()
    if with_metadata:
        exif[315] = "Private author"
    Image.new("RGB", (20, 15), "red").save(path, exif=exif)
    return path


def test_real_supported_metadata_is_distinct_from_no_supported_fields(tmp_path):
    original = photo(tmp_path / "original.jpg", with_metadata=True)
    empty = photo(tmp_path / "empty.jpg")
    assert inspect_metadata(original).status == "found"
    assert "Artist" in inspect_metadata(original).fields
    assert inspect_metadata(empty).summary == "No supported metadata found"
    assert "clean" not in inspect_metadata(empty).summary.lower()


@pytest.mark.parametrize("extension", [".txt", ".csv", ".gif", ".ico", ".xls"])
def test_unsupported_inspection_never_reports_clean(extension, tmp_path):
    path = tmp_path / f"uninspected{extension}"
    path.write_bytes(b"not a supported metadata route")
    evidence = inspect_metadata(path)
    assert evidence.status == "unavailable"
    assert evidence.summary == "Metadata inspection unavailable"


@pytest.mark.parametrize("extension,flag", [(".docx", "_DOCX_AVAILABLE"), (".pptx", "_PPTX_AVAILABLE"), (".xlsx", "_OPENPYXL_AVAILABLE")])
def test_missing_reader_is_unknown_not_no_metadata(extension, flag, tmp_path, monkeypatch):
    monkeypatch.setattr(metadata_evidence.metadata_engine, flag, False)
    path = tmp_path / f"missing-reader{extension}"
    path.write_bytes(b"placeholder")
    assert inspect_metadata(path).status == "unavailable"


def test_internal_inspection_failure_is_not_clean(tmp_path, monkeypatch):
    path = photo(tmp_path / "image.jpg")
    monkeypatch.setattr(metadata_evidence.metadata_engine, "get_detailed_metadata", lambda *_args, **_kwargs: {
        "has_metadata": False, "fields": {}, "warnings": ["Image metadata inspection failed: unavailable reader"],
    })
    evidence = inspect_metadata(path)
    assert evidence.status == "failed"
    assert "unavailable reader" in evidence.detail


def test_informational_gps_warning_still_reports_found_fields(tmp_path, monkeypatch):
    path = photo(tmp_path / "gps.jpg")
    monkeypatch.setattr(metadata_evidence.metadata_engine, "get_detailed_metadata", lambda *_args, **_kwargs: {
        "has_metadata": True, "fields": {"GPSInfo": "coordinates"}, "warnings": ["Contains embedded GPS location data"],
    })
    evidence = inspect_metadata(path)
    assert evidence.status == "found"
    assert evidence.summary == "1 supported metadata field found"


def test_exception_is_failed_evidence(tmp_path, monkeypatch):
    path = photo(tmp_path / "image.jpg")

    def fail(*_args, **_kwargs):
        raise OSError("Reader failed")

    monkeypatch.setattr(metadata_evidence.metadata_engine, "get_detailed_metadata", fail)
    assert inspect_metadata(path).status == "failed"
    assert "Reader failed" in inspect_metadata(path).detail


def test_encrypted_pdf_requires_valid_password_for_evidence(tmp_path):
    path = tmp_path / "encrypted.pdf"
    with fitz.open() as document:
        document.new_page()
        document.save(path, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="secret")
    assert inspect_metadata(path).status == "unavailable"
    assert inspect_metadata(path, password="incorrect").status == "unavailable"
    assert inspect_metadata(path, password="secret").status == "not_found"


def test_malformed_odt_metadata_is_failed_not_absent(tmp_path):
    path = tmp_path / "malformed.odt"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("meta.xml", "<broken><metadata>")
    assert inspect_metadata(path).status == "failed"
    assert "no element found" in inspect_metadata(path).detail


def test_corrupt_exif_warning_is_failed_not_absent(tmp_path):
    path = tmp_path / "corrupt-exif.jpg"
    # TIFF header declares an IFD entry but omits its twelve-byte body.
    Image.new("RGB", (20, 15), "red").save(path, exif=b"Exif\x00\x00II*\x00\x08\x00\x00\x00\x01\x00")
    evidence = inspect_metadata(path)
    assert evidence.status == "failed"
    assert "Corrupt EXIF" in evidence.detail


def test_odt_preflight_matches_reader_utf8_decoding(tmp_path):
    path = tmp_path / "utf16.odt"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("meta.xml", '<?xml version="1.0" encoding="UTF-16"?><metadata><author>Private author</author></metadata>'.encode("utf-16"))
    assert inspect_metadata(path).status == "failed"


def test_concurrent_clean_and_corrupt_checks_keep_warning_states_separate(tmp_path):
    clean = photo(tmp_path / "clean.jpg")
    corrupt = tmp_path / "corrupt.jpg"
    Image.new("RGB", (20, 15), "red").save(corrupt, exif=b"Exif\x00\x00II*\x00\x08\x00\x00\x00\x01\x00")
    paths = [clean, corrupt] * 4
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(inspect_metadata, paths))
    assert [item.status for item in results] == ["not_found", "failed"] * 4


def test_inspector_exposes_unknown_and_selectable_output_evidence(qapp, tmp_path):
    text = tmp_path / "notes.txt"
    text.write_text("hello")
    preview = ImagePreviewWidget()
    preview.set_image(text)
    assert preview.lbl_meta_privacy.text() == "Metadata inspection unavailable"
    assert preview.lbl_meta_privacy.property("state") != "success"
    output = tmp_path / "output.jpg"
    evidence = MetadataEvidence("found", ("Artist",), "Supported field remains")
    preview.set_output_evidence(output, evidence)
    assert "Artist" in preview.lbl_output_metadata.text()
    assert str(output) in preview.lbl_output_metadata.text()
    assert preview.lbl_output_metadata.accessibleName() == "Output metadata check"
    assert preview.lbl_output_metadata.focusPolicy() == Qt.FocusPolicy.StrongFocus
    assert preview.lbl_output_metadata.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByKeyboard
    assert "QLabel:focus" in preview.lbl_output_metadata.styleSheet()
    preview.clear_preview()
    assert preview.lbl_output_metadata.isHidden()
    preview.close()


def test_settings_describe_the_routes_that_actually_receive_flags(qapp):
    settings = ConversionSettingsWidget()
    assert settings.chk_strip_metadata.text() == "Remove supported metadata"
    assert "where the format and conversion route allow" in settings.chk_strip_metadata.toolTip()
    assert "PDF to TXT or DOCX" in settings.chk_enable_ocr.toolTip()
    assert "Image to TXT always uses OCR" in settings.chk_enable_ocr.toolTip()
    assert "image to DOCX embeds the image" in settings.chk_enable_ocr.toolTip()
    assert "Word conversion routes do not use this field" in settings.line_password.toolTip()
    assert "Keep supported EXIF" in settings.chk_preserve_exif.text()
    settings.close()


def test_constructed_pages_do_not_contain_old_guarantees(qapp):
    widgets = [ImageConverterMainWindow(), ImageToolsPage(), PdfToolsPage(), CompressDialog(), ImageCompressDialog()]
    banned = ["never overwritten", "originals were not changed", "no tracking tags", "Strip all metadata", "across all formats", "Drag-friendly", "Non-destructive save", "Original stays untouched", "already optimal", "150 DPI", "100 DPI", "smallest file size", "engine and output behavior stay unchanged"]
    for widget in widgets:
        strings = []
        for child in widget.findChildren(QLabel) + widget.findChildren(QAbstractButton):
            strings += [child.text(), child.toolTip(), child.accessibleDescription()]
        combined = "\n".join(strings)
        for phrase in banned:
            assert phrase not in combined
        widget.close()


def test_footer_describes_current_destination_without_preservation_promise(qapp, tmp_path):
    window = ImageConverterMainWindow()
    assert "same folder as each source" in window.lbl_status_hint.text()
    assert "Existing destination files may be replaced" in window.lbl_status_hint.text()
    window.settings_widget.radio_custom_dir.setChecked(True)
    window.settings_widget.line_out_dir.setText(str(tmp_path))
    window._refresh_queue_ui()
    assert str(tmp_path) in window.lbl_status_hint.text()
    window.close()


def test_worker_retains_completion_api_and_adds_actual_output_evidence(qapp, tmp_path):
    source = photo(tmp_path / "source.jpg", with_metadata=True)
    output = photo(tmp_path / "actual-output.jpg", with_metadata=True)
    config = ConversionConfig(target_format="JPG", strip_metadata=True)
    result = ConversionResult(success=True, input_path=str(source), output_path=str(output), output_size_bytes=output.stat().st_size)
    received = []

    def convert_batch(tasks, progress_callback, cancel_check):
        assert tasks == [(source, output, config)]
        assert not cancel_check()
        progress_callback(1, 1, result)
        return [result]

    worker = BatchConversionWorker([(source, output, config)], SimpleNamespace(convert_batch=convert_batch))
    worker.file_completed.connect(lambda index, item: received.append(("completed", index, item)))
    worker.metadata_inspected.connect(lambda index, item: received.append(("metadata", index, item)))
    worker.run()
    assert received[0] == ("completed", 0, result)
    assert received[1][0:2] == ("metadata", 0)
    assert received[1][2].status == "found"
    assert config.strip_metadata is True


def test_worker_marks_document_image_evidence_partial(qapp, tmp_path):
    source = tmp_path / "pages.pdf"
    output = photo(tmp_path / "pages_1.jpg")
    config = ConversionConfig(target_format="JPG")
    result = ConversionResult(success=True, input_path=str(source), output_path=str(output))

    def convert_batch(_tasks, progress_callback, **_kwargs):
        progress_callback(1, 1, result)
        return [result]

    worker = BatchConversionWorker([(source, output, config)], SimpleNamespace(convert_batch=convert_batch))
    received = []
    worker.metadata_inspected.connect(lambda _index, item: received.append(item))
    worker.run()
    assert received[0].partial
    assert "Only the first output file was checked" in received[0].output_text


def test_completed_row_retains_evidence_and_source_preview(qapp, tmp_path):
    source = photo(tmp_path / "source.jpg")
    output = photo(tmp_path / "output.jpg", with_metadata=True)
    window = ImageConverterMainWindow()
    window.add_images([source])
    window._active_rows = [0]
    result = ConversionResult(success=True, input_path=str(source), output_path=str(output), output_size_bytes=output.stat().st_size, error_message="Existing warning")
    window._on_file_completed(0, result)
    evidence = inspect_metadata(output)
    window._on_metadata_inspected(0, evidence)
    window._on_batch_finished(1, 0, 0.1, source.stat().st_size, output.stat().st_size)
    entry = window.queue_table.queue_model.entry(0)
    assert entry.output_path == output
    assert entry.status == "Warning"
    assert "1 with supported fields" in window.lbl_metadata_result.text()
    window._on_table_row_selected(str(source))
    assert window.preview_widget.current_file_path == source
    assert "Artist" in window.preview_widget.lbl_output_metadata.text()
    assert "originals were not changed" not in window.lbl_status_hint.text()
    window.close()


def test_failed_and_unavailable_checks_do_not_become_success_counts():
    summary = metadata_check_summary([MetadataEvidence("found", ("Author",)), MetadataEvidence("not_found"), MetadataEvidence("failed"), MetadataEvidence("unavailable")])
    assert "1 with no supported fields found" in summary
    assert "1 with supported fields" in summary
    assert "2 unavailable or failed" in summary


def test_rerun_clears_selected_output_evidence_until_new_check(qapp, tmp_path, monkeypatch):
    source = photo(tmp_path / "source.jpg")
    output = photo(tmp_path / "previous-output.jpg")
    window = ImageConverterMainWindow()
    window.add_images([source])
    window._active_rows = [0]
    result = ConversionResult(success=True, input_path=str(source), output_path=str(output), output_size_bytes=output.stat().st_size)
    window._on_file_completed(0, result)
    window._on_metadata_inspected(0, inspect_metadata(output))
    window._on_table_row_selected(str(source))
    assert not window.preview_widget.lbl_output_metadata.isHidden()
    monkeypatch.setattr(BatchConversionWorker, "start", lambda _self: None)
    window.start_conversion()
    entry = window.queue_table.queue_model.entry(0)
    assert entry.output_path is None
    assert entry.metadata_evidence is None
    assert window.preview_widget.lbl_output_metadata.isHidden()
    assert not window.preview_widget.lbl_output_metadata.text()
    window.close()


def test_image_compressor_fallback_is_unchanged_and_reports_retained_metadata(qapp, tmp_path, monkeypatch):
    source = photo(tmp_path / "original.jpg", with_metadata=True)
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda _parent, _title, text, *_args: messages.append(text) or QMessageBox.StandardButton.Ok)
    dialog = ImageCompressDialog(initial_files=[source])
    dialog.combo_format.setCurrentText("JPG")
    dialog.txt_output_dir.setText(str(tmp_path / "outputs"))

    def larger_conversion(input_path, output_path, config):
        assert config.strip_metadata
        Path(output_path).write_bytes(Path(input_path).read_bytes() + b"larger output")
        return ConversionResult(success=True, input_path=str(input_path), output_path=str(output_path))

    monkeypatch.setattr(dialog.engine, "convert_single", larger_conversion)
    dialog._execute_compress()
    destination = tmp_path / "outputs" / "original_compressed.jpg"
    assert destination.read_bytes() == source.read_bytes()
    assert "unchanged copy saved" in messages[0]
    assert "Original metadata and dimensions may remain" in messages[0]
    assert "1 supported metadata field found" in messages[0]
    assert dialog.lbl_result.property("state") == "warning"
    assert dialog.lbl_result.accessibleName() == "Image compression result"
    assert dialog.lbl_result.focusPolicy() == Qt.FocusPolicy.StrongFocus
    assert dialog.lbl_result.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByKeyboard
    assert "QLabel:focus" in dialog.lbl_result.styleSheet()
    assert dialog.btn_compress.nextInFocusChain() == dialog.lbl_result
    dialog.close()


def test_larger_cross_format_output_reports_increase(qapp, tmp_path, monkeypatch):
    source = photo(tmp_path / "tiny.jpg")
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: QMessageBox.StandardButton.Ok)
    dialog = ImageCompressDialog(initial_files=[source])
    dialog.combo_format.setCurrentText("PNG")

    def larger_conversion(input_path, output_path, _config):
        Image.effect_noise((200, 200), 80).convert("RGB").save(output_path)
        return ConversionResult(success=True, input_path=str(input_path), output_path=str(output_path))

    monkeypatch.setattr(dialog.engine, "convert_single", larger_conversion)
    dialog._execute_compress()
    assert "% larger" in dialog.lbl_result.text()
    assert dialog.lbl_result.property("state") == "warning"
    dialog.close()


def test_pdf_profiles_match_actual_engine_parameters(qapp):
    dialog = CompressDialog()
    assert "1200 pixels" in dialog.rb_balanced.toolTip()
    assert "quality 65" in dialog.rb_balanced.toolTip()
    assert "800 pixels" in dialog.rb_max.toolTip()
    assert "quality 40" in dialog.rb_max.toolTip()
    assert "not guaranteed" in dialog.rb_max.toolTip()
    assert "without re-encoding page images" in dialog.rb_lossless.toolTip()
    dialog.close()
