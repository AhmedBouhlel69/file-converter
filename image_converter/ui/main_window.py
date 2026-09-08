"""
Main window of Universal File Converter desktop application.
Supports Images, PDF, Word (DOCX), CSV, and Excel (XLSX).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from image_converter.cli import collect_convertible_files
from image_converter.core.engine import (
    FORMAT_EXTENSIONS,
    ImageConverterEngine,
    UniversalConverterEngine,
)
from image_converter.ui.components import (
    ConversionSettingsWidget,
    DropZoneWidget,
    FilePreviewWidget,
    QueueTableWidget,
    format_bytes,
)
from image_converter.ui.theme import DARK_STYLESHEET
from image_converter.ui.worker import BatchConversionWorker


class ImageConverterMainWindow(QMainWindow):
    """Primary application window for Universal File Converter."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Universal File Converter (Images, PDF, Word, Excel, CSV)")
        self.resize(1180, 780)
        self.setMinimumSize(880, 580)

        self.engine = UniversalConverterEngine()
        self.worker: Optional[BatchConversionWorker] = None
        self.last_output_dir: Optional[Path] = None

        self._init_ui()
        self.setStyleSheet(DARK_STYLESHEET)

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # 1. Top Header Bar
        top_bar = QHBoxLayout()

        title_box = QVBoxLayout()
        app_title = QLabel("Universal File Converter")
        app_title.setObjectName("HeaderLabel")
        app_sub = QLabel("Convert between Images, PDF, Word (.docx), Excel (.xlsx), and CSV files")
        app_sub.setObjectName("MutedLabel")
        title_box.addWidget(app_title)
        title_box.addWidget(app_sub)
        top_bar.addLayout(title_box)

        top_bar.addStretch()

        self.btn_add_files = QPushButton("➕ Add Files")
        self.btn_add_files.setObjectName("SecondaryButton")
        self.btn_add_files.clicked.connect(self._add_files_dialog)

        self.btn_add_folder = QPushButton("📁 Add Folder")
        self.btn_add_folder.setObjectName("SecondaryButton")
        self.btn_add_folder.clicked.connect(self._add_folder_dialog)

        self.btn_remove_item = QPushButton("🗑️ Remove")
        self.btn_remove_item.setObjectName("SecondaryButton")
        self.btn_remove_item.clicked.connect(self._remove_selected)

        self.btn_clear_all = QPushButton("Clear All")
        self.btn_clear_all.setObjectName("DangerButton")
        self.btn_clear_all.clicked.connect(self._clear_all_items)

        top_bar.addWidget(self.btn_add_files)
        top_bar.addWidget(self.btn_add_folder)
        top_bar.addWidget(self.btn_remove_item)
        top_bar.addWidget(self.btn_clear_all)

        main_layout.addLayout(top_bar)

        # 2. Main Content (Splitter: Left = DropZone + Queue Table, Right = Sidebar)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left Container
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        self.drop_zone = DropZoneWidget()
        self.drop_zone.files_added.connect(self.add_images)
        left_layout.addWidget(self.drop_zone)

        self.queue_table = QueueTableWidget()
        self.queue_table.item_selected.connect(self._on_table_row_selected)
        left_layout.addWidget(self.queue_table)

        splitter.addWidget(left_widget)

        # Right Container (Sidebar with scroll)
        sidebar_scroll = QScrollArea()
        sidebar_scroll.setWidgetResizable(True)
        sidebar_scroll.setFrameShape(QFrame.Shape.NoFrame)
        sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        sidebar_widget = QWidget()
        sidebar_layout = QVBoxLayout(sidebar_widget)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(12)

        self.preview_widget = FilePreviewWidget()
        self.settings_widget = ConversionSettingsWidget()
        self.settings_widget.settings_changed.connect(self._on_settings_changed)

        sidebar_layout.addWidget(self.preview_widget)
        sidebar_layout.addWidget(self.settings_widget)
        sidebar_layout.addStretch()

        sidebar_scroll.setWidget(sidebar_widget)
        splitter.addWidget(sidebar_scroll)

        # Set splitter proportions (70% table, 30% sidebar)
        splitter.setStretchFactor(0, 7)
        splitter.setStretchFactor(1, 3)

        main_layout.addWidget(splitter)

        # 3. Bottom Action & Progress Bar
        bottom_bar = QFrame()
        bottom_bar.setObjectName("CardFrame")
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(14, 10, 14, 10)
        bottom_layout.setSpacing(14)

        # Status & progress
        stat_box = QVBoxLayout()
        stat_box.setSpacing(4)

        self.lbl_status = QLabel("Ready • 0 file(s) in queue")
        self.lbl_status.setStyleSheet("font-weight: 500; color: #cbd5e1;")

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)

        stat_box.addWidget(self.lbl_status)
        stat_box.addWidget(self.progress_bar)
        bottom_layout.addLayout(stat_box, stretch=1)

        # Buttons
        self.btn_open_folder = QPushButton("📂 Open Output Folder")
        self.btn_open_folder.setObjectName("SuccessButton")
        self.btn_open_folder.setVisible(False)
        self.btn_open_folder.clicked.connect(self._open_output_folder)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("DangerButton")
        self.btn_cancel.setVisible(False)
        self.btn_cancel.clicked.connect(self._cancel_conversion)

        self.btn_convert_all = QPushButton("🚀 Convert All")
        self.btn_convert_all.setObjectName("PrimaryButton")
        self.btn_convert_all.clicked.connect(self.start_conversion)

        bottom_layout.addWidget(self.btn_open_folder)
        bottom_layout.addWidget(self.btn_cancel)
        bottom_layout.addWidget(self.btn_convert_all)

        main_layout.addWidget(bottom_bar)

    def add_images(self, file_paths: List[Path]):
        """Add files to batch queue."""
        target_fmt = self.settings_widget.get_target_format()
        current_paths = set(self.queue_table.file_paths)
        new_count = 0

        for p in file_paths:
            if p not in current_paths:
                self.queue_table.add_file_item(p, target_fmt)
                new_count += 1

        total = len(self.queue_table.file_paths)
        self.lbl_status.setText(f"Ready • {total} file(s) in queue")

        # Automatically select the first newly added file if none selected
        if self.queue_table.currentRow() < 0 and total > 0:
            self.queue_table.selectRow(0)

    add_files = add_images

    def _add_files_dialog(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Files to Convert",
            "",
            "All Supported Files (*.jpg *.jpeg *.png *.heic *.heif *.webp *.bmp *.tiff *.tif *.gif *.ico *.pdf *.docx *.csv *.xlsx);;"
            "Documents (*.pdf *.docx);;"
            "Spreadsheets (*.csv *.xlsx);;"
            "Images (*.jpg *.jpeg *.png *.heic *.heif *.webp *.bmp *.tiff *.tif *.gif *.ico);;"
            "All Files (*.*)",
        )
        if files:
            self.add_images([Path(f) for f in files])

    def _add_folder_dialog(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder Containing Files")
        if folder:
            paths = collect_convertible_files(Path(folder), recursive=True)
            self.add_images(paths)

    def _remove_selected(self):
        self.queue_table.remove_selected_row()
        total = len(self.queue_table.file_paths)
        self.lbl_status.setText(f"Ready • {total} file(s) in queue")
        if total == 0:
            self.preview_widget.clear_preview()

    def _clear_all_items(self):
        self.queue_table.clear_all()
        self.preview_widget.clear_preview()
        self.lbl_status.setText("Ready • 0 file(s) in queue")
        self.btn_open_folder.setVisible(False)
        self.progress_bar.setVisible(False)
        self.progress_bar.setValue(0)

    def _on_table_row_selected(self, file_path: str):
        self.preview_widget.set_image(file_path)

    def _on_settings_changed(self):
        fmt = self.settings_widget.get_target_format()
        self.queue_table.set_target_format_all(fmt)

    def start_conversion(self):
        """Build conversion tasks and run background worker thread."""
        files = self.queue_table.file_paths
        if not files:
            QMessageBox.information(
                self,
                "No Files",
                "Please add files or folders before starting conversion.",
            )
            return

        config = self.settings_widget.get_config()
        ext = FORMAT_EXTENSIONS.get(config.target_format, f".{config.target_format.lower()}")
        custom_out_dir = self.settings_widget.get_output_directory()

        tasks = []
        for f in files:
            out_dir = custom_out_dir if custom_out_dir else f.parent
            dest_file = out_dir / f"{f.stem}{ext}"
            if dest_file.resolve() == f.resolve():
                dest_file = out_dir / f"{f.stem}_converted{ext}"
            tasks.append((f, dest_file, config))

        self.last_output_dir = custom_out_dir or (files[0].parent if files else None)

        # Reset row states
        for row in range(self.queue_table.rowCount()):
            self.queue_table.update_status(row, "⏳ Pending", "#9ca3af")
            item = self.queue_table.item(row, 7)
            if item:
                item.setText("-")

        # UI state: converting
        self.btn_convert_all.setEnabled(False)
        self.btn_cancel.setVisible(True)
        self.btn_open_folder.setVisible(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.lbl_status.setText(f"Converting 0 of {len(tasks)} files...")

        # Start background worker
        self.worker = BatchConversionWorker(tasks, self.engine)
        self.worker.file_started.connect(self._on_file_started)
        self.worker.file_completed.connect(self._on_file_completed)
        self.worker.progress_updated.connect(self._on_progress_updated)
        self.worker.batch_finished.connect(self._on_batch_finished)
        self.worker.batch_cancelled.connect(self._on_batch_cancelled)
        self.worker.start()

    def _on_file_started(self, idx: int, name: str):
        self.queue_table.update_status(idx, "🔄 Converting...", "#818cf8")
        self.lbl_status.setText(f"Converting {idx + 1} of {len(self.queue_table.file_paths)}: {name}")

    def _on_file_completed(self, idx: int, result):
        if result.success:
            self.queue_table.update_status(idx, "✅ Done", "#34d399")
            self.queue_table.update_converted_size(idx, result.output_size_bytes)
        else:
            self.queue_table.update_status(idx, "❌ Error", "#f87171")
            item = self.queue_table.item(idx, 0)
            if item:
                item.setToolTip(result.error_message or "Unknown error")

    def _on_progress_updated(self, current: int, total: int, pct: int):
        self.progress_bar.setValue(pct)
        self.lbl_status.setText(f"Converting {current} of {total} files ({pct}%)...")

    def _on_batch_finished(
        self,
        success_count: int,
        fail_count: int,
        elapsed_sec: float,
        in_bytes: int,
        out_bytes: int,
    ):
        self.btn_convert_all.setEnabled(True)
        self.btn_cancel.setVisible(False)
        self.btn_open_folder.setVisible(True)

        delta_bytes = in_bytes - out_bytes
        saved_str = ""
        if in_bytes > 0:
            pct_change = (delta_bytes / in_bytes) * 100.0
            if delta_bytes > 0:
                saved_str = f" • Saved {format_bytes(delta_bytes)} ({pct_change:.1f}%)"
            elif delta_bytes < 0:
                saved_str = f" • Size increased by {format_bytes(-delta_bytes)}"

        status_msg = f"Completed: {success_count} succeeded, {fail_count} failed in {elapsed_sec:.2f}s{saved_str}"
        self.lbl_status.setText(status_msg)

        QMessageBox.information(
            self,
            "Conversion Complete",
            f"Batch Conversion Finished!\n\n"
            f"• Succeeded: {success_count}\n"
            f"• Failed: {fail_count}\n"
            f"• Time Taken: {elapsed_sec:.2f} seconds\n"
            f"• Original Size: {format_bytes(in_bytes)}\n"
            f"• Converted Size: {format_bytes(out_bytes)}\n"
            f"{'• Saved: ' + format_bytes(delta_bytes) + ' (' + f'{pct_change:.1f}%' + ')' if delta_bytes > 0 else ''}",
        )

    def _on_batch_cancelled(self):
        self.btn_convert_all.setEnabled(True)
        self.btn_cancel.setVisible(False)
        self.btn_open_folder.setVisible(False)
        self.progress_bar.setVisible(False)
        self.lbl_status.setText("Conversion cancelled")

    def _cancel_conversion(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.lbl_status.setText("Cancelling conversion...")

    def _open_output_folder(self):
        if self.last_output_dir and self.last_output_dir.exists():
            os.startfile(str(self.last_output_dir))
        else:
            QMessageBox.warning(self, "Warning", "Output directory does not exist or has not been set.")


# Alias for backward compatibility
UniversalFileConverterMainWindow = ImageConverterMainWindow


def launch_app():
    app = QApplication(sys.argv)
    app.setApplicationName("Universal File Converter")
    window = ImageConverterMainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    launch_app()
