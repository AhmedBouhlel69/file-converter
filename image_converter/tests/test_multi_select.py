"""
Test multi-file selection in QueueTableWidget and MainWindow.
"""

from pathlib import Path
import pytest
from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtWidgets import QApplication

from image_converter.ui.components import QueueTableWidget
from image_converter.ui.main_window import ImageConverterMainWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_queue_table_multi_selection(qapp, tmp_path: Path):
    table = QueueTableWidget()
    f1 = tmp_path / "file1.png"
    f2 = tmp_path / "file2.jpg"
    f3 = tmp_path / "file3.pdf"

    f1.write_bytes(b"dummy1")
    f2.write_bytes(b"dummy2")
    f3.write_bytes(b"dummy3")

    table.add_file_item(f1, "PNG")
    table.add_file_item(f2, "JPG")
    table.add_file_item(f3, "PDF")

    assert table.rowCount() == 3

    # Select row 0 and row 2 (multi-selection)
    sel_model = table.selectionModel()
    idx0 = table.model().index(0, 0)
    idx2 = table.model().index(2, 0)

    sel_model.select(idx0, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
    sel_model.select(idx2, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)

    selected_rows = table.get_selected_rows()
    assert selected_rows == [0, 2]

    selected_paths = table.get_selected_file_paths()
    assert selected_paths == [f1, f3]

    # Test removing selected rows
    removed = table.remove_selected_rows()
    assert removed == [2, 0] or removed == [0, 2]
    assert table.rowCount() == 1
    assert table.file_paths == [f2]


def test_main_window_multi_selection_helpers(qapp, tmp_path: Path):
    win = ImageConverterMainWindow()
    f1 = tmp_path / "file1.png"
    f2 = tmp_path / "file2.jpg"
    f3 = tmp_path / "file3.pdf"

    f1.write_bytes(b"dummy1")
    f2.write_bytes(b"dummy2")
    f3.write_bytes(b"dummy3")

    win.add_images([f1, f2, f3])
    assert win.queue_table.rowCount() == 3

    # Select f2 and f3
    table = win.queue_table
    table.clearSelection()
    sel_model = table.selectionModel()
    idx1 = table.model().index(1, 0)
    idx2 = table.model().index(2, 0)

    sel_model.select(idx1, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
    sel_model.select(idx2, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)

    assert win._get_selected_or_all_paths() == [f2, f3]
    assert win._get_selected_pdf_path() == f3

    # Remove selected (f2 and f3)
    win._remove_selected()
    assert win.queue_table.rowCount() == 1
    assert win.queue_table.file_paths == [f1]
    win.close()
