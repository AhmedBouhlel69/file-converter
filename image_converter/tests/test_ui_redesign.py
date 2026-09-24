"""Regression checks for the tokenized model/view redesign."""

from __future__ import annotations

import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton

from image_converter.ui.contrast import assert_theme_contrast
from image_converter.ui.image_tools_page import ImageToolsPage
from image_converter.ui.main_window import ImageConverterMainWindow
from image_converter.ui.pdf_tools_page import PdfToolsPage
from image_converter.ui.queue_model import QueueTableModel


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    return app


def test_theme_contrast_meets_wcag_thresholds():
    ratios = assert_theme_contrast()
    assert ratios["secondary on raised surface"] >= 4.5
    assert ratios["focus ring on first surface"] >= 3.0


def test_queue_model_is_five_columns_and_handles_mixed_defaults(qapp, tmp_path: Path):
    image_path = tmp_path / "sample.png"
    Image.new("RGB", (32, 24), "#6654E8").save(image_path)
    text_path = tmp_path / "notes.txt"
    text_path.write_text("sample document", encoding="utf-8")

    model = QueueTableModel()
    model.add_paths([image_path, text_path])
    assert model.columnCount() == 5
    assert model.rowCount() == 2

    model.set_default_format("PER_FILE")
    assert all(not entry.overridden for entry in model.entries)
    assert all(entry.default_format == entry.target_format for entry in model.entries)


def test_main_window_switches_empty_queue_and_inspector_states(qapp, tmp_path: Path):
    window = ImageConverterMainWindow()
    assert window.queue_state_stack.currentIndex() == 0
    assert not window.btn_convert_all.isEnabled()

    image_path = tmp_path / "selected.png"
    Image.new("RGB", (64, 48), "#67DFFF").save(image_path)
    window.add_images([image_path])
    qapp.processEvents()
    assert window.queue_state_stack.currentIndex() == 1
    assert window.queue_table.columnCount() == 5
    assert window.btn_convert_all.isEnabled()

    window.queue_table.selectRow(0)
    qapp.processEvents()
    assert window.inspector_stack.currentIndex() == 1
    window._show_batch_settings()
    assert window.inspector_stack.currentIndex() == 0
    window.close()


def test_main_window_mode_buttons_show_matching_pages(qapp):
    window = ImageConverterMainWindow()

    window._set_app_mode(0)
    assert window.app_stack.currentWidget() is window.convert_page
    assert window.btn_mode_convert.isChecked()

    window._set_app_mode(1)
    assert window.app_stack.currentWidget() is window.image_tools_page
    assert window.btn_mode_images.isChecked()

    window._set_app_mode(2)
    assert window.app_stack.currentWidget() is window.pdf_tools_page
    assert window.btn_mode_pdf.isChecked()

    window.close()


def test_pdf_tool_view_has_one_primary_action(qapp):
    page = PdfToolsPage()
    for index in range(page.stack.count()):
        page.set_active_tool(index)
        primary_actions = [
            button
            for button in page.stack.currentWidget().findChildren(QPushButton)
            if button.property("variant") == "primary" and button.isVisibleTo(page.stack.currentWidget())
        ]
        assert len(primary_actions) == 1


def test_image_tool_view_has_one_primary_action(qapp):
    page = ImageToolsPage()
    primary_actions = [
        button
        for button in page.findChildren(QPushButton)
        if button.property("variant") == "primary" and button.isVisibleTo(page)
    ]
    assert len(primary_actions) == 1


def test_ui_conversion_runs_existing_engine_end_to_end(qapp, tmp_path: Path):
    source = tmp_path / "convert-me.png"
    destination = tmp_path / "convert-me.jpg"
    Image.new("RGB", (96, 64), "#6654E8").save(source)

    window = ImageConverterMainWindow()
    assert window.app_stack.count() == 3
    window.add_images([source])
    window.queue_table.set_target_format_for_row(0, "JPG")
    window.start_conversion()

    deadline = time.monotonic() + 10
    while window._is_converting and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)

    assert not window._is_converting
    assert destination.exists()
    assert window.queue_table.queue_model.entry(0).status == "Done"
    assert window._footer_state == "completed"
    window.close()
