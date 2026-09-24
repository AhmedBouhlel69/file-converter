"""Main PySide6 window and presentation glue for the Universal File Converter."""

from __future__ import annotations

import dataclasses
import logging
import os
import sys
from pathlib import Path
from typing import List, Optional

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

from image_converter.cli import collect_convertible_files
from image_converter.core.engine import FORMAT_EXTENSIONS, UniversalConverterEngine
from image_converter.ui.components import (
    ConversionSettingsWidget,
    DropZoneWidget,
    FilePreviewWidget,
    format_bytes,
)
from image_converter.ui.image_tools_page import ImageToolsPage
from image_converter.ui.pdf_tools_page import PdfToolsPage
from image_converter.ui.queue_model import QueueTableView
from image_converter.ui.stats_widget import StatsWidget
from image_converter.ui.theme import apply_theme, icon, set_eyebrow, set_variant
from image_converter.ui.tool_dialogs import (
    CompressDialog,
    ImageCompressDialog,
    MergeDialog,
    OrganizePagesDialog,
    SplitDialog,
)
from image_converter.ui.worker import BatchConversionWorker

logger = logging.getLogger(__name__)


def get_app_icon() -> QIcon:
    """Load the application icon from source or bundled locations."""
    candidates = [
        Path(__file__).resolve().parent / "assets" / "app_icon.png",
        Path(__file__).resolve().parent / "assets" / "app_icon.ico",
        Path(__file__).resolve().parent.parent.parent / "app_icon.png",
        Path(__file__).resolve().parent.parent.parent / "app_icon.ico",
    ]
    for path in candidates:
        if path.exists():
            return QIcon(str(path))
    return QIcon()


class DragOverlay(QFrame):
    """Window-sized drag target displayed only while files are hovering."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DragOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.hide()
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)
        glyph = QLabel()
        glyph.setPixmap(icon("upload").pixmap(56, 56))
        glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("Drop to add files")
        title.setObjectName("DragOverlayTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        help_text = QLabel("Folders are scanned recursively. Unsupported files are ignored.")
        help_text.setObjectName("MutedLabel")
        help_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(glyph)
        layout.addWidget(title)
        layout.addWidget(help_text)


class ImageConverterMainWindow(QMainWindow):
    """Primary application window. Conversion engines remain presentation-agnostic."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Universal File Converter")
        self.resize(1380, 860)
        self.setMinimumSize(1120, 700)
        self.setAcceptDrops(True)

        app_icon = get_app_icon()
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)

        self.engine = UniversalConverterEngine()
        self.worker: Optional[BatchConversionWorker] = None
        self.last_output_dir: Optional[Path] = None
        self._is_converting = False
        self._active_rows: List[int] = []
        self._last_removed: List[tuple[Path, str]] = []
        self._footer_state = "ready"

        self._init_ui()
        apply_theme(self)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _init_ui(self):
        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 16, 20, 18)
        root.setSpacing(12)

        root.addWidget(self._build_header())

        self.app_stack = QStackedWidget()
        self.convert_page = self._build_convert_page()
        self.pdf_tools_page = PdfToolsPage()
        self.pdf_tools_page.merge_requested.connect(self._open_merge_dialog)
        self.pdf_tools_page.split_requested.connect(self._open_split_dialog)
        self.pdf_tools_page.organize_requested.connect(self._open_organize_dialog)
        self.pdf_tools_page.compress_requested.connect(self._open_compress_dialog)
        self.image_tools_page = ImageToolsPage()
        self.image_tools_page.compress_requested.connect(self._open_image_compress_dialog)
        self.app_stack.addWidget(self.convert_page)
        self.app_stack.addWidget(self.pdf_tools_page)
        self.app_stack.addWidget(self.image_tools_page)
        root.addWidget(self.app_stack, stretch=1)

        self.drag_overlay = DragOverlay(central)
        self.drag_overlay.raise_()

        # Backward-compatible attributes retained without rendering removed views.
        self.nav_rail = None
        self.stats_widget = StatsWidget()
        self.stats_widget.hide()
        self.right_stack = self.inspector_stack

        self._setup_shortcuts()
        self._setup_tab_order()
        self._set_app_mode(0)
        self._refresh_queue_ui()

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("HeaderBar")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(12)

        app_icon = get_app_icon()
        if not app_icon.isNull():
            glyph = QLabel()
            glyph.setPixmap(app_icon.pixmap(40, 40))
            glyph.setAccessibleName("Universal File Converter icon")
            layout.addWidget(glyph)

        brand = QVBoxLayout()
        brand.setSpacing(0)
        eyebrow = QLabel("LOCAL FILE WORKSPACE")
        set_eyebrow(eyebrow)
        title = QLabel("Universal File Converter")
        title.setObjectName("AppTitle")
        brand.addWidget(eyebrow)
        brand.addWidget(title)
        layout.addLayout(brand)
        layout.addSpacing(16)

        mode_surface = QFrame()
        mode_surface.setObjectName("ToolbarSurface")
        mode_layout = QHBoxLayout(mode_surface)
        mode_layout.setContentsMargins(4, 4, 4, 4)
        mode_layout.setSpacing(4)
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.btn_mode_convert = QPushButton("Convert")
        self.btn_mode_images = QPushButton("Image Tools")
        self.btn_mode_pdf = QPushButton("PDF Tools")
        for index, button in enumerate((self.btn_mode_convert, self.btn_mode_images, self.btn_mode_pdf)):
            button.setCheckable(True)
            set_variant(button, "mode")
            self.mode_group.addButton(button, index)
            mode_layout.addWidget(button)
        self.mode_group.idClicked.connect(self._set_app_mode)
        layout.addWidget(mode_surface)
        layout.addStretch()

        self.btn_add_files = QPushButton("Add files")
        self.btn_add_files.setIcon(icon("plus"))
        self.btn_add_files.setToolTip("Choose one or more files (Ctrl+O)")
        self.btn_add_files.setAccessibleName("Add files")
        self.btn_add_files.setAccessibleDescription("Choose one or more files for the conversion queue.")
        self.btn_add_files.clicked.connect(self._add_files_dialog)

        self.btn_add_folder = QPushButton("Add folder")
        self.btn_add_folder.setIcon(icon("folder"))
        set_variant(self.btn_add_folder, "ghost")
        self.btn_add_folder.setToolTip("Scan a folder recursively (Ctrl+Shift+O)")
        self.btn_add_folder.clicked.connect(self._add_folder_dialog)

        self.privacy_badge = QLabel("●  ON-DEVICE · NO UPLOADS")
        self.privacy_badge.setObjectName("PrivacyBadge")
        self.privacy_badge.setCursor(Qt.CursorShape.ArrowCursor)
        self.privacy_badge.setAccessibleDescription("All file processing happens locally.")
        layout.addWidget(self.btn_add_files)
        layout.addWidget(self.btn_add_folder)
        layout.addWidget(self.privacy_badge)
        return header

    def _build_convert_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(12)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_queue_panel())
        splitter.addWidget(self._build_inspector_panel())
        splitter.setSizes([900, 400])
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 2)
        page_layout.addWidget(splitter, stretch=1)
        page_layout.addWidget(self._build_footer())
        return page

    def _build_queue_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("WorkspaceCard")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Conversion queue")
        title.setObjectName("SectionTitle")
        self.lbl_queue_count = QLabel("0 FILES")
        self.lbl_queue_count.setObjectName("CountBadge")
        self.btn_remove_item = QPushButton("Remove")
        set_variant(self.btn_remove_item, "ghost")
        self.btn_remove_item.setEnabled(False)
        self.btn_remove_item.setToolTip("Remove selected rows (Delete)")
        self.btn_remove_item.clicked.connect(self._remove_selected)
        self.btn_clear_all = QPushButton("Clear queue")
        set_variant(self.btn_clear_all, "danger")
        self.btn_clear_all.setEnabled(False)
        self.btn_clear_all.clicked.connect(self._clear_all_items)
        header.addWidget(title)
        header.addWidget(self.lbl_queue_count)
        header.addStretch()
        header.addWidget(self.btn_remove_item)
        header.addWidget(self.btn_clear_all)
        layout.addLayout(header)

        self.queue_state_stack = QStackedWidget()
        self.drop_zone = DropZoneWidget()
        self.drop_zone.setAcceptDrops(False)
        self.drop_zone.files_added.connect(self.add_images)
        self.queue_state_stack.addWidget(self.drop_zone)

        populated = QWidget()
        populated_layout = QVBoxLayout(populated)
        populated_layout.setContentsMargins(0, 0, 0, 0)
        populated_layout.setSpacing(8)
        compact_bar = QFrame()
        compact_bar.setObjectName("ToolbarSurface")
        compact_layout = QHBoxLayout(compact_bar)
        compact_layout.setContentsMargins(10, 6, 8, 6)
        compact_hint = QLabel("Drop more files anywhere in the window")
        compact_hint.setObjectName("MutedLabel")
        self.btn_add_more = QPushButton("+  Add more")
        set_variant(self.btn_add_more, "ghost")
        self.btn_add_more.clicked.connect(self._add_files_dialog)
        compact_layout.addWidget(compact_hint)
        compact_layout.addStretch()
        compact_layout.addWidget(self.btn_add_more)
        populated_layout.addWidget(compact_bar)

        self.queue_table = QueueTableView()
        self.queue_table.item_selected.connect(self._on_table_row_selected)
        self.queue_table.tool_merge_requested.connect(self._open_merge_dialog_with_files)
        self.queue_table.tool_split_requested.connect(self._open_split_dialog_with_file)
        self.queue_table.tool_organize_requested.connect(self._open_organize_dialog_with_file)
        self.queue_table.tool_compress_requested.connect(self._open_compress_dialog_with_file)
        self.queue_table.tool_image_compress_requested.connect(self._open_image_compress_dialog_with_files)
        self.queue_table.retry_requested.connect(self._retry_row)
        self.queue_table.selectionModel().selectionChanged.connect(self._on_queue_selection_changed)
        model = self.queue_table.queue_model
        model.rowsInserted.connect(self._on_queue_structure_changed)
        model.rowsRemoved.connect(self._on_queue_structure_changed)
        model.modelReset.connect(self._on_queue_structure_changed)
        model.totals_changed.connect(self._on_queue_totals_changed)
        model.analysis_finished.connect(lambda _row: self._refresh_queue_ui(update_status=False))
        populated_layout.addWidget(self.queue_table, stretch=1)
        self.queue_state_stack.addWidget(populated)
        layout.addWidget(self.queue_state_stack, stretch=1)

        self.undo_toast = QFrame()
        self.undo_toast.setObjectName("ToolbarSurface")
        toast_layout = QHBoxLayout(self.undo_toast)
        toast_layout.setContentsMargins(10, 5, 7, 5)
        self.lbl_undo = QLabel("Removed from queue")
        self.lbl_undo.setObjectName("MutedLabel")
        self.btn_undo = QPushButton("Undo")
        set_variant(self.btn_undo, "link")
        self.btn_undo.clicked.connect(self._undo_last_removal)
        toast_layout.addWidget(self.lbl_undo)
        toast_layout.addStretch()
        toast_layout.addWidget(self.btn_undo)
        self.undo_toast.hide()
        layout.addWidget(self.undo_toast)
        return panel

    def _build_inspector_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("InspectorCard")
        panel.setMinimumWidth(340)
        panel.setMaximumWidth(420)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        self.inspector_stack = QStackedWidget()
        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setFrameShape(QFrame.Shape.NoFrame)
        settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.settings_widget = ConversionSettingsWidget()
        self.settings_widget.settings_changed.connect(self._on_settings_changed)
        settings_scroll.setWidget(self.settings_widget)
        self.inspector_stack.addWidget(settings_scroll)

        inspector_page = QWidget()
        inspector_layout = QVBoxLayout(inspector_page)
        inspector_layout.setContentsMargins(0, 0, 0, 0)
        self.btn_back_to_settings = QPushButton("←  Back to batch settings")
        set_variant(self.btn_back_to_settings, "link")
        self.btn_back_to_settings.clicked.connect(self._show_batch_settings)
        inspector_layout.addWidget(self.btn_back_to_settings)
        preview_scroll = QScrollArea()
        preview_scroll.setWidgetResizable(True)
        preview_scroll.setFrameShape(QFrame.Shape.NoFrame)
        preview_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.preview_widget = FilePreviewWidget()
        preview_scroll.setWidget(self.preview_widget)
        inspector_layout.addWidget(preview_scroll, stretch=1)
        self.inspector_stack.addWidget(inspector_page)
        layout.addWidget(self.inspector_stack, stretch=1)
        return panel

    def _build_footer(self) -> QFrame:
        footer = QFrame()
        footer.setObjectName("BottomDock")
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(16, 10, 12, 10)
        layout.setSpacing(12)
        copy = QVBoxLayout()
        copy.setSpacing(2)
        self.lbl_status = QLabel("0 files · 0 B → —")
        self.lbl_status.setObjectName("StatusLabel")
        self.lbl_status_hint = QLabel("Your originals are never overwritten.")
        self.lbl_status_hint.setObjectName("MutedLabel")
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        copy.addWidget(self.lbl_status)
        copy.addWidget(self.lbl_status_hint)
        copy.addWidget(self.progress_bar)
        layout.addLayout(copy, stretch=1)

        self.btn_open_folder = QPushButton("Open folder")
        set_variant(self.btn_open_folder, "success")
        self.btn_open_folder.hide()
        self.btn_open_folder.clicked.connect(self._open_output_folder)
        self.btn_convert_more = QPushButton("Convert more")
        set_variant(self.btn_convert_more, "ghost")
        self.btn_convert_more.hide()
        self.btn_convert_more.clicked.connect(self._convert_more)
        self.btn_convert_all = QPushButton("Convert 0 files")
        set_variant(self.btn_convert_all, "primary")
        self.btn_convert_all.setEnabled(False)
        self.btn_convert_all.clicked.connect(self._primary_footer_action)
        self.btn_cancel = self.btn_convert_all  # compatibility alias
        layout.addWidget(self.btn_open_folder)
        layout.addWidget(self.btn_convert_more)
        layout.addWidget(self.btn_convert_all)
        return footer

    # ------------------------------------------------------------------
    # Navigation, drag-and-drop, and accessibility
    # ------------------------------------------------------------------
    def _set_app_mode(self, index: int):
        if not hasattr(self, "app_stack"):
            return
        index = 0 if index not in (0, 1, 2) else index
        self.app_stack.setCurrentIndex(index)
        self.btn_mode_convert.setChecked(index == 0)
        self.btn_mode_images.setChecked(index == 1)
        self.btn_mode_pdf.setChecked(index == 2)
        self.btn_add_files.setVisible(index == 0)
        self.btn_add_folder.setVisible(index == 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "drag_overlay"):
            self.drag_overlay.setGeometry(self.centralWidget().rect().adjusted(4, 4, -4, -4))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not self._is_converting:
            event.acceptProposedAction()
            self.drag_overlay.setGeometry(self.centralWidget().rect().adjusted(4, 4, -4, -4))
            self.drag_overlay.show()
            self.drag_overlay.raise_()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls() and not self._is_converting:
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.drag_overlay.hide()
        event.accept()

    def dropEvent(self, event):
        self.drag_overlay.hide()
        paths: List[Path] = []
        for url in event.mimeData().urls():
            candidate = Path(url.toLocalFile())
            if candidate.exists():
                paths.extend(collect_convertible_files(candidate, recursive=True))
        if paths:
            self._set_app_mode(0)
            self.add_images(paths)
        event.acceptProposedAction()

    def _setup_shortcuts(self):
        bindings = (
            ("Ctrl+O", self._add_files_dialog),
            ("Ctrl+Shift+O", self._add_folder_dialog),
            ("Ctrl+Return", self.start_conversion),
            ("Delete", self._remove_selected),
            ("Escape", self._cancel_conversion),
        )
        self._shortcuts = []
        for keys, handler in bindings:
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.activated.connect(handler)
            self._shortcuts.append(shortcut)

    def _setup_tab_order(self):
        widgets = [
            self.btn_mode_convert,
            self.btn_mode_images,
            self.btn_mode_pdf,
            self.btn_add_files,
            self.btn_add_folder,
            self.btn_remove_item,
            self.btn_clear_all,
            self.queue_table,
            self.settings_widget,
            self.btn_convert_all,
        ]
        for current, following in zip(widgets, widgets[1:]):
            self.setTabOrder(current, following)

    # ------------------------------------------------------------------
    # Queue state and inspector
    # ------------------------------------------------------------------
    def _on_queue_structure_changed(self, *_args):
        self._refresh_queue_ui()
        if not self.queue_table.file_paths:
            self._show_batch_settings()

    def _on_queue_totals_changed(self, _input_total: int, _estimated_total):
        self._refresh_queue_ui(update_status=not self._is_converting)

    def _on_queue_selection_changed(self, *_args):
        selected = bool(self.queue_table.get_selected_rows())
        self.btn_remove_item.setEnabled(selected and not self._is_converting)
        if not selected:
            self.inspector_stack.setCurrentIndex(0)

    def _on_table_row_selected(self, file_path: str):
        self.preview_widget.set_image(file_path)
        self.inspector_stack.setCurrentIndex(1)
        self.btn_remove_item.setEnabled(not self._is_converting)

    def _show_batch_settings(self):
        self.queue_table.clearSelection()
        self.inspector_stack.setCurrentIndex(0)

    def _refresh_queue_ui(self, update_status: bool = True):
        if not hasattr(self, "queue_table"):
            return
        model = self.queue_table.queue_model
        total = model.rowCount()
        selected = bool(self.queue_table.get_selected_rows())
        self.lbl_queue_count.setText(f"{total} FILE" if total == 1 else f"{total} FILES")
        self.queue_state_stack.setCurrentIndex(1 if total else 0)
        self.btn_remove_item.setEnabled(selected and not self._is_converting)
        self.btn_clear_all.setEnabled(bool(total) and not self._is_converting)
        self.btn_convert_all.setEnabled(bool(total))
        if self._is_converting:
            self.btn_convert_all.setText("Cancel conversion")
            set_variant(self.btn_add_files, "secondary")
            set_variant(self.btn_convert_all, "danger")
        elif total:
            self.btn_convert_all.setText(f"Convert {total} file{'s' if total != 1 else ''}")
            set_variant(self.btn_add_files, "secondary")
            set_variant(self.btn_convert_all, "primary")
        else:
            self.btn_convert_all.setText("Convert 0 files")
            set_variant(self.btn_add_files, "primary")
            set_variant(self.btn_convert_all, "secondary")

        input_total = model.input_total()
        estimated_total = model.estimated_total()
        estimate = f"~{format_bytes(estimated_total)}" if estimated_total is not None else "—"
        if update_status and self._footer_state == "ready" and not self._is_converting:
            self.lbl_status.setText(
                f"{total} file{'s' if total != 1 else ''} · {format_bytes(input_total)} → {estimate}"
            )
            self.lbl_status_hint.setText("Your originals are never overwritten.")

        if hasattr(self.settings_widget, "set_queue_context"):
            compatible_formats = model.compatible_format_intersection()
            self.settings_widget.set_queue_context(
                compatible_formats,
                model.has_images(),
                model.has_documents(),
                estimated_total,
                mixed_queue=bool(total and not compatible_formats),
            )
            selected_default = self.settings_widget.get_target_format()
            if selected_default and model.default_format != selected_default:
                model.set_default_format(selected_default)

    def _set_queue_editing_enabled(self, enabled: bool):
        self.btn_add_files.setEnabled(enabled)
        self.btn_add_folder.setEnabled(enabled)
        self.btn_add_more.setEnabled(enabled)
        self.drop_zone.setEnabled(enabled)
        self.settings_widget.setEnabled(enabled)
        selected = bool(self.queue_table.get_selected_rows())
        has_files = bool(self.queue_table.file_paths)
        self.btn_remove_item.setEnabled(enabled and selected)
        self.btn_clear_all.setEnabled(enabled and has_files)

    def add_images(self, file_paths: List[Path]):
        self._set_app_mode(0)
        added = self.queue_table.add_files(file_paths, self.settings_widget.get_target_format())
        self._footer_state = "ready"
        self.undo_toast.hide()
        self._refresh_queue_ui()
        if not added and file_paths:
            self.lbl_status_hint.setText("Those files are already in the queue or are unsupported.")

    add_files = add_images

    def _add_files_dialog(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Choose files to convert",
            "",
            "All Supported Files (*.jpg *.jpeg *.png *.heic *.heif *.webp *.bmp *.tiff *.tif *.gif *.ico *.pdf *.docx *.csv *.xlsx *.pptx *.odt *.rtf *.txt);;"
            "Documents & Presentations (*.pdf *.docx *.pptx *.odt *.rtf *.txt);;"
            "Spreadsheets (*.csv *.xlsx);;"
            "Images (*.jpg *.jpeg *.png *.heic *.heif *.webp *.bmp *.tiff *.tif *.gif *.ico);;"
            "All Files (*.*)",
        )
        if files:
            self.add_images([Path(path) for path in files])

    def _add_folder_dialog(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose a folder")
        if folder:
            self.add_images(collect_convertible_files(Path(folder), recursive=True))

    def _remove_selected(self):
        if self._is_converting:
            return
        rows = self.queue_table.get_selected_rows()
        if not rows:
            return
        self._last_removed = [
            (self.queue_table.queue_model.entry(row).path, self.queue_table.queue_model.entry(row).target_format)
            for row in rows
        ]
        removed = self.queue_table.remove_selected_rows()
        if removed:
            self.lbl_undo.setText(
                f"Removed {len(removed)} file{'s' if len(removed) != 1 else ''} from the queue"
            )
            self.undo_toast.show()
        self._refresh_queue_ui()

    def _clear_all_items(self):
        if self._is_converting or not self.queue_table.file_paths:
            return
        self._last_removed = [
            (entry.path, entry.target_format) for entry in self.queue_table.queue_model.entries
        ]
        count = len(self._last_removed)
        self.queue_table.clear_all()
        self.preview_widget.clear_preview()
        self.btn_open_folder.hide()
        self.btn_convert_more.hide()
        self.progress_bar.hide()
        self.lbl_undo.setText(f"Cleared {count} file{'s' if count != 1 else ''} from the queue")
        self.undo_toast.show()
        self._footer_state = "ready"
        self._refresh_queue_ui()

    def _undo_last_removal(self):
        if not self._last_removed:
            return
        restored = list(self._last_removed)
        self._last_removed.clear()
        rows = self.queue_table.add_files(
            [path for path, _target in restored],
            self.settings_widget.get_target_format(),
        )
        for row, (_path, target) in zip(rows, restored):
            self.queue_table.set_target_format_for_row(row, target)
        self.undo_toast.hide()
        self._refresh_queue_ui()

    def _on_settings_changed(self):
        if not hasattr(self, "queue_table"):
            return
        model = self.queue_table.queue_model
        model.set_default_format(self.settings_widget.get_target_format())
        model.set_quality(self.settings_widget.slider_quality.value())
        self._refresh_queue_ui()

    # ------------------------------------------------------------------
    # Conversion lifecycle
    # ------------------------------------------------------------------
    def _primary_footer_action(self):
        if self._is_converting:
            self._cancel_conversion()
        else:
            self.start_conversion()

    def start_conversion(self, rows: Optional[List[int]] = None):
        if self._is_converting:
            return
        model = self.queue_table.queue_model
        if not model.entries:
            return
        rows = list(range(model.rowCount())) if rows is None else rows
        rows = [row for row in rows if model.entry(row)]
        if not rows:
            return

        base_config = self.settings_widget.get_config()
        custom_out_dir = self.settings_widget.get_output_directory()
        tasks = []
        for row in rows:
            entry = model.entry(row)
            source = entry.path
            out_dir = custom_out_dir if custom_out_dir else source.parent
            row_fmt = entry.target_format
            row_ext = FORMAT_EXTENSIONS.get(row_fmt, f".{row_fmt.lower()}")
            row_config = dataclasses.replace(base_config, target_format=row_fmt)
            if row_fmt in ("STRIP_METADATA", "CLEAN") or not row_ext:
                destination = out_dir / f"{source.stem}_clean{source.suffix.lower()}"
            else:
                destination = out_dir / f"{source.stem}{row_ext}"
                if destination.resolve() == source.resolve():
                    suffix = "_clean" if row_config.strip_metadata else "_converted"
                    destination = out_dir / f"{source.stem}{suffix}{row_ext}"
            tasks.append((source, destination, row_config))

        self._active_rows = rows
        self.last_output_dir = custom_out_dir or model.entry(rows[0]).path.parent
        for row in rows:
            model.update_status(row, "Queued", progress=0)
            model.entry(row).output_size = None
            model.entry(row).error = ""
        model.update_status(rows[0], "Converting", progress=0)

        self._is_converting = True
        self._footer_state = "converting"
        self._set_queue_editing_enabled(False)
        self.btn_open_folder.hide()
        self.btn_convert_more.hide()
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.btn_convert_all.setEnabled(True)
        self.btn_convert_all.setText("Cancel conversion")
        set_variant(self.btn_convert_all, "danger")
        self.lbl_status.setText(f"Converting 0 of {len(tasks)} files")
        self.lbl_status_hint.setText("Cancel stops after the current file finishes.")

        self.worker = BatchConversionWorker(tasks, self.engine)
        self.worker.file_started.connect(self._on_file_started)
        self.worker.file_completed.connect(self._on_file_completed)
        self.worker.progress_updated.connect(self._on_progress_updated)
        self.worker.batch_finished.connect(self._on_batch_finished)
        self.worker.batch_cancelled.connect(self._on_batch_cancelled)
        self.worker.start()

    def _retry_row(self, row: int):
        if not self._is_converting:
            self.start_conversion([row])

    def _on_file_started(self, worker_index: int, _name: str):
        if 0 <= worker_index < len(self._active_rows):
            self.queue_table.queue_model.update_status(
                self._active_rows[worker_index], "Converting", progress=10
            )

    def _on_file_completed(self, worker_index: int, result):
        if not (0 <= worker_index < len(self._active_rows)):
            return
        row = self._active_rows[worker_index]
        model = self.queue_table.queue_model
        if result.success:
            model.update_status(
                row,
                "Warning" if result.error_message else "Done",
                progress=100,
                error=result.error_message or "",
            )
            model.update_output_size(row, result.output_size_bytes)
        else:
            model.update_status(
                row,
                "Failed",
                progress=0,
                error=result.error_message or "Conversion failed. Review the file and retry.",
            )

    def _on_progress_updated(self, current: int, total: int, percentage: int):
        self.progress_bar.setValue(percentage)
        self.lbl_status.setText(f"Converting {current} of {total} files · {percentage}%")

    def _on_batch_finished(
        self,
        success_count: int,
        fail_count: int,
        elapsed_sec: float,
        in_bytes: int,
        out_bytes: int,
    ):
        self._is_converting = False
        self._footer_state = "completed" if not fail_count else "partial_failure"
        self._set_queue_editing_enabled(True)
        self.progress_bar.setValue(100)
        self.progress_bar.hide()
        set_variant(self.btn_convert_all, "primary")
        self.btn_convert_all.setText(
            f"Convert {len(self.queue_table.file_paths)} file{'s' if len(self.queue_table.file_paths) != 1 else ''}"
        )
        self.btn_open_folder.setVisible(success_count > 0)
        self.btn_convert_more.show()
        self.lbl_status.setText(
            f"{success_count} converted · {fail_count} failed"
            if fail_count
            else f"{success_count} converted · {format_bytes(in_bytes)} → {format_bytes(out_bytes)}"
        )
        self.lbl_status_hint.setText(
            "Select a failed status to retry."
            if fail_count
            else f"Completed in {elapsed_sec:.2f}s. Your originals were not changed."
        )
        self._refresh_queue_ui(update_status=False)

    def _on_batch_cancelled(self):
        self._is_converting = False
        self._footer_state = "ready"
        for row in self._active_rows:
            entry = self.queue_table.queue_model.entry(row)
            if entry and entry.status in {"Queued", "Converting"}:
                self.queue_table.queue_model.update_status(row, "Cancelled", progress=0)
        self._set_queue_editing_enabled(True)
        self.progress_bar.hide()
        set_variant(self.btn_convert_all, "primary")
        self.btn_convert_all.setText(
            f"Convert {len(self.queue_table.file_paths)} file{'s' if len(self.queue_table.file_paths) != 1 else ''}"
        )
        self.lbl_status.setText("Conversion cancelled")
        self.lbl_status_hint.setText("Completed outputs were kept. Adjust the batch or convert again.")

    def _cancel_conversion(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.btn_convert_all.setEnabled(False)
            self.btn_convert_all.setText("Cancelling…")
            self.lbl_status.setText("Cancelling after the current file…")

    def _convert_more(self):
        self._footer_state = "ready"
        self.btn_open_folder.hide()
        self.btn_convert_more.hide()
        self._add_files_dialog()
        self._refresh_queue_ui()

    # ------------------------------------------------------------------
    # PDF tools and output helpers
    # ------------------------------------------------------------------
    def _open_merge_dialog(self):
        MergeDialog(initial_files=self._get_selected_or_all_paths(), parent=self).exec()

    def _open_merge_dialog_with_files(self, paths: List[Path]):
        MergeDialog(initial_files=paths, parent=self).exec()

    def _open_split_dialog(self):
        SplitDialog(initial_file=self._get_selected_pdf_path(), parent=self).exec()

    def _open_split_dialog_with_file(self, path: Path):
        SplitDialog(initial_file=path, parent=self).exec()

    def _open_organize_dialog(self):
        OrganizePagesDialog(initial_file=self._get_selected_pdf_path(), parent=self).exec()

    def _open_organize_dialog_with_file(self, path: Path):
        OrganizePagesDialog(initial_file=path, parent=self).exec()

    def _open_compress_dialog(self):
        CompressDialog(initial_file=self._get_selected_pdf_path(), parent=self).exec()

    def _open_compress_dialog_with_file(self, path: Path):
        CompressDialog(initial_file=path, parent=self).exec()

    def _open_image_compress_dialog(self):
        ImageCompressDialog(initial_files=self._get_selected_or_all_image_paths(), parent=self).exec()

    def _open_image_compress_dialog_with_files(self, paths: List[Path]):
        ImageCompressDialog(initial_files=paths, parent=self).exec()

    def _get_selected_or_all_paths(self) -> List[Path]:
        selected = self.queue_table.get_selected_file_paths()
        return selected or list(self.queue_table.file_paths)

    def _get_selected_pdf_path(self) -> Optional[Path]:
        selected = self.queue_table.get_selected_file_paths()
        for path in selected:
            if path.suffix.lower() == ".pdf":
                return path
        row = self.queue_table.currentRow()
        if 0 <= row < len(self.queue_table.file_paths):
            path = self.queue_table.file_paths[row]
            if path.suffix.lower() == ".pdf":
                return path
        return next(
            (path for path in self.queue_table.file_paths if path.suffix.lower() == ".pdf"),
            None,
        )

    def _get_selected_or_all_image_paths(self) -> List[Path]:
        image_exts = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".bmp", ".tif", ".tiff", ".gif", ".ico"}
        selected = [path for path in self.queue_table.get_selected_file_paths() if path.suffix.lower() in image_exts]
        if selected:
            return selected
        return [path for path in self.queue_table.file_paths if path.suffix.lower() in image_exts]

    def _open_output_folder(self):
        if self.last_output_dir and self.last_output_dir.exists():
            os.startfile(str(self.last_output_dir))
        else:
            QMessageBox.warning(
                self,
                "Output folder unavailable",
                "The output folder no longer exists. Choose a new destination and convert again.",
            )


UniversalFileConverterMainWindow = ImageConverterMainWindow


def launch_app():
    from image_converter.core.logging_config import setup_logger

    setup_logger()
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "UniversalFileConverter.App.1.0"
            )
        except Exception as exc:
            logger.warning("Failed to set Windows AppUserModelID: %s", exc)

    app = QApplication(sys.argv)
    app.setApplicationName("Universal File Converter")
    app.setApplicationDisplayName("Universal File Converter")
    apply_theme(app)
    icon_value = get_app_icon()
    if not icon_value.isNull():
        app.setWindowIcon(icon_value)
    window = ImageConverterMainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    launch_app()
