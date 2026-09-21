"""
Main window of Universal File Converter desktop application.
Supports Images, PDF, Word (DOCX), CSV, and Excel (XLSX).
"""

from __future__ import annotations

import dataclasses
import logging
import os
import sys
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
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
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


def get_app_icon() -> QIcon:
    """Load application icon with multi-location fallback."""
    candidates = [
        Path(__file__).resolve().parent / "assets" / "app_icon.png",
        Path(__file__).resolve().parent / "assets" / "app_icon.ico",
        Path(__file__).resolve().parent.parent.parent / "app_icon.png",
        Path(__file__).resolve().parent.parent.parent / "app_icon.ico",
    ]
    for p in candidates:
        if p.exists():
            return QIcon(str(p))
    return QIcon()

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
from image_converter.ui.nav_rail import NavRailWidget
from image_converter.ui.stats_widget import StatsWidget
from image_converter.ui.theme import DARK_STYLESHEET
from image_converter.ui.tool_dialogs import (
    CompressDialog,
    MergeDialog,
    OrganizePagesDialog,
    SplitDialog,
)
from image_converter.ui.worker import BatchConversionWorker


class ImageConverterMainWindow(QMainWindow):
    """Primary application window for Universal File Converter."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Universal File Converter (Images, PDF, Word, Excel, CSV)")
        self.resize(1240, 800)
        self.setMinimumSize(940, 600)

        app_icon = get_app_icon()
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)

        self.engine = UniversalConverterEngine()
        self.worker: Optional[BatchConversionWorker] = None
        self.last_output_dir: Optional[Path] = None
        self._is_converting: bool = False

        self._init_ui()
        self.setStyleSheet(DARK_STYLESHEET)

    def _init_ui(self):
        central_widget = QWidget()
        central_widget.setObjectName("centralWidget")
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(10)

        # 1. Top Header Bar: App Identity
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(4, 2, 4, 4)

        header_left = QHBoxLayout()
        header_left.setSpacing(12)

        app_icon = get_app_icon()
        if not app_icon.isNull():
            lbl_icon = QLabel()
            lbl_icon.setPixmap(app_icon.pixmap(36, 36))
            header_left.addWidget(lbl_icon)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        app_title = QLabel("Universal File Converter")
        app_title.setObjectName("HeaderLabel")
        app_sub = QLabel("100% Local & Private • Batch Converter & Document Tools")
        app_sub.setObjectName("MutedLabel")
        title_box.addWidget(app_title)
        title_box.addWidget(app_sub)
        header_left.addLayout(title_box)

        top_bar.addLayout(header_left)
        top_bar.addStretch()

        main_layout.addLayout(top_bar)

        # 2. Quick Actions Bar (Batch queue actions + Document Tools)
        conv_top_bar = QHBoxLayout()
        conv_top_bar.setContentsMargins(0, 0, 0, 0)
        conv_top_bar.setSpacing(8)

        self.btn_add_files = QPushButton("➕ Add Files (Ctrl+O)")
        self.btn_add_files.setObjectName("SecondaryButton")
        self.btn_add_files.clicked.connect(self._add_files_dialog)

        self.btn_add_folder = QPushButton("📁 Add Folder (Ctrl+Shift+O)")
        self.btn_add_folder.setObjectName("SecondaryButton")
        self.btn_add_folder.clicked.connect(self._add_folder_dialog)

        self.btn_remove_item = QPushButton("🗑️ Remove (Del)")
        self.btn_remove_item.setObjectName("SecondaryButton")
        self.btn_remove_item.clicked.connect(self._remove_selected)

        self.btn_clear_all = QPushButton("Clear All")
        self.btn_clear_all.setObjectName("DangerButton")
        self.btn_clear_all.clicked.connect(self._clear_all_items)

        conv_top_bar.addWidget(self.btn_add_files)
        conv_top_bar.addWidget(self.btn_add_folder)
        conv_top_bar.addWidget(self.btn_remove_item)
        conv_top_bar.addWidget(self.btn_clear_all)

        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #363b4d; margin: 2px 4px;")
        conv_top_bar.addWidget(sep)

        # 4 Core Document Tools
        self.btn_tool_merge = QPushButton("Merge to PDF...")
        self.btn_tool_merge.setObjectName("SecondaryButton")
        self.btn_tool_merge.clicked.connect(self._open_merge_dialog)

        self.btn_tool_split = QPushButton("Split PDF...")
        self.btn_tool_split.setObjectName("SecondaryButton")
        self.btn_tool_split.clicked.connect(self._open_split_dialog)

        self.btn_tool_organize = QPushButton("Organize Pages...")
        self.btn_tool_organize.setObjectName("SecondaryButton")
        self.btn_tool_organize.clicked.connect(self._open_organize_dialog)

        self.btn_tool_compress = QPushButton("Compress PDF...")
        self.btn_tool_compress.setObjectName("SecondaryButton")
        self.btn_tool_compress.clicked.connect(self._open_compress_dialog)

        conv_top_bar.addWidget(self.btn_tool_merge)
        conv_top_bar.addWidget(self.btn_tool_split)
        conv_top_bar.addWidget(self.btn_tool_organize)
        conv_top_bar.addWidget(self.btn_tool_compress)
        conv_top_bar.addStretch()

        main_layout.addLayout(conv_top_bar)

        # 3. Middle Area: Nav Rail (Left) + Splitter (Center Queue / Right Inspector)
        middle_layout = QHBoxLayout()
        middle_layout.setContentsMargins(0, 0, 0, 0)
        middle_layout.setSpacing(8)

        # Left Nav Rail
        self.nav_rail = NavRailWidget()
        self.nav_rail.tab_changed.connect(self._on_nav_tab_changed)
        middle_layout.addWidget(self.nav_rail)

        # Horizontal Splitter for queue table and right panel
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Center Container (Drop Zone + Queue Table)
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(8)

        self.drop_zone = DropZoneWidget()
        self.drop_zone.files_added.connect(self.add_images)
        center_layout.addWidget(self.drop_zone)

        self.queue_table = QueueTableWidget()
        self.queue_table.item_selected.connect(self._on_table_row_selected)
        self.queue_table.tool_merge_requested.connect(self._open_merge_dialog_with_files)
        self.queue_table.tool_split_requested.connect(self._open_split_dialog_with_file)
        self.queue_table.tool_organize_requested.connect(self._open_organize_dialog_with_file)
        self.queue_table.tool_compress_requested.connect(self._open_compress_dialog_with_file)
        center_layout.addWidget(self.queue_table)

        splitter.addWidget(center_widget)

        # Right Panel: QStackedWidget hosting Settings, Preview, and Stats
        self.right_stack = QStackedWidget()
        self.right_stack.setMinimumWidth(350)

        # Page 0: Settings Panel
        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setFrameShape(QFrame.Shape.NoFrame)
        settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.settings_widget = ConversionSettingsWidget()
        self.settings_widget.settings_changed.connect(self._on_settings_changed)
        settings_scroll.setWidget(self.settings_widget)
        self.right_stack.addWidget(settings_scroll)

        # Page 1: Preview & Metadata Inspector Panel
        preview_scroll = QScrollArea()
        preview_scroll.setWidgetResizable(True)
        preview_scroll.setFrameShape(QFrame.Shape.NoFrame)
        preview_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.preview_widget = FilePreviewWidget()
        preview_scroll.setWidget(self.preview_widget)
        self.right_stack.addWidget(preview_scroll)

        # Page 2: Stats & Metrics Panel
        stats_scroll = QScrollArea()
        stats_scroll.setWidgetResizable(True)
        stats_scroll.setFrameShape(QFrame.Shape.NoFrame)
        stats_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.stats_widget = StatsWidget()
        stats_scroll.setWidget(self.stats_widget)
        self.right_stack.addWidget(stats_scroll)

        splitter.addWidget(self.right_stack)

        splitter.setSizes([800, 400])
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        middle_layout.addWidget(splitter, stretch=1)
        main_layout.addLayout(middle_layout, stretch=1)

        # 4. Bottom Action & Progress Bar for Batch Converter
        bottom_bar = QFrame()
        bottom_bar.setObjectName("CardFrame")
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(16, 10, 16, 10)
        bottom_layout.setSpacing(14)

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

        self.btn_open_folder = QPushButton("📂 Open Output Folder")
        self.btn_open_folder.setObjectName("SuccessButton")
        self.btn_open_folder.setVisible(False)
        self.btn_open_folder.clicked.connect(self._open_output_folder)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("DangerButton")
        self.btn_cancel.setVisible(False)
        self.btn_cancel.clicked.connect(self._cancel_conversion)

        self.btn_convert_all = QPushButton("🚀 Convert All (Ctrl+Enter)")
        self.btn_convert_all.setObjectName("PrimaryButton")
        self.btn_convert_all.clicked.connect(self.start_conversion)

        bottom_layout.addWidget(self.btn_open_folder)
        bottom_layout.addWidget(self.btn_cancel)
        bottom_layout.addWidget(self.btn_convert_all)

        main_layout.addWidget(bottom_bar)

        # Setup Keyboard Shortcuts
        self._setup_shortcuts()

    def _open_merge_dialog(self):
        selected_paths = self._get_selected_or_all_paths()
        dlg = MergeDialog(initial_files=selected_paths, parent=self)
        dlg.exec()

    def _open_merge_dialog_with_files(self, paths: List[Path]):
        dlg = MergeDialog(initial_files=paths, parent=self)
        dlg.exec()

    def _open_split_dialog(self):
        pdf_path = self._get_selected_pdf_path()
        dlg = SplitDialog(initial_file=pdf_path, parent=self)
        dlg.exec()

    def _open_split_dialog_with_file(self, path: Path):
        dlg = SplitDialog(initial_file=path, parent=self)
        dlg.exec()

    def _open_organize_dialog(self):
        pdf_path = self._get_selected_pdf_path()
        dlg = OrganizePagesDialog(initial_file=pdf_path, parent=self)
        dlg.exec()

    def _open_organize_dialog_with_file(self, path: Path):
        dlg = OrganizePagesDialog(initial_file=path, parent=self)
        dlg.exec()

    def _open_compress_dialog(self):
        pdf_path = self._get_selected_pdf_path()
        dlg = CompressDialog(initial_file=pdf_path, parent=self)
        dlg.exec()

    def _open_compress_dialog_with_file(self, path: Path):
        dlg = CompressDialog(initial_file=path, parent=self)
        dlg.exec()

    def _get_selected_or_all_paths(self) -> List[Path]:
        selected = self.queue_table.get_selected_file_paths()
        if selected:
            return selected
        return list(self.queue_table.file_paths)

    def _get_selected_pdf_path(self) -> Optional[Path]:
        for p in self.queue_table.get_selected_file_paths():
            if p.suffix.lower() == ".pdf":
                return p
        row = self.queue_table.currentRow()
        if 0 <= row < len(self.queue_table.file_paths):
            p = self.queue_table.file_paths[row]
            if p.suffix.lower() == ".pdf":
                return p
        for p in self.queue_table.file_paths:
            if p.suffix.lower() == ".pdf":
                return p
        return None

    def _setup_shortcuts(self):
        """Bind ergonomic keyboard shortcuts."""
        shortcut_add_file = QShortcut(QKeySequence("Ctrl+O"), self)
        shortcut_add_file.activated.connect(self._add_files_dialog)

        shortcut_add_folder = QShortcut(QKeySequence("Ctrl+Shift+O"), self)
        shortcut_add_folder.activated.connect(self._add_folder_dialog)

        shortcut_convert = QShortcut(QKeySequence("Ctrl+Return"), self)
        shortcut_convert.activated.connect(self.start_conversion)

        shortcut_delete = QShortcut(QKeySequence("Delete"), self)
        shortcut_delete.activated.connect(self._remove_selected)

        shortcut_esc = QShortcut(QKeySequence("Escape"), self)
        shortcut_esc.activated.connect(self._cancel_conversion)

    def _on_nav_tab_changed(self, index: int):
        self.right_stack.setCurrentIndex(index)

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
        self.drop_zone.set_collapsed(total > 0)

        # Automatically select the first newly added file if none selected
        if self.queue_table.currentRow() < 0 and total > 0:
            self.queue_table.selectRow(0)

    add_files = add_images

    def _add_files_dialog(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Files to Convert",
            "",
            "All Supported Files (*.jpg *.jpeg *.png *.heic *.heif *.webp *.bmp *.tiff *.tif *.gif *.ico *.pdf *.docx *.csv *.xlsx *.pptx *.odt *.rtf *.txt);;"
            "Documents & Presentations (*.pdf *.docx *.pptx *.odt *.rtf *.txt);;"
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
        self.queue_table.remove_selected_rows()
        total = len(self.queue_table.file_paths)
        self.lbl_status.setText(f"Ready • {total} file(s) in queue")
        self.drop_zone.set_collapsed(total > 0)
        if total == 0:
            self.preview_widget.clear_preview()

    def _clear_all_items(self):
        self.queue_table.clear_all()
        self.preview_widget.clear_preview()
        self.drop_zone.set_collapsed(False)
        self.lbl_status.setText("Ready • 0 file(s) in queue")
        self.btn_open_folder.setVisible(False)
        self.progress_bar.setVisible(False)
        self.progress_bar.setValue(0)

    def _on_table_row_selected(self, file_path: str):
        self.preview_widget.set_image(file_path)
        # Activate Preview tab in nav rail
        self.nav_rail.set_active_tab(1)

    def _on_settings_changed(self):
        fmt = self.settings_widget.get_target_format()
        self.queue_table.set_target_format_all(fmt)

    def start_conversion(self):
        """Build conversion tasks and run background worker thread."""
        if self._is_converting:
            return

        files = self.queue_table.file_paths
        if not files:
            QMessageBox.information(
                self,
                "No Files",
                "Please add files or folders before starting conversion.",
            )
            return

        base_config = self.settings_widget.get_config()
        custom_out_dir = self.settings_widget.get_output_directory()

        tasks = []
        for row_idx, f in enumerate(files):
            out_dir = custom_out_dir if custom_out_dir else f.parent
            # Read format chosen specifically for this row from the queue table
            row_fmt = self.queue_table.get_target_format_for_row(row_idx)
            row_ext = FORMAT_EXTENSIONS.get(row_fmt, f".{row_fmt.lower()}")
            row_config = dataclasses.replace(base_config, target_format=row_fmt)

            if row_fmt in ("STRIP_METADATA", "CLEAN") or not row_ext:
                target_ext = f.suffix.lower()
                dest_file = out_dir / f"{f.stem}_clean{target_ext}"
            else:
                dest_file = out_dir / f"{f.stem}{row_ext}"
                if dest_file.resolve() == f.resolve():
                    suffix = "_clean" if row_config.strip_metadata else "_converted"
                    dest_file = out_dir / f"{f.stem}{suffix}{row_ext}"
            tasks.append((f, dest_file, row_config))

        self.last_output_dir = custom_out_dir or (files[0].parent if files else None)

        # Reset row states
        for row in range(self.queue_table.rowCount()):
            self.queue_table.update_status(row, "⏳ Pending", "#9ca3af")
            item = self.queue_table.item(row, 7)
            if item:
                item.setText("-")

        # UI state: converting
        self._is_converting = True
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
            if result.error_message:
                self.queue_table.update_status(idx, "⚠️ Done (Warning)", "#fbbf24")
                item = self.queue_table.item(idx, 0)
                if item:
                    item.setToolTip(result.error_message)
            else:
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
        self._is_converting = False
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

        # Update metrics & switch to Stats tab
        self.stats_widget.update_stats(
            success_count,
            fail_count,
            elapsed_sec,
            in_bytes,
            out_bytes,
        )
        self.nav_rail.set_active_tab(2)

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
        self._is_converting = False
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
    from image_converter.core.logging_config import setup_logger
    setup_logger()

    # Set Windows AppUserModelID so taskbar displays our custom icon
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("UniversalFileConverter.App.1.0")
        except Exception as e:
            logger.warning(f"Failed to set Windows AppUserModelID: {e}", exc_info=True)

    app = QApplication(sys.argv)
    app.setApplicationName("Universal File Converter")
    app.setApplicationDisplayName("Universal File Converter")

    icon = get_app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)

    window = ImageConverterMainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    launch_app()
