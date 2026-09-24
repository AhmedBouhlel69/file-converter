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
import shutil
from pathlib import Path
from typing import Dict, List, Optional

import fitz  # PyMuPDF
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
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
    QSlider,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from image_converter.core.engine import (
    ConversionConfig,
    FORMAT_EXTENSIONS,
    IMAGE_INPUT_EXTS,
    UniversalConverterEngine,
)
from image_converter.core.pdf_tools import (
    compress_pdf,
    merge_pdfs,
    organize_pages,
    split_pdf,
)
from image_converter.ui.components import format_bytes
from image_converter.ui.theme import icon, repolish, set_variant


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
        header.setObjectName("HeaderLabel")
        sub = QLabel("Reorder PDFs and images to combine them into one document.")
        sub.setObjectName("MutedLabel")
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
        self.table.setAccessibleName("Files to merge")
        layout.addWidget(self.table, stretch=1)

        # Control buttons under table
        ctrl_bar = QHBoxLayout()
        ctrl_bar.setSpacing(8)

        self.btn_add = QPushButton("Add files")
        self.btn_add.setIcon(icon("plus"))
        set_variant(self.btn_add, "secondary")
        self.btn_add.clicked.connect(self._on_add_files)

        self.btn_up = QPushButton("▲ Move Up")
        set_variant(self.btn_up, "secondary")
        self.btn_up.clicked.connect(self._move_up)

        self.btn_down = QPushButton("▼ Move Down")
        set_variant(self.btn_down, "secondary")
        self.btn_down.clicked.connect(self._move_down)

        self.btn_remove = QPushButton("Remove")
        self.btn_remove.setIcon(icon("trash"))
        set_variant(self.btn_remove, "ghost")
        self.btn_remove.clicked.connect(self._remove_selected)

        self.btn_clear = QPushButton("Clear")
        set_variant(self.btn_clear, "danger")
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
        opt_frame.setObjectName("InnerCard")
        opt_layout = QVBoxLayout(opt_frame)
        opt_layout.setContentsMargins(10, 8, 10, 8)
        opt_layout.setSpacing(8)

        out_row = QHBoxLayout()
        out_lbl = QLabel("Output PDF:")
        out_lbl.setObjectName("SectionTitle")
        self.txt_output = QLineEdit()
        self.txt_output.setPlaceholderText("Select destination file...")
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
        self.lbl_status.setObjectName("MutedLabel")

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_merge = QPushButton("Merge to PDF")
        set_variant(self.btn_merge, "primary")
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
        header.setObjectName("HeaderLabel")
        sub = QLabel("Divide a PDF into single pages, chunks, or custom page ranges.")
        sub.setObjectName("MutedLabel")
        layout.addWidget(header)
        layout.addWidget(sub)

        # File Selection Card
        file_card = QFrame()
        file_card.setObjectName("InnerCard")
        fc_layout = QVBoxLayout(file_card)

        f_row = QHBoxLayout()
        self.lbl_file = QLabel("No PDF file selected")
        self.lbl_file.setObjectName("SectionTitle")
        btn_browse = QPushButton("Choose PDF...")
        btn_browse.clicked.connect(self._browse_input)
        f_row.addWidget(self.lbl_file, stretch=1)
        f_row.addWidget(btn_browse)
        fc_layout.addLayout(f_row)

        self.lbl_meta = QLabel("Pages: - • Size: -")
        self.lbl_meta.setObjectName("MutedLabel")
        fc_layout.addWidget(self.lbl_meta)
        layout.addWidget(file_card)

        # Split Options
        opt_group = QFrame()
        opt_group.setObjectName("InnerCard")
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
        out_lbl.setObjectName("SectionTitle")
        self.txt_output_dir = QLineEdit()
        self.txt_output_dir.setPlaceholderText("Select destination directory...")
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
        set_variant(self.btn_split, "primary")
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
        header.setObjectName("HeaderLabel")
        sub = QLabel("Reorder, rotate, duplicate, or remove pages.")
        sub.setObjectName("MutedLabel")
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
        self.list_widget.setAccessibleName("PDF page thumbnails")
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
        set_variant(self.btn_del, "danger")
        self.btn_del.clicked.connect(self._delete_selected)

        action_bar.addWidget(self.btn_move_left)
        action_bar.addWidget(self.btn_move_right)
        action_bar.addWidget(self.btn_rot_cw)
        action_bar.addWidget(self.btn_dup)
        action_bar.addWidget(self.btn_del)
        action_bar.addStretch()

        self.lbl_page_count = QLabel("0 pages")
        self.lbl_page_count.setObjectName("MutedLabel")
        action_bar.addWidget(self.lbl_page_count)
        layout.addLayout(action_bar)

        # Bottom Bar
        bot_bar = QHBoxLayout()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_save = QPushButton("Save Reorganized PDF...")
        set_variant(self.btn_save, "primary")
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

class ImageCompressDialog(QDialog):
    """Compress one or more images through the standard conversion engine."""

    IMAGE_FILTER = (
        "Images (*.jpg *.jpeg *.png *.heic *.heif *.webp *.bmp *.tiff *.tif *.gif *.ico);;"
        "All Files (*.*)"
    )

    def __init__(self, initial_files: Optional[List[Path]] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Compress Images")
        self.resize(680, 540)
        self.setMinimumSize(560, 430)

        self.files: List[Path] = []
        self.engine = UniversalConverterEngine()
        self._init_ui()
        if initial_files:
            self.add_files(initial_files)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        header = QLabel("Compress Images")
        header.setObjectName("HeaderLabel")
        sub = QLabel("Create smaller image copies while keeping the originals unchanged.")
        sub.setObjectName("MutedLabel")
        layout.addWidget(header)
        layout.addWidget(sub)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["File", "Type", "Size"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(self.table, stretch=1)

        controls = QHBoxLayout()
        self.btn_add = QPushButton("Add images")
        self.btn_add.setIcon(icon("plus"))
        set_variant(self.btn_add, "secondary")
        self.btn_add.clicked.connect(self._on_add_files)
        self.btn_remove = QPushButton("Remove")
        self.btn_remove.setIcon(icon("trash"))
        set_variant(self.btn_remove, "ghost")
        self.btn_remove.clicked.connect(self._remove_selected)
        self.btn_clear = QPushButton("Clear")
        set_variant(self.btn_clear, "danger")
        self.btn_clear.clicked.connect(self._clear_all)
        controls.addWidget(self.btn_add)
        controls.addWidget(self.btn_remove)
        controls.addStretch()
        controls.addWidget(self.btn_clear)
        layout.addLayout(controls)

        options = QFrame()
        options.setObjectName("InnerCard")
        options_layout = QVBoxLayout(options)
        options_layout.setContentsMargins(12, 10, 12, 12)
        options_layout.setSpacing(10)

        format_row = QHBoxLayout()
        format_row.addWidget(QLabel("Output format:"))
        self.combo_format = QComboBox()
        self.combo_format.addItems(["WEBP", "JPG", "PNG", "Keep original format"])
        format_row.addWidget(self.combo_format)
        format_row.addStretch()
        options_layout.addLayout(format_row)

        quality_row = QHBoxLayout()
        quality_row.addWidget(QLabel("Quality:"))
        self.slider_quality = QSlider(Qt.Orientation.Horizontal)
        self.slider_quality.setRange(1, 100)
        self.slider_quality.setValue(75)
        self.lbl_quality = QLabel("75%")
        self.lbl_quality.setObjectName("CountBadge")
        self.slider_quality.valueChanged.connect(lambda value: self.lbl_quality.setText(f"{value}%"))
        quality_row.addWidget(self.slider_quality, stretch=1)
        quality_row.addWidget(self.lbl_quality)
        options_layout.addLayout(quality_row)

        resize_row = QHBoxLayout()
        self.chk_resize = QCheckBox("Fit within")
        self.chk_resize.setChecked(True)
        self.spin_max_width = QSpinBox()
        self.spin_max_width.setRange(64, 20000)
        self.spin_max_width.setValue(1920)
        self.spin_max_width.setSuffix(" px wide")
        self.spin_max_height = QSpinBox()
        self.spin_max_height.setRange(64, 20000)
        self.spin_max_height.setValue(1920)
        self.spin_max_height.setSuffix(" px tall")
        resize_row.addWidget(self.chk_resize)
        resize_row.addWidget(self.spin_max_width)
        resize_row.addWidget(self.spin_max_height)
        resize_row.addStretch()
        options_layout.addLayout(resize_row)

        self.chk_strip_metadata = QCheckBox("Strip metadata from compressed copies")
        self.chk_strip_metadata.setChecked(True)
        options_layout.addWidget(self.chk_strip_metadata)

        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Output folder:"))
        self.txt_output_dir = QLineEdit()
        self.txt_output_dir.setPlaceholderText("Same folder as each image")
        btn_browse = QPushButton("Browse...")
        btn_browse.clicked.connect(self._browse_output_dir)
        out_row.addWidget(self.txt_output_dir, stretch=1)
        out_row.addWidget(btn_browse)
        options_layout.addLayout(out_row)
        layout.addWidget(options)

        self.lbl_result = QLabel("")
        self.lbl_result.setProperty("state", "success")
        self.lbl_result.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_result)

        bottom = QHBoxLayout()
        self.lbl_status = QLabel("0 images selected")
        self.lbl_status.setObjectName("MutedLabel")
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_compress = QPushButton("Compress Images")
        set_variant(self.btn_compress, "primary")
        self.btn_compress.clicked.connect(self._execute_compress)
        bottom.addWidget(self.lbl_status)
        bottom.addStretch()
        bottom.addWidget(self.btn_cancel)
        bottom.addWidget(self.btn_compress)
        layout.addLayout(bottom)

    def add_files(self, paths: List[Path]):
        existing = {str(path.resolve()).casefold() for path in self.files if path.exists()}
        for raw_path in paths:
            path = Path(raw_path)
            if not path.is_file() or path.suffix.lower() not in IMAGE_INPUT_EXTS:
                continue
            key = str(path.resolve()).casefold()
            if key in existing:
                continue
            existing.add(key)
            self.files.append(path)
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(path.name))
            self.table.setItem(row, 1, QTableWidgetItem(path.suffix.lstrip(".").upper()))
            self.table.setItem(row, 2, QTableWidgetItem(format_bytes(path.stat().st_size)))
        self._refresh_status()

    def _on_add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select Images to Compress", "", self.IMAGE_FILTER)
        if files:
            self.add_files([Path(path) for path in files])

    def _remove_selected(self):
        rows = sorted({item.row() for item in self.table.selectedItems()}, reverse=True)
        for row in rows:
            if 0 <= row < len(self.files):
                self.files.pop(row)
                self.table.removeRow(row)
        self._refresh_status()

    def _clear_all(self):
        self.files.clear()
        self.table.setRowCount(0)
        self._refresh_status()

    def _browse_output_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder", self.txt_output_dir.text())
        if folder:
            self.txt_output_dir.setText(folder)

    def _refresh_status(self):
        count = len(self.files)
        total = sum(path.stat().st_size for path in self.files if path.exists())
        self.lbl_status.setText(f"{count} image{'s' if count != 1 else ''} selected · {format_bytes(total)}")

    def _target_for(self, source: Path) -> str:
        selected = self.combo_format.currentText().upper()
        if selected.startswith("KEEP"):
            suffix = source.suffix.lower()
            if suffix in (".jpg", ".jpeg"):
                return "JPG"
            if suffix in (".tif", ".tiff"):
                return "TIFF"
            if suffix in (".heic", ".heif"):
                return "HEIC"
            return suffix.lstrip(".").upper()
        return selected

    def _destination_for(self, source: Path, target_format: str) -> Path:
        out_dir_text = self.txt_output_dir.text().strip()
        out_dir = Path(out_dir_text) if out_dir_text else source.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        ext = FORMAT_EXTENSIONS.get(target_format, source.suffix.lower()) or source.suffix.lower()
        candidate = out_dir / f"{source.stem}_compressed{ext}"
        counter = 2
        while candidate.exists():
            candidate = out_dir / f"{source.stem}_compressed_{counter}{ext}"
            counter += 1
        return candidate

    def _execute_compress(self):
        if not self.files:
            QMessageBox.warning(self, "No Images", "Please add at least one image to compress.")
            return

        successes = 0
        failures: List[str] = []
        input_total = 0
        output_total = 0
        last_output_dir: Optional[Path] = None

        for source in self.files:
            try:
                target_format = self._target_for(source)
                destination = self._destination_for(source, target_format)
                config = ConversionConfig(
                    target_format=target_format,
                    quality=self.slider_quality.value(),
                    preserve_metadata=not self.chk_strip_metadata.isChecked(),
                    strip_metadata=self.chk_strip_metadata.isChecked(),
                    auto_orient=True,
                    resize_mode="fit_box" if self.chk_resize.isChecked() else "none",
                    custom_width=self.spin_max_width.value() if self.chk_resize.isChecked() else None,
                    custom_height=self.spin_max_height.value() if self.chk_resize.isChecked() else None,
                    keep_aspect_ratio=True,
                )
                result = self.engine.convert_single(source, destination, config)
                if not result.success:
                    failures.append(f"{source.name}: {result.error_message or 'compression failed'}")
                    continue

                source_size = source.stat().st_size
                output_size = destination.stat().st_size
                same_format = source.suffix.lower() == destination.suffix.lower()
                if same_format and output_size > source_size:
                    shutil.copy2(source, destination)
                    output_size = destination.stat().st_size

                successes += 1
                input_total += source_size
                output_total += output_size
                last_output_dir = destination.parent
            except Exception as exc:
                failures.append(f"{source.name}: {exc}")

        if successes:
            saved = max(0, input_total - output_total)
            pct = (saved / input_total * 100.0) if input_total else 0.0
            msg = (
                f"{successes} compressed · {format_bytes(input_total)} -> "
                f"{format_bytes(output_total)} ({pct:.1f}% saved)"
            )
            self.lbl_result.setText(f"Complete: {msg}")
            self.lbl_result.setProperty("state", "success" if not failures else "warning")
            repolish(self.lbl_result)
            detail = msg
            if failures:
                detail += f"\n\n{len(failures)} image(s) failed:\n" + "\n".join(failures[:5])
            reply = QMessageBox.information(
                self,
                "Image Compression Complete" if not failures else "Image Compression Partially Complete",
                f"{detail}\n\nOpen output folder?",
                QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Ok,
            )
            if reply == QMessageBox.StandardButton.Open and last_output_dir:
                os.startfile(str(last_output_dir))
            self.accept()
        else:
            self.lbl_result.setText("Compression failed")
            self.lbl_result.setProperty("state", "danger")
            repolish(self.lbl_result)
            QMessageBox.critical(
                self,
                "Image Compression Failed",
                "Could not compress the selected images:\n" + "\n".join(failures[:8]),
            )


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
        header.setObjectName("HeaderLabel")
        sub = QLabel("Reduce file size using image resampling and stream deflation.")
        sub.setObjectName("MutedLabel")
        layout.addWidget(header)
        layout.addWidget(sub)

        # File Card
        f_card = QFrame()
        f_card.setObjectName("InnerCard")
        fc_layout = QHBoxLayout(f_card)
        self.lbl_file = QLabel("No PDF selected")
        self.lbl_file.setObjectName("SectionTitle")
        self.lbl_size = QLabel("-")
        self.lbl_size.setObjectName("MutedLabel")
        btn_browse = QPushButton("Choose PDF...")
        btn_browse.clicked.connect(self._browse_file)
        fc_layout.addWidget(self.lbl_file, stretch=1)
        fc_layout.addWidget(self.lbl_size)
        fc_layout.addWidget(btn_browse)
        layout.addWidget(f_card)

        # Compression Profiles
        opt_group = QFrame()
        opt_group.setObjectName("InnerCard")
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
        self.lbl_result.setProperty("state", "success")
        self.lbl_result.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_result)

        layout.addStretch()

        # Bottom Actions
        bot_bar = QHBoxLayout()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_compress = QPushButton("Compress PDF")
        set_variant(self.btn_compress, "primary")
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

            if stats.get("path_taken") == "fallback-copy" or stats.get("saved_bytes", 0) <= 0:
                msg = f"No reduction was achieved (original was already optimal at {orig_s}). Original file preserved."
                self.lbl_result.setText(f"Note: {msg}")
                self.lbl_result.setProperty("state", "warning")
                repolish(self.lbl_result)
                reply = QMessageBox.information(
                    self,
                    "No Reduction Achieved",
                    f"{msg}\n\nCopied to:\n{out_f}\n\nOpen output folder?",
                    QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Ok,
                )
            else:
                msg = f"Original: {orig_s} → Compressed: {comp_s} ({pct:.1f}% space saved)"
                self.lbl_result.setText(f"Complete: {msg}")
                self.lbl_result.setProperty("state", "success")
                repolish(self.lbl_result)
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
