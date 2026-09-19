"""
Clean, modal dialogs for local PDF tools:
- MergeDialog
- SplitDialog
- OrganizePagesDialog
- CompressDialog

100% offline, local operations with instant feedback.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional

import fitz  # PyMuPDF
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from image_converter.core.pdf_tools import (
    compress_pdf,
    merge_pdfs,
    organize_pages,
    split_pdf,
)
from image_converter.ui.components import format_bytes


def fitz_page_to_qpixmap(page: fitz.Page, dpi: int = 72) -> QPixmap:
    """Render a fitz page to QPixmap."""
    pix = page.get_pixmap(dpi=dpi)
    if pix.alpha:
        qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGBA8888)
    else:
        qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimg)


# ===========================================================================
# 1. MERGE DIALOG
# ===========================================================================

class MergeDialog(QDialog):
    """Clean dialog to reorder and merge multiple PDFs and images into one PDF."""

    def __init__(self, initial_files: Optional[List[Path]] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Merge Files to PDF")
        self.resize(650, 520)
        self.setMinimumSize(500, 400)

        self.files: List[Path] = []
        self._init_ui()

        if initial_files:
            self.add_files(initial_files)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        # Header
        header = QLabel("Merge Files into a Single PDF")
        header.setStyleSheet("font-size: 16px; font-weight: 700; color: #f8fafc;")
        sub = QLabel("Reorder PDFs and images to combine them into one document. 100% local.")
        sub.setStyleSheet("font-size: 12px; color: #94a3b8;")
        layout.addWidget(header)
        layout.addWidget(sub)

        # File List Table
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["File", "Type", "Size"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setStyleSheet(
            "QTableWidget { background-color: #1a1d26; border: 1px solid #282c38; border-radius: 8px; color: #f3f4f6; gridline-color: #242938; }"
            "QTableWidget::item:selected { background-color: #3b4256; color: #ffffff; }"
            "QHeaderView::section { background-color: #12141c; color: #94a3b8; padding: 6px; border: none; font-weight: 600; }"
        )
        layout.addWidget(self.table, stretch=1)

        # Control buttons under table
        ctrl_bar = QHBoxLayout()
        ctrl_bar.setSpacing(8)

        self.btn_add = QPushButton("➕ Add Files...")
        self.btn_add.setObjectName("SecondaryButton")
        self.btn_add.clicked.connect(self._on_add_files)

        self.btn_up = QPushButton("▲ Move Up")
        self.btn_up.setObjectName("SecondaryButton")
        self.btn_up.clicked.connect(self._move_up)

        self.btn_down = QPushButton("▼ Move Down")
        self.btn_down.setObjectName("SecondaryButton")
        self.btn_down.clicked.connect(self._move_down)

        self.btn_remove = QPushButton("🗑️ Remove")
        self.btn_remove.setObjectName("SecondaryButton")
        self.btn_remove.clicked.connect(self._remove_selected)

        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setObjectName("DangerButton")
        self.btn_clear.clicked.connect(self._clear_all)

        ctrl_bar.addWidget(self.btn_add)
        ctrl_bar.addWidget(self.btn_up)
        ctrl_bar.addWidget(self.btn_down)
        ctrl_bar.addWidget(self.btn_remove)
        ctrl_bar.addStretch()
        ctrl_bar.addWidget(self.btn_clear)
        layout.addLayout(ctrl_bar)

        # Options
        opt_frame = QFrame()
        opt_frame.setStyleSheet("background-color: #12141c; border-radius: 8px; padding: 10px;")
        opt_layout = QVBoxLayout(opt_frame)
        opt_layout.setContentsMargins(10, 8, 10, 8)
        opt_layout.setSpacing(8)

        out_row = QHBoxLayout()
        out_lbl = QLabel("Output PDF:")
        out_lbl.setStyleSheet("color: #cbd5e1; font-weight: 600;")
        self.txt_output = QLineEdit()
        self.txt_output.setPlaceholderText("Select destination file...")
        self.txt_output.setStyleSheet("background-color: #1a1d26; color: #f3f4f6; border: 1px solid #363b4d; border-radius: 6px; padding: 6px;")
        btn_browse_out = QPushButton("Browse...")
        btn_browse_out.clicked.connect(self._browse_output)
        out_row.addWidget(out_lbl)
        out_row.addWidget(self.txt_output, stretch=1)
        out_row.addWidget(btn_browse_out)
        opt_layout.addLayout(out_row)

        layout.addWidget(opt_frame)

        # Bottom actions
        bot_bar = QHBoxLayout()
        self.lbl_status = QLabel("0 files selected")
        self.lbl_status.setStyleSheet("color: #94a3b8; font-size: 12px;")

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_merge = QPushButton("Merge to PDF")
        self.btn_merge.setStyleSheet("background-color: #4f46e5; color: #ffffff; font-weight: 600; padding: 8px 18px; border-radius: 6px;")
        self.btn_merge.clicked.connect(self._execute_merge)

        bot_bar.addWidget(self.lbl_status)
        bot_bar.addStretch()
        bot_bar.addWidget(self.btn_cancel)
        bot_bar.addWidget(self.btn_merge)
        layout.addLayout(bot_bar)

    def add_files(self, paths: List[Path]):
        for p in paths:
            if p.is_file() and p not in self.files:
                self.files.append(p)
                row = self.table.rowCount()
                self.table.insertRow(row)
                self.table.setItem(row, 0, QTableWidgetItem(p.name))
                self.table.setItem(row, 1, QTableWidgetItem(p.suffix.lstrip(".").upper()))
                self.table.setItem(row, 2, QTableWidgetItem(format_bytes(p.stat().st_size)))

        self.lbl_status.setText(f"{len(self.files)} file(s) selected")
        if not self.txt_output.text() and self.files:
            default_out = self.files[0].parent / "merged_document.pdf"
            self.txt_output.setText(str(default_out))

    def _on_add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Files to Merge",
            "",
            "PDF & Images (*.pdf *.jpg *.jpeg *.png *.webp *.bmp *.tiff *.tif);;All Files (*.*)",
        )
        if files:
            self.add_files([Path(f) for f in files])

    def _move_up(self):
        row = self.table.currentRow()
        if row > 0:
            self.files[row - 1], self.files[row] = self.files[row], self.files[row - 1]
            self._refresh_table(row - 1)

    def _move_down(self):
        row = self.table.currentRow()
        if 0 <= row < len(self.files) - 1:
            self.files[row + 1], self.files[row] = self.files[row], self.files[row + 1]
            self._refresh_table(row + 1)

    def _remove_selected(self):
        row = self.table.currentRow()
        if 0 <= row < len(self.files):
            self.files.pop(row)
            self._refresh_table(-1)

    def _clear_all(self):
        self.files.clear()
        self.table.setRowCount(0)
        self.lbl_status.setText("0 files selected")

    def _refresh_table(self, select_row: int):
        self.table.setRowCount(0)
        for p in self.files:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(p.name))
            self.table.setItem(r, 1, QTableWidgetItem(p.suffix.lstrip(".").upper()))
            self.table.setItem(r, 2, QTableWidgetItem(format_bytes(p.stat().st_size)))

        if 0 <= select_row < len(self.files):
            self.table.selectRow(select_row)
        self.lbl_status.setText(f"{len(self.files)} file(s) selected")

    def _browse_output(self):
        f, _ = QFileDialog.getSaveFileName(self, "Save Merged PDF", str(self.txt_output.text()), "PDF Document (*.pdf)")
        if f:
            self.txt_output.setText(f)

    def _execute_merge(self):
        if len(self.files) < 2:
            QMessageBox.warning(self, "Not Enough Files", "Please add at least 2 files to merge.")
            return

        out_path = self.txt_output.text().strip()
        if not out_path:
            QMessageBox.warning(self, "Missing Output", "Please specify a destination file path.")
            return

        try:
            merge_pdfs(self.files, out_path)
            reply = QMessageBox.information(
                self,
                "Merge Successful",
                f"Successfully merged {len(self.files)} files into:\n{out_path}\n\nWould you like to open the output folder?",
                QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Ok,
            )
            if reply == QMessageBox.StandardButton.Open:
                os.startfile(str(Path(out_path).parent))
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "Merge Failed", f"An error occurred while merging:\n{str(exc)}")


# ===========================================================================
# 2. SPLIT DIALOG
# ===========================================================================

class SplitDialog(QDialog):
    """Clean dialog to split a PDF into separate files."""

    def __init__(self, initial_file: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Split PDF")
        self.resize(520, 420)

        self.pdf_file: Optional[Path] = initial_file
        self.total_pages = 0

        self._init_ui()
        if initial_file:
            self._load_file(initial_file)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        # Header
        header = QLabel("Split PDF Document")
        header.setStyleSheet("font-size: 16px; font-weight: 700; color: #f8fafc;")
        sub = QLabel("Divide a PDF into single pages, chunks, or custom page ranges. 100% local.")
        sub.setStyleSheet("font-size: 12px; color: #94a3b8;")
        layout.addWidget(header)
        layout.addWidget(sub)

        # File Selection Card
        file_card = QFrame()
        file_card.setStyleSheet("background-color: #12141c; border-radius: 8px; padding: 10px;")
        fc_layout = QVBoxLayout(file_card)

        f_row = QHBoxLayout()
        self.lbl_file = QLabel("No PDF file selected")
        self.lbl_file.setStyleSheet("color: #cbd5e1; font-weight: 600;")
        btn_browse = QPushButton("Choose PDF...")
        btn_browse.clicked.connect(self._browse_input)
        f_row.addWidget(self.lbl_file, stretch=1)
        f_row.addWidget(btn_browse)
        fc_layout.addLayout(f_row)

        self.lbl_meta = QLabel("Pages: - • Size: -")
        self.lbl_meta.setStyleSheet("color: #94a3b8; font-size: 12px;")
        fc_layout.addWidget(self.lbl_meta)
        layout.addWidget(file_card)

        # Split Options
        opt_group = QFrame()
        opt_group.setStyleSheet("background-color: #1a1d26; border: 1px solid #282c38; border-radius: 8px; padding: 12px;")
        opt_layout = QVBoxLayout(opt_group)
        opt_layout.setSpacing(10)

        self.rb_single = QRadioButton("Split every page into a separate PDF")
        self.rb_single.setChecked(True)

        self.rb_every_n = QRadioButton("Split every N pages:")
        every_row = QHBoxLayout()
        every_row.addWidget(self.rb_every_n)
        self.spn_n = QSpinBox()
        self.spn_n.setRange(2, 500)
        self.spn_n.setValue(2)
        every_row.addWidget(self.spn_n)
        every_row.addStretch()

        self.rb_ranges = QRadioButton("Custom page ranges (e.g. 1-2, 3-5, 8):")
        ranges_row = QVBoxLayout()
        ranges_row.addWidget(self.rb_ranges)
        self.txt_ranges = QLineEdit()
        self.txt_ranges.setPlaceholderText("e.g. 1-3, 5, 7-end")
        self.txt_ranges.setStyleSheet("background-color: #12141c; color: #f3f4f6; border: 1px solid #363b4d; border-radius: 6px; padding: 6px;")
        ranges_row.addWidget(self.txt_ranges)

        self.btn_group = QButtonGroup(self)
        self.btn_group.addButton(self.rb_single)
        self.btn_group.addButton(self.rb_every_n)
        self.btn_group.addButton(self.rb_ranges)

        opt_layout.addWidget(self.rb_single)
        opt_layout.addLayout(every_row)
        opt_layout.addLayout(ranges_row)
        layout.addWidget(opt_group)

        # Output Folder
        out_row = QHBoxLayout()
        out_lbl = QLabel("Output Folder:")
        out_lbl.setStyleSheet("color: #cbd5e1; font-weight: 600;")
        self.txt_output_dir = QLineEdit()
        self.txt_output_dir.setPlaceholderText("Select destination directory...")
        self.txt_output_dir.setStyleSheet("background-color: #1a1d26; color: #f3f4f6; border: 1px solid #363b4d; border-radius: 6px; padding: 6px;")
        btn_browse_dir = QPushButton("Browse...")
        btn_browse_dir.clicked.connect(self._browse_dir)
        out_row.addWidget(out_lbl)
        out_row.addWidget(self.txt_output_dir, stretch=1)
        out_row.addWidget(btn_browse_dir)
        layout.addLayout(out_row)

        layout.addStretch()

        # Bottom actions
        bot_bar = QHBoxLayout()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_split = QPushButton("Split PDF")
        self.btn_split.setStyleSheet("background-color: #4f46e5; color: #ffffff; font-weight: 600; padding: 8px 18px; border-radius: 6px;")
        self.btn_split.clicked.connect(self._execute_split)

        bot_bar.addStretch()
        bot_bar.addWidget(self.btn_cancel)
        bot_bar.addWidget(self.btn_split)
        layout.addLayout(bot_bar)

    def _load_file(self, path: Path):
        try:
            doc = fitz.open(str(path))
            self.pdf_file = path
            self.total_pages = len(doc)
            self.lbl_file.setText(path.name)
            self.lbl_meta.setText(f"Pages: {self.total_pages} • Size: {format_bytes(path.stat().st_size)}")
            self.txt_output_dir.setText(str(path.parent))
            doc.close()
        except Exception as exc:
            QMessageBox.critical(self, "Invalid PDF", f"Could not open PDF file:\n{str(exc)}")

    def _browse_input(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select PDF to Split", "", "PDF Document (*.pdf)")
        if f:
            self._load_file(Path(f))

    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select Output Directory", self.txt_output_dir.text())
        if d:
            self.txt_output_dir.setText(d)

    def _execute_split(self):
        if not self.pdf_file or not self.pdf_file.is_file():
            QMessageBox.warning(self, "No File", "Please select a PDF file to split.")
            return

        out_dir = self.txt_output_dir.text().strip()
        if not out_dir:
            QMessageBox.warning(self, "Missing Output", "Please select an output directory.")
            return

        mode = "all_single"
        ranges = None
        n_val = 1

        if self.rb_every_n.isChecked():
            mode = "every_n"
            n_val = self.spn_n.value()
        elif self.rb_ranges.isChecked():
            mode = "ranges"
            ranges = self.txt_ranges.text().strip()
            if not ranges:
                QMessageBox.warning(self, "Missing Ranges", "Please enter page ranges (e.g. 1-2, 3-5).")
                return

        try:
            generated = split_pdf(self.pdf_file, out_dir, mode=mode, ranges=ranges, n=n_val)
            reply = QMessageBox.information(
                self,
                "Split Complete",
                f"Successfully created {len(generated)} PDF file(s) in:\n{out_dir}\n\nOpen output folder?",
                QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Ok,
            )
            if reply == QMessageBox.StandardButton.Open:
                os.startfile(out_dir)
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "Split Failed", f"An error occurred while splitting:\n{str(exc)}")


# ===========================================================================
# 3. ORGANIZE PAGES DIALOG
# ===========================================================================

class OrganizePagesDialog(QDialog):
    """Visual page manager to reorder, rotate, duplicate, or delete PDF pages."""

    def __init__(self, initial_file: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Reorganize PDF Pages")
        self.resize(780, 560)

        self.pdf_file: Optional[Path] = initial_file
        self.doc: Optional[fitz.Document] = None
        # Page model: list of dicts: {"src_page": int, "rotation": int}
        self.pages: List[Dict[str, int]] = []

        self._init_ui()
        if initial_file:
            self._load_file(initial_file)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        # Header
        top_row = QHBoxLayout()
        h_box = QVBoxLayout()
        header = QLabel("Reorganize PDF Pages")
        header.setStyleSheet("font-size: 16px; font-weight: 700; color: #f8fafc;")
        sub = QLabel("Reorder, rotate, duplicate, or remove pages. 100% local.")
        sub.setStyleSheet("font-size: 12px; color: #94a3b8;")
        h_box.addWidget(header)
        h_box.addWidget(sub)
        top_row.addLayout(h_box)
        top_row.addStretch()

        btn_browse = QPushButton("Choose PDF...")
        btn_browse.clicked.connect(self._browse_file)
        top_row.addWidget(btn_browse)
        layout.addLayout(top_row)

        # Page List Widget
        self.list_widget = QListWidget()
        self.list_widget.setIconSize(QSize(100, 140))
        self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_widget.setSpacing(12)
        self.list_widget.setStyleSheet(
            "QListWidget { background-color: #12141c; border: 1px solid #282c38; border-radius: 8px; padding: 10px; color: #cbd5e1; }"
            "QListWidget::item { background-color: #1a1d26; border: 1px solid #363b4d; border-radius: 6px; padding: 6px; }"
            "QListWidget::item:selected { background-color: #3b4256; border-color: #6366f1; color: #ffffff; }"
        )
        layout.addWidget(self.list_widget, stretch=1)

        # Toolbar under list
        action_bar = QHBoxLayout()
        action_bar.setSpacing(8)

        self.btn_move_left = QPushButton("Move Left")
        self.btn_move_left.clicked.connect(self._move_left)

        self.btn_move_right = QPushButton("Move Right")
        self.btn_move_right.clicked.connect(self._move_right)

        self.btn_rot_cw = QPushButton("Rotate 90°")
        self.btn_rot_cw.clicked.connect(lambda: self._rotate_selected(90))

        self.btn_dup = QPushButton("Duplicate")
        self.btn_dup.clicked.connect(self._duplicate_selected)

        self.btn_del = QPushButton("Delete")
        self.btn_del.setObjectName("DangerButton")
        self.btn_del.clicked.connect(self._delete_selected)

        action_bar.addWidget(self.btn_move_left)
        action_bar.addWidget(self.btn_move_right)
        action_bar.addWidget(self.btn_rot_cw)
        action_bar.addWidget(self.btn_dup)
        action_bar.addWidget(self.btn_del)
        action_bar.addStretch()

        self.lbl_page_count = QLabel("0 pages")
        self.lbl_page_count.setStyleSheet("color: #94a3b8; font-size: 12px;")
        action_bar.addWidget(self.lbl_page_count)
        layout.addLayout(action_bar)

        # Bottom Bar
        bot_bar = QHBoxLayout()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_save = QPushButton("Save Reorganized PDF...")
        self.btn_save.setStyleSheet("background-color: #4f46e5; color: #ffffff; font-weight: 600; padding: 8px 18px; border-radius: 6px;")
        self.btn_save.clicked.connect(self._save_pdf)

        bot_bar.addStretch()
        bot_bar.addWidget(self.btn_cancel)
        bot_bar.addWidget(self.btn_save)
        layout.addLayout(bot_bar)

    def _load_file(self, path: Path):
        try:
            if self.doc:
                self.doc.close()
            self.pdf_file = path
            self.doc = fitz.open(str(path))
            self.pages = [{"src_page": i, "rotation": 0} for i in range(len(self.doc))]
            self._render_thumbnails()
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to load PDF:\n{str(exc)}")

    def _browse_file(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select PDF", "", "PDF Document (*.pdf)")
        if f:
            self._load_file(Path(f))

    def _render_thumbnails(self):
        self.list_widget.clear()
        if not self.doc:
            return

        for idx, p_info in enumerate(self.pages):
            src_idx = p_info["src_page"]
            rot = p_info["rotation"]

            page = self.doc[src_idx]
            pix = fitz_page_to_qpixmap(page, dpi=48)

            if rot != 0:
                from PySide6.QtGui import QTransform
                transform = QTransform().rotate(rot)
                pix = pix.transformed(transform, Qt.TransformationMode.SmoothTransformation)

            item = QListWidgetItem()
            item.setIcon(QIcon(pix))
            rot_str = f" ({rot}°)" if rot else ""
            item.setText(f"Page {idx + 1}\n(Orig: {src_idx + 1}){rot_str}")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.list_widget.addItem(item)

        self.lbl_page_count.setText(f"{len(self.pages)} page(s)")

    def _move_left(self):
        row = self.list_widget.currentRow()
        if row > 0:
            self.pages[row - 1], self.pages[row] = self.pages[row], self.pages[row - 1]
            self._render_thumbnails()
            self.list_widget.setCurrentRow(row - 1)

    def _move_right(self):
        row = self.list_widget.currentRow()
        if 0 <= row < len(self.pages) - 1:
            self.pages[row + 1], self.pages[row] = self.pages[row], self.pages[row + 1]
            self._render_thumbnails()
            self.list_widget.setCurrentRow(row + 1)

    def _rotate_selected(self, angle: int):
        row = self.list_widget.currentRow()
        if 0 <= row < len(self.pages):
            self.pages[row]["rotation"] = (self.pages[row]["rotation"] + angle) % 360
            self._render_thumbnails()
            self.list_widget.setCurrentRow(row)

    def _duplicate_selected(self):
        row = self.list_widget.currentRow()
        if 0 <= row < len(self.pages):
            dup = dict(self.pages[row])
            self.pages.insert(row + 1, dup)
            self._render_thumbnails()
            self.list_widget.setCurrentRow(row + 1)

    def _delete_selected(self):
        row = self.list_widget.currentRow()
        if 0 <= row < len(self.pages):
            if len(self.pages) <= 1:
                QMessageBox.warning(self, "Cannot Delete", "A PDF must retain at least one page.")
                return
            self.pages.pop(row)
            self._render_thumbnails()
            new_row = min(row, len(self.pages) - 1)
            self.list_widget.setCurrentRow(new_row)

    def _save_pdf(self):
        if not self.pdf_file or not self.pages:
            QMessageBox.warning(self, "No Pages", "No pages to save.")
            return

        default_out = self.pdf_file.parent / f"{self.pdf_file.stem}_organized.pdf"
        out_f, _ = QFileDialog.getSaveFileName(self, "Save Reorganized PDF", str(default_out), "PDF Document (*.pdf)")
        if not out_f:
            return

        try:
            page_order = [p["src_page"] for p in self.pages]
            rotations = {idx: p["rotation"] for idx, p in enumerate(self.pages) if p["rotation"] != 0}
            organize_pages(self.pdf_file, out_f, page_order, rotations=rotations)
            reply = QMessageBox.information(
                self,
                "Saved Successfully",
                f"Reorganized PDF saved to:\n{out_f}\n\nOpen output folder?",
                QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Ok,
            )
            if reply == QMessageBox.StandardButton.Open:
                os.startfile(str(Path(out_f).parent))
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "Save Failed", f"Could not save reorganized PDF:\n{str(exc)}")

    def closeEvent(self, event):
        if self.doc:
            self.doc.close()
        super().closeEvent(event)


# ===========================================================================
# 4. COMPRESS DIALOG
# ===========================================================================

class CompressDialog(QDialog):
    """Clean dialog to compress and shrink PDF file size locally."""

    def __init__(self, initial_file: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Compress PDF")
        self.resize(500, 360)

        self.pdf_file: Optional[Path] = initial_file
        self._init_ui()
        if initial_file:
            self._load_file(initial_file)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        # Header
        header = QLabel("Compress PDF File")
        header.setStyleSheet("font-size: 16px; font-weight: 700; color: #f8fafc;")
        sub = QLabel("Reduce file size using local image resampling and stream deflation. 100% offline.")
        sub.setStyleSheet("font-size: 12px; color: #94a3b8;")
        layout.addWidget(header)
        layout.addWidget(sub)

        # File Card
        f_card = QFrame()
        f_card.setStyleSheet("background-color: #12141c; border-radius: 8px; padding: 10px;")
        fc_layout = QHBoxLayout(f_card)
        self.lbl_file = QLabel("No PDF selected")
        self.lbl_file.setStyleSheet("color: #cbd5e1; font-weight: 600;")
        self.lbl_size = QLabel("-")
        self.lbl_size.setStyleSheet("color: #94a3b8; font-size: 12px;")
        btn_browse = QPushButton("Choose PDF...")
        btn_browse.clicked.connect(self._browse_file)
        fc_layout.addWidget(self.lbl_file, stretch=1)
        fc_layout.addWidget(self.lbl_size)
        fc_layout.addWidget(btn_browse)
        layout.addWidget(f_card)

        # Compression Profiles
        opt_group = QFrame()
        opt_group.setStyleSheet("background-color: #1a1d26; border: 1px solid #282c38; border-radius: 8px; padding: 12px;")
        opt_layout = QVBoxLayout(opt_group)
        opt_layout.setSpacing(10)

        self.rb_balanced = QRadioButton("Balanced (Recommended) — 150 DPI, 75% quality, stream deflation")
        self.rb_balanced.setChecked(True)

        self.rb_max = QRadioButton("Maximum Compression — 100 DPI, 55% quality, smallest file size")

        self.rb_lossless = QRadioButton("Lossless — Deflate streams and remove xrefs without altering images")

        self.btn_group = QButtonGroup(self)
        self.btn_group.addButton(self.rb_balanced)
        self.btn_group.addButton(self.rb_max)
        self.btn_group.addButton(self.rb_lossless)

        opt_layout.addWidget(self.rb_balanced)
        opt_layout.addWidget(self.rb_max)
        opt_layout.addWidget(self.rb_lossless)
        layout.addWidget(opt_group)

        # Result Banner
        self.lbl_result = QLabel("")
        self.lbl_result.setStyleSheet("color: #34d399; font-weight: 600; font-size: 13px;")
        self.lbl_result.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_result)

        layout.addStretch()

        # Bottom Actions
        bot_bar = QHBoxLayout()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_compress = QPushButton("Compress PDF")
        self.btn_compress.setStyleSheet("background-color: #4f46e5; color: #ffffff; font-weight: 600; padding: 8px 18px; border-radius: 6px;")
        self.btn_compress.clicked.connect(self._execute_compress)

        bot_bar.addStretch()
        bot_bar.addWidget(self.btn_cancel)
        bot_bar.addWidget(self.btn_compress)
        layout.addLayout(bot_bar)

    def _load_file(self, path: Path):
        self.pdf_file = path
        self.lbl_file.setText(path.name)
        self.lbl_size.setText(format_bytes(path.stat().st_size))

    def _browse_file(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select PDF to Compress", "", "PDF Document (*.pdf)")
        if f:
            self._load_file(Path(f))

    def _execute_compress(self):
        if not self.pdf_file or not self.pdf_file.is_file():
            QMessageBox.warning(self, "No File", "Please select a PDF file to compress.")
            return

        level = "medium"
        if self.rb_max.isChecked():
            level = "high"
        elif self.rb_lossless.isChecked():
            level = "low"

        default_out = self.pdf_file.parent / f"{self.pdf_file.stem}_compressed.pdf"
        out_f, _ = QFileDialog.getSaveFileName(self, "Save Compressed PDF", str(default_out), "PDF Document (*.pdf)")
        if not out_f:
            return

        try:
            stats = compress_pdf(self.pdf_file, out_f, level=level)
            orig_s = format_bytes(stats["original_size"])
            comp_s = format_bytes(stats["compressed_size"])
            pct = stats["savings_percent"]

            msg = f"Original: {orig_s} → Compressed: {comp_s} ({pct:.1f}% space saved)"
            self.lbl_result.setText(f"✅ {msg}")

            reply = QMessageBox.information(
                self,
                "Compression Complete",
                f"{msg}\n\nSaved to:\n{out_f}\n\nOpen output folder?",
                QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Ok,
            )
            if reply == QMessageBox.StandardButton.Open:
                os.startfile(str(Path(out_f).parent))
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "Compression Failed", f"Could not compress PDF:\n{str(exc)}")
