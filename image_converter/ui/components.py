"""
Custom Qt components: DropZone, Preview, Settings, and Queue Table.
Supports Images, PDF, Word (DOCX), CSV, and Excel (XLSX).
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Dict, List, Optional

import fitz  # PyMuPDF
from PIL import Image
from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from image_converter.cli import collect_convertible_files
from image_converter.core.engine import (
    ConversionConfig,
    FORMAT_EXTENSIONS,
    _HEIF_AVAILABLE,
    get_file_metadata,
    get_image_metadata,
    get_supported_output_formats,
)


def get_compatible_output_formats(file_path_or_ext: str | Path) -> List[str]:
    """Return list of supported output formats for a given input file extension."""
    if isinstance(file_path_or_ext, Path):
        ext = file_path_or_ext.suffix.lower()
    else:
        ext = str(file_path_or_ext).lower()
        if not ext.startswith(".") and "." in ext:
            ext = Path(ext).suffix.lower()
        elif not ext.startswith("."):
            ext = f".{ext}"

    # 1. PDF
    if ext == ".pdf":
        return ["DOCX", "TXT", "PNG", "JPG", "CSV", "XLSX", "PPTX"]

    # 2. Word (.docx, .doc)
    elif ext in (".docx", ".doc"):
        return ["PDF", "TXT", "HTML", "PNG", "JPG", "ODT", "RTF", "PPTX"]

    # 3. PowerPoint (.pptx)
    elif ext == ".pptx":
        return ["PDF", "TXT", "HTML", "PNG", "JPG", "DOCX"]

    # 4. OpenDocument (.odt)
    elif ext == ".odt":
        return ["PDF", "DOCX", "TXT", "RTF"]

    # 5. Rich Text (.rtf)
    elif ext == ".rtf":
        return ["PDF", "DOCX", "TXT", "ODT"]

    # 6. Text (.txt)
    elif ext == ".txt":
        return ["PDF", "DOCX", "PPTX", "RTF", "HTML"]

    # 7. CSV (.csv)
    elif ext == ".csv":
        return ["XLSX", "PDF", "JSON", "HTML", "TXT"]

    # 8. Excel (.xlsx, .xls)
    elif ext in (".xlsx", ".xls"):
        return ["CSV", "PDF", "JSON", "HTML"]

    # 9. Standard Images
    else:
        fmts = ["JPG", "PNG", "WEBP"]
        if _HEIF_AVAILABLE:
            fmts.append("HEIC")
        fmts.extend(["BMP", "TIFF", "GIF", "ICO", "PDF", "TXT", "DOCX"])
        return fmts


def format_bytes(size: int) -> str:
    """Format file size in human-readable units."""
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    else:
        return f"{size / (1024 * 1024):.2f} MB"


def pil_to_qpixmap(pil_img: Image.Image) -> QPixmap:
    """Safely convert PIL Image to QPixmap, handling any mode."""
    if pil_img.mode != "RGBA":
        pil_img = pil_img.convert("RGBA")
    data = pil_img.tobytes("raw", "RGBA")
    qimg = QImage(
        data,
        pil_img.width,
        pil_img.height,
        pil_img.width * 4,
        QImage.Format.Format_RGBA8888,
    )
    return QPixmap.fromImage(qimg)


def fitz_pixmap_to_qpixmap(pix: fitz.Pixmap) -> QPixmap:
    """Convert PyMuPDF Pixmap to QPixmap."""
    if pix.alpha:
        qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGBA8888)
    else:
        qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimg)


class DropZoneWidget(QFrame):
    """Interactive drag and drop landing box for files and folders with compact/collapsed modes."""

    files_added = Signal(list)  # list of Path objects

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self._is_collapsed = False

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(14, 10, 14, 10)
        self.main_layout.setSpacing(6)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Full view content
        self.full_container = QWidget()
        full_layout = QVBoxLayout(self.full_container)
        full_layout.setContentsMargins(0, 0, 0, 0)
        full_layout.setSpacing(6)
        full_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.title_lbl = QLabel("📁 Drag & Drop Files or Folders Here")
        self.title_lbl.setStyleSheet("font-size: 15px; font-weight: 600; color: #cbd5e1;")
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.sub_lbl = QLabel("Supports PDF, Word (.docx), Excel (.xlsx), CSV, Presentations, Text, and Images")
        self.sub_lbl.setObjectName("MutedLabel")
        self.sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        btn_layout = QHBoxLayout()
        btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_layout.setSpacing(10)

        self.btn_browse_files = QPushButton("Browse Files...")
        self.btn_browse_files.setObjectName("SecondaryButton")
        self.btn_browse_files.clicked.connect(self._browse_files)

        self.btn_browse_folder = QPushButton("Browse Folder...")
        self.btn_browse_folder.setObjectName("SecondaryButton")
        self.btn_browse_folder.clicked.connect(self._browse_folder)

        btn_layout.addWidget(self.btn_browse_files)
        btn_layout.addWidget(self.btn_browse_folder)

        full_layout.addWidget(self.title_lbl)
        full_layout.addWidget(self.sub_lbl)
        full_layout.addLayout(btn_layout)
        self.main_layout.addWidget(self.full_container)

        # Compact strip view (when collapsed)
        self.compact_container = QWidget()
        compact_layout = QHBoxLayout(self.compact_container)
        compact_layout.setContentsMargins(4, 0, 4, 0)
        compact_layout.setSpacing(12)

        self.compact_lbl = QLabel("📥 Drag & drop additional files here, or click to add")
        self.compact_lbl.setStyleSheet("font-weight: 500; color: #94a3b8; font-size: 12px;")
        compact_layout.addWidget(self.compact_lbl)
        compact_layout.addStretch()

        self.btn_compact_add = QPushButton("➕ Add Files")
        self.btn_compact_add.setObjectName("SecondaryButton")
        self.btn_compact_add.clicked.connect(self._browse_files)
        compact_layout.addWidget(self.btn_compact_add)

        self.main_layout.addWidget(self.compact_container)
        self.compact_container.setVisible(False)
        self.setMinimumHeight(110)

    def set_collapsed(self, collapsed: bool):
        self._is_collapsed = collapsed
        self.full_container.setVisible(not collapsed)
        self.compact_container.setVisible(collapsed)
        if collapsed:
            self.setMinimumHeight(44)
            self.setMaximumHeight(48)
        else:
            self.setMinimumHeight(110)
            self.setMaximumHeight(16777215)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet("QFrame#DropZone { border-color: #818cf8; background-color: #1f2537; }")

    def dragLeaveEvent(self, event):
        self.setStyleSheet("")

    def dropEvent(self, event):
        self.setStyleSheet("")
        urls = event.mimeData().urls()
        all_paths: List[Path] = []

        for url in urls:
            local_path = Path(url.toLocalFile())
            if local_path.exists():
                all_paths.extend(collect_convertible_files(local_path, recursive=True))

        if all_paths:
            self.files_added.emit(all_paths)
        event.acceptProposedAction()

    def _browse_files(self):
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
            paths = [Path(f) for f in files]
            self.files_added.emit(paths)

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder Containing Files")
        if folder:
            paths = collect_convertible_files(Path(folder), recursive=True)
            if paths:
                self.files_added.emit(paths)


class ImagePreviewWidget(QFrame):
    """Displays preview thumbnail and file metadata for images, PDFs, Word, and spreadsheets."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CardFrame")
        self.setMinimumWidth(260)
        self.setMaximumWidth(360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        title = QLabel("FILE PREVIEW")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        # Image canvas / preview area
        self.preview_lbl = QLabel()
        self.preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_lbl.setMinimumHeight(200)
        self.preview_lbl.setStyleSheet(
            "background-color: #12141c; border-radius: 8px; border: 1px solid #232734; padding: 10px; color: #94a3b8;"
        )
        self.preview_lbl.setWordWrap(True)
        self.preview_lbl.setText("Select a file to preview")
        layout.addWidget(self.preview_lbl)

        # Metadata info box
        self.info_frame = QFrame()
        self.info_frame.setStyleSheet("background-color: #161922; border-radius: 6px; padding: 8px;")
        info_layout = QGridLayout(self.info_frame)
        info_layout.setContentsMargins(8, 8, 8, 8)
        info_layout.setSpacing(6)

        info_layout.addWidget(QLabel("File Name:"), 0, 0)
        self.lbl_name = QLabel("-")
        self.lbl_name.setWordWrap(True)
        self.lbl_name.setStyleSheet("font-weight: 600; color: #f3f4f6;")
        info_layout.addWidget(self.lbl_name, 0, 1)

        info_layout.addWidget(QLabel("Dimensions / Count:"), 1, 0)
        self.lbl_dim = QLabel("-")
        info_layout.addWidget(self.lbl_dim, 1, 1)

        info_layout.addWidget(QLabel("Format / Type:"), 2, 0)
        self.lbl_format = QLabel("-")
        info_layout.addWidget(self.lbl_format, 2, 1)

        info_layout.addWidget(QLabel("File Size:"), 3, 0)
        self.lbl_size = QLabel("-")
        info_layout.addWidget(self.lbl_size, 3, 1)

        info_layout.addWidget(QLabel("Privacy / Meta:"), 4, 0)
        self.lbl_meta_privacy = QLabel("-")
        self.lbl_meta_privacy.setWordWrap(True)
        info_layout.addWidget(self.lbl_meta_privacy, 4, 1)

        self.current_file_path: Optional[Path] = None

        layout.addWidget(self.info_frame)

        # Quick action buttons for selected file
        action_layout = QHBoxLayout()
        action_layout.setSpacing(8)

        self.btn_open_location = QPushButton("📂 Open Location")
        self.btn_open_location.setObjectName("SecondaryButton")
        self.btn_open_location.setEnabled(False)
        self.btn_open_location.clicked.connect(self._open_file_location)

        self.btn_copy_path = QPushButton("📋 Copy Path")
        self.btn_copy_path.setObjectName("SecondaryButton")
        self.btn_copy_path.setEnabled(False)
        self.btn_copy_path.clicked.connect(self._copy_path_to_clipboard)

        action_layout.addWidget(self.btn_open_location)
        action_layout.addWidget(self.btn_copy_path)
        layout.addLayout(action_layout)

        layout.addStretch()

    def _open_file_location(self):
        if self.current_file_path and self.current_file_path.exists():
            import os
            try:
                os.startfile(str(self.current_file_path.parent))
            except Exception:
                pass

    def _copy_path_to_clipboard(self):
        if self.current_file_path:
            from PySide6.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            if clipboard:
                clipboard.setText(str(self.current_file_path))

    def set_image(self, file_path: Optional[str | Path]):
        """Load and display preview thumbnail for the given file."""
        if not file_path or not Path(file_path).is_file():
            self.clear_preview()
            return

        p = Path(file_path)
        self.current_file_path = p
        self.btn_open_location.setEnabled(True)
        self.btn_copy_path.setEnabled(True)
        ext = p.suffix.lower()
        self.lbl_name.setText(p.name)
        self.lbl_size.setText(format_bytes(p.stat().st_size) if p.exists() else "-")

        # Inspect metadata presence
        try:
            from image_converter.core.metadata_engine import get_detailed_metadata
            d_meta = get_detailed_metadata(p)
            if d_meta.get("has_metadata"):
                warn_str = f" ({d_meta['warnings'][0]})" if d_meta.get("warnings") else ""
                self.lbl_meta_privacy.setText(f"⚠️ Has metadata{warn_str}")
                self.lbl_meta_privacy.setStyleSheet("color: #fbbf24; font-weight: 500;")
            else:
                self.lbl_meta_privacy.setText("🛡️ Clean (No tracking tags)")
                self.lbl_meta_privacy.setStyleSheet("color: #34d399; font-weight: 500;")
        except Exception:
            self.lbl_meta_privacy.setText("-")
            self.lbl_meta_privacy.setStyleSheet("")

        try:
            meta = get_file_metadata(p)

            # 1. PDF Preview
            if ext == ".pdf":
                self.lbl_format.setText("PDF Document")
                self.lbl_dim.setText(f"{meta.get('page_count', 1)} page(s)")
                try:
                    doc = fitz.open(str(p))
                    if len(doc) > 0:
                        page = doc[0]
                        pix = page.get_pixmap(dpi=100)
                        qpix = fitz_pixmap_to_qpixmap(pix).scaled(
                            300, 220, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                        )
                        self.preview_lbl.setPixmap(qpix)
                    doc.close()
                except Exception:
                    self.preview_lbl.setText("📄 PDF Document\n(Preview unavailable)")

            # 2. Word (DOCX) Preview
            elif ext in (".docx", ".doc"):
                self.lbl_format.setText("Word Document (.docx)")
                self.lbl_dim.setText(f"{meta.get('word_count', 0)} words, {meta.get('paragraphs', 0)} paras")
                self.preview_lbl.setPixmap(QPixmap())
                self.preview_lbl.setText(
                    f"📘 Microsoft Word Document\n\n"
                    f"• Paragraphs: {meta.get('paragraphs', 0)}\n"
                    f"• Tables: {meta.get('tables', 0)}\n"
                    f"• Words: ~{meta.get('word_count', 0)}"
                )

            # 3. CSV Preview
            elif ext == ".csv":
                self.lbl_format.setText("CSV Spreadsheet")
                self.lbl_dim.setText(f"{meta.get('rows', 0)} rows × {meta.get('cols', 0)} cols")
                cols_preview = ", ".join(meta.get("columns", [])[:5])
                self.preview_lbl.setPixmap(QPixmap())
                self.preview_lbl.setText(
                    f"📝 CSV Tabular Data\n\n"
                    f"• Rows: {meta.get('rows', 0)}\n"
                    f"• Columns: {meta.get('cols', 0)}\n"
                    f"• Headers: {cols_preview}"
                )

            # 4. Excel Preview
            elif ext in (".xlsx", ".xls"):
                self.lbl_format.setText("Excel Spreadsheet (.xlsx)")
                self.lbl_dim.setText(f"{meta.get('rows', 0)} rows × {meta.get('cols', 0)} cols")
                sheets_preview = ", ".join(meta.get("sheets", [])[:4])
                self.preview_lbl.setPixmap(QPixmap())
                self.preview_lbl.setText(
                    f"📊 Excel Workbook\n\n"
                    f"• Sheets: {sheets_preview}\n"
                    f"• Rows: {meta.get('rows', 0)}\n"
                    f"• Columns: {meta.get('cols', 0)}"
                )

            # 5. PowerPoint Presentation Preview
            elif ext == ".pptx":
                self.lbl_format.setText("PowerPoint Presentation (.pptx)")
                self.lbl_dim.setText(f"{meta.get('slide_count', 0)} slides")
                self.preview_lbl.setPixmap(QPixmap())
                self.preview_lbl.setText(
                    f"📽️ PowerPoint Presentation\n\n"
                    f"• Title: {meta.get('title', p.stem)}\n"
                    f"• Slides: {meta.get('slide_count', 0)}"
                )

            # 6. OpenDocument Text Preview
            elif ext == ".odt":
                self.lbl_format.setText("OpenDocument Text (.odt)")
                self.lbl_dim.setText(f"{meta.get('word_count', 0)} words, {meta.get('paragraphs', 0)} paras")
                self.preview_lbl.setPixmap(QPixmap())
                self.preview_lbl.setText(
                    f"📄 OpenDocument Text\n\n"
                    f"• Paragraphs: {meta.get('paragraphs', 0)}\n"
                    f"• Words: ~{meta.get('word_count', 0)}"
                )

            # 7. Rich Text Format Preview
            elif ext == ".rtf":
                self.lbl_format.setText("Rich Text Format (.rtf)")
                self.lbl_dim.setText(f"{meta.get('word_count', 0)} words, {meta.get('line_count', 0)} lines")
                self.preview_lbl.setPixmap(QPixmap())
                self.preview_lbl.setText(
                    f"📝 Rich Text Format\n\n"
                    f"• Lines: {meta.get('line_count', 0)}\n"
                    f"• Words: ~{meta.get('word_count', 0)}"
                )

            # 8. Plain Text Document Preview
            elif ext == ".txt":
                self.lbl_format.setText("Plain Text (.txt)")
                self.lbl_dim.setText(f"{meta.get('words', 0)} words, {meta.get('lines', 0)} lines")
                self.preview_lbl.setPixmap(QPixmap())
                self.preview_lbl.setText(
                    f"📄 Plain Text Document\n\n"
                    f"• Lines: {meta.get('lines', 0)}\n"
                    f"• Words: ~{meta.get('words', 0)}"
                )

            # 9. Standard Image Preview
            else:
                self.lbl_dim.setText(f"{meta['width']} × {meta['height']} px")
                alpha_str = " (Alpha)" if meta.get("has_alpha") else ""
                self.lbl_format.setText(f"{meta['format']} / {meta.get('mode', '')}{alpha_str}")

                with Image.open(p) as img:
                    img.thumbnail((300, 220), Image.Resampling.BILINEAR)
                    pixmap = pil_to_qpixmap(img)
                    self.preview_lbl.setPixmap(pixmap)

        except Exception as e:
            self.preview_lbl.setText(f"Preview unavailable:\n{str(e)[:60]}")
            self.lbl_dim.setText("-")
            self.lbl_format.setText(ext.lstrip(".").upper())

    def clear_preview(self):
        self.current_file_path = None
        self.btn_open_location.setEnabled(False)
        self.btn_copy_path.setEnabled(False)
        self.preview_lbl.setPixmap(QPixmap())
        self.preview_lbl.setText("Select a file to preview")
        self.lbl_name.setText("-")
        self.lbl_dim.setText("-")
        self.lbl_format.setText("-")
        self.lbl_size.setText("-")
        if hasattr(self, "lbl_meta_privacy"):
            self.lbl_meta_privacy.setText("-")
            self.lbl_meta_privacy.setStyleSheet("")


FilePreviewWidget = ImagePreviewWidget


class ConversionSettingsWidget(QFrame):
    """Controls for output format, quality, resizing, DPI, sheet, and destination."""

    settings_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CardFrame")
        self.setMinimumWidth(300)
        self.setMaximumWidth(520)

        self.bg_color_rgb = (255, 255, 255)  # default white

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel("CONVERSION SETTINGS")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        # Tab Widget for organized settings
        self.tabs = QTabWidget()
        self.tabs.setUsesScrollButtons(False)
        self.tabs.tabBar().setExpanding(True)
        tab_output = QWidget()
        out_tab_layout = QVBoxLayout(tab_output)
        out_tab_layout.setContentsMargins(8, 12, 8, 8)
        out_tab_layout.setSpacing(10)

        # Target Format
        fmt_layout = QHBoxLayout()
        fmt_lbl = QLabel("Target Format:")
        fmt_lbl.setStyleSheet("font-weight: 600;")
        self.combo_format = QComboBox()
        self.combo_format.addItems(get_supported_output_formats())
        self.combo_format.currentTextChanged.connect(self._on_format_changed)
        fmt_layout.addWidget(fmt_lbl)
        fmt_layout.addWidget(self.combo_format)
        out_tab_layout.addLayout(fmt_layout)

        # Quality Slider (for lossy image formats)
        self.quality_group = QFrame()
        q_layout = QVBoxLayout(self.quality_group)
        q_layout.setContentsMargins(0, 4, 0, 4)
        q_layout.setSpacing(4)

        q_head = QHBoxLayout()
        q_label = QLabel("Quality / Compression:")
        self.lbl_quality_val = QLabel("90%")
        self.lbl_quality_val.setStyleSheet("font-weight: 600; color: #a5b4fc;")
        q_head.addWidget(q_label)
        q_head.addStretch()
        q_head.addWidget(self.lbl_quality_val)

        self.slider_quality = QSlider(Qt.Orientation.Horizontal)
        self.slider_quality.setRange(1, 100)
        self.slider_quality.setValue(90)
        self.slider_quality.valueChanged.connect(self._on_quality_slider_changed)

        self.chk_lossless = QCheckBox("Lossless (WEBP)")
        self.chk_lossless.setVisible(False)
        self.chk_lossless.toggled.connect(self.settings_changed)

        q_layout.addLayout(q_head)
        q_layout.addWidget(self.slider_quality)
        q_layout.addWidget(self.chk_lossless)
        out_tab_layout.addWidget(self.quality_group)

        # Output Folder Selection
        out_box = QGroupBox("Destination Directory")
        out_layout = QVBoxLayout(out_box)
        out_layout.setSpacing(6)

        self.radio_same_dir = QRadioButton("Same folder as original")
        self.radio_same_dir.setChecked(True)
        self.radio_custom_dir = QRadioButton("Custom folder:")

        self.btn_group_dest = QButtonGroup(self)
        self.btn_group_dest.addButton(self.radio_same_dir)
        self.btn_group_dest.addButton(self.radio_custom_dir)
        self.btn_group_dest.buttonClicked.connect(self._on_dest_radio_changed)

        dir_picker_layout = QHBoxLayout()
        self.line_out_dir = QLineEdit()
        self.line_out_dir.setPlaceholderText("Select output folder...")
        self.line_out_dir.setEnabled(False)

        self.btn_browse_dest = QPushButton("Browse...")
        self.btn_browse_dest.setEnabled(False)
        self.btn_browse_dest.clicked.connect(self._browse_custom_dest)

        dir_picker_layout.addWidget(self.line_out_dir)
        dir_picker_layout.addWidget(self.btn_browse_dest)

        out_layout.addWidget(self.radio_same_dir)
        out_layout.addWidget(self.radio_custom_dir)
        out_layout.addLayout(dir_picker_layout)

        out_tab_layout.addWidget(out_box)
        out_tab_layout.addStretch()
        self.tabs.addTab(tab_output, "General")

        # --- Tab 2: Dimensions & Image Transform ---
        tab_transform = QWidget()
        tr_tab_layout = QVBoxLayout(tab_transform)
        tr_tab_layout.setContentsMargins(8, 12, 8, 8)
        tr_tab_layout.setSpacing(10)

        # Resizing Group (images)
        self.resize_box = QGroupBox("Resize / Scale (Images)")
        r_layout = QVBoxLayout(self.resize_box)
        r_layout.setSpacing(8)

        self.combo_resize_mode = QComboBox()
        self.combo_resize_mode.addItems([
            "Original Size (100%)",
            "Percentage Scale",
            "Custom Dimensions (W × H)",
            "Fit within Max Bounds",
        ])
        self.combo_resize_mode.currentIndexChanged.connect(self._on_resize_mode_changed)
        r_layout.addWidget(self.combo_resize_mode)

        # Percentage spinbox
        self.frame_percent = QFrame()
        pct_layout = QHBoxLayout(self.frame_percent)
        pct_layout.setContentsMargins(0, 0, 0, 0)
        pct_layout.addWidget(QLabel("Scale Percentage:"))
        self.spin_percent = QSpinBox()
        self.spin_percent.setRange(5, 500)
        self.spin_percent.setValue(50)
        self.spin_percent.setSuffix(" %")
        pct_layout.addWidget(self.spin_percent)
        self.frame_percent.setVisible(False)
        r_layout.addWidget(self.frame_percent)

        # Custom dimensions frame
        self.frame_custom_dim = QFrame()
        cd_layout = QGridLayout(self.frame_custom_dim)
        cd_layout.setContentsMargins(0, 0, 0, 0)
        cd_layout.setSpacing(6)

        cd_layout.addWidget(QLabel("Width:"), 0, 0)
        self.spin_width = QSpinBox()
        self.spin_width.setRange(1, 10000)
        self.spin_width.setValue(1920)
        self.spin_width.setSuffix(" px")
        cd_layout.addWidget(self.spin_width, 0, 1)

        cd_layout.addWidget(QLabel("Height:"), 1, 0)
        self.spin_height = QSpinBox()
        self.spin_height.setRange(1, 10000)
        self.spin_height.setValue(1080)
        self.spin_height.setSuffix(" px")
        cd_layout.addWidget(self.spin_height, 1, 1)

        self.chk_aspect_ratio = QCheckBox("Keep Aspect Ratio")
        self.chk_aspect_ratio.setChecked(True)
        cd_layout.addWidget(self.chk_aspect_ratio, 2, 0, 1, 2)

        self.frame_custom_dim.setVisible(False)
        r_layout.addWidget(self.frame_custom_dim)
        tr_tab_layout.addWidget(self.resize_box)

        # DPI option (for rendering PDF / DOCX to images)
        self.frame_dpi = QFrame()
        dpi_layout = QHBoxLayout(self.frame_dpi)
        dpi_layout.setContentsMargins(0, 0, 0, 0)
        dpi_layout.addWidget(QLabel("Render DPI:"))
        self.spin_dpi = QSpinBox()
        self.spin_dpi.setRange(50, 600)
        self.spin_dpi.setValue(150)
        self.spin_dpi.setSuffix(" DPI")
        self.spin_dpi.valueChanged.connect(self.settings_changed)
        dpi_layout.addWidget(self.spin_dpi)
        tr_tab_layout.addWidget(self.frame_dpi)

        # Transparency background color
        self.frame_bg = QFrame()
        bg_box = QHBoxLayout(self.frame_bg)
        bg_box.setContentsMargins(0, 0, 0, 0)
        bg_box.addWidget(QLabel("Alpha Background:"))
        self.btn_color = QPushButton("■ Color")
        self.btn_color.setStyleSheet("color: white; font-weight: bold; background-color: #374151;")
        self.btn_color.clicked.connect(self._pick_bg_color)
        bg_box.addWidget(self.btn_color)
        tr_tab_layout.addWidget(self.frame_bg)

        tr_tab_layout.addStretch()
        self.tabs.addTab(tab_transform, "Transform")

        # --- Tab 3: Documents & Security ---
        tab_docs = QWidget()
        doc_tab_layout = QVBoxLayout(tab_docs)
        doc_tab_layout.setContentsMargins(8, 12, 8, 8)
        doc_tab_layout.setSpacing(10)

        # Excel sheet name option
        self.frame_sheet = QFrame()
        sheet_layout = QHBoxLayout(self.frame_sheet)
        sheet_layout.setContentsMargins(0, 0, 0, 0)
        sheet_layout.addWidget(QLabel("Sheet Name:"))
        self.line_sheet = QLineEdit()
        self.line_sheet.setPlaceholderText("First / Active sheet")
        self.line_sheet.textChanged.connect(self.settings_changed)
        sheet_layout.addWidget(self.line_sheet)
        doc_tab_layout.addWidget(self.frame_sheet)

        # OCR Group
        doc_sec_box = QGroupBox("Document OCR & Decryption")
        doc_sec_layout = QVBoxLayout(doc_sec_box)
        doc_sec_layout.setSpacing(8)

        self.chk_enable_ocr = QCheckBox("Enable OCR Text Fallback")
        self.chk_enable_ocr.setToolTip("Use OCR fallback when converting scanned PDFs or images to text/DOCX")
        self.chk_enable_ocr.toggled.connect(self.settings_changed)
        doc_sec_layout.addWidget(self.chk_enable_ocr)

        pwd_layout = QHBoxLayout()
        pwd_layout.addWidget(QLabel("Password:"))
        self.line_password = QLineEdit()
        self.line_password.setPlaceholderText("Encrypted PDF / Word...")
        self.line_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.line_password.textChanged.connect(self.settings_changed)
        pwd_layout.addWidget(self.line_password)
        doc_sec_layout.addLayout(pwd_layout)

        doc_tab_layout.addWidget(doc_sec_box)
        doc_tab_layout.addStretch()
        self.tabs.addTab(tab_docs, "Doc & OCR")

        # --- Tab 4: Privacy & Metadata ---
        tab_privacy = QWidget()
        priv_tab_layout = QVBoxLayout(tab_privacy)
        priv_tab_layout.setContentsMargins(8, 12, 8, 8)
        priv_tab_layout.setSpacing(10)

        meta_box = QGroupBox("Metadata Cleaning & Sanitization")
        meta_layout = QVBoxLayout(meta_box)
        meta_layout.setSpacing(8)

        self.chk_strip_metadata = QCheckBox("🗑️ Strip all metadata (Privacy mode)")
        self.chk_strip_metadata.setToolTip(
            "Strip all personal identifiable information, author properties, "
            "camera/device tags, GPS coordinates, and timestamps across all formats."
        )
        self.chk_strip_metadata.setChecked(False)
        self.chk_strip_metadata.toggled.connect(self._on_strip_metadata_toggled)

        self.chk_preserve_exif = QCheckBox("Preserve EXIF Metadata (Images)")
        self.chk_preserve_exif.setChecked(True)
        self.chk_preserve_exif.toggled.connect(self.settings_changed)

        self.chk_auto_orient = QCheckBox("Auto-orient Photos (EXIF)")
        self.chk_auto_orient.setChecked(True)
        self.chk_auto_orient.toggled.connect(self.settings_changed)

        meta_layout.addWidget(self.chk_strip_metadata)
        meta_layout.addWidget(self.chk_preserve_exif)
        meta_layout.addWidget(self.chk_auto_orient)
        priv_tab_layout.addWidget(meta_box)

        lbl_priv_help = QLabel(
            "💡 Privacy Mode removes author info, revision history, and GPS tags from output files."
        )
        lbl_priv_help.setObjectName("MutedLabel")
        lbl_priv_help.setWordWrap(True)
        priv_tab_layout.addWidget(lbl_priv_help)
        priv_tab_layout.addStretch()
        self.tabs.addTab(tab_privacy, "Privacy")

        layout.addWidget(self.tabs)

        self._on_format_changed(self.combo_format.currentText())

    def _on_format_changed(self, fmt: str):
        fmt = fmt.upper()
        # Quality slider is applicable for JPG, WEBP, HEIC
        supports_quality = fmt in ("JPG", "JPEG", "WEBP", "HEIC", "HEIF")
        self.quality_group.setVisible(supports_quality)
        self.chk_lossless.setVisible(fmt == "WEBP")

        # Background color applies when alpha is flattened (JPG, BMP)
        self.frame_bg.setVisible(fmt in ("JPG", "JPEG", "BMP"))

        # Resize applies to image formats
        is_image_output = fmt in ("JPG", "PNG", "WEBP", "HEIC", "BMP", "TIFF", "GIF", "ICO")
        self.resize_box.setVisible(is_image_output)

        # DPI applicable when exporting to images or PDF
        self.frame_dpi.setVisible(is_image_output or fmt == "PDF")

        # Sheet name applicable for Excel conversions
        self.frame_sheet.setVisible(fmt in ("CSV", "XLSX", "PDF", "JSON", "HTML"))

        self.settings_changed.emit()

    def _on_quality_slider_changed(self, val: int):
        self.lbl_quality_val.setText(f"{val}%")
        self.settings_changed.emit()

    def _on_resize_mode_changed(self, idx: int):
        self.frame_percent.setVisible(idx == 1)
        self.frame_custom_dim.setVisible(idx in (2, 3))
        self.settings_changed.emit()

    def _pick_bg_color(self):
        color = QColorDialog.getColor(QColor(*self.bg_color_rgb), self, "Select Alpha Background Color")
        if color.isValid():
            self.bg_color_rgb = (color.red(), color.green(), color.blue())
            hex_col = color.name()
            self.btn_color.setStyleSheet(f"background-color: {hex_col}; color: {'black' if color.lightness() > 128 else 'white'};")

    def _on_dest_radio_changed(self):
        custom = self.radio_custom_dir.isChecked()
        self.line_out_dir.setEnabled(custom)
        self.btn_browse_dest.setEnabled(custom)

    def _browse_custom_dest(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Destination")
        if folder:
            self.line_out_dir.setText(folder)

    def get_target_format(self) -> str:
        return self.combo_format.currentText().upper()

    def get_output_directory(self) -> Optional[Path]:
        if self.radio_custom_dir.isChecked():
            txt = self.line_out_dir.text().strip()
            if txt:
                return Path(txt)
        return None

    def _on_strip_metadata_toggled(self, checked: bool):
        if checked:
            self.chk_preserve_exif.setEnabled(False)
            self.chk_preserve_exif.setChecked(False)
        else:
            self.chk_preserve_exif.setEnabled(True)
            self.chk_preserve_exif.setChecked(True)
        self.settings_changed.emit()

    def get_config(self) -> ConversionConfig:
        fmt = self.get_target_format()
        resize_idx = self.combo_resize_mode.currentIndex()

        resize_mode = "none"
        if resize_idx == 1:
            resize_mode = "percentage"
        elif resize_idx == 2:
            resize_mode = "custom"
        elif resize_idx == 3:
            resize_mode = "fit_box"

        sheet_txt = self.line_sheet.text().strip()
        sheet_val = sheet_txt if sheet_txt else None
        pwd_txt = self.line_password.text().strip()
        pwd_val = pwd_txt if pwd_txt else None
        strip_meta = self.chk_strip_metadata.isChecked()

        return ConversionConfig(
            target_format=fmt,
            quality=self.slider_quality.value(),
            lossless=self.chk_lossless.isChecked() if fmt == "WEBP" else False,
            preserve_metadata=not strip_meta and self.chk_preserve_exif.isChecked(),
            strip_metadata=strip_meta,
            auto_orient=self.chk_auto_orient.isChecked(),
            resize_mode=resize_mode,
            resize_percent=float(self.spin_percent.value()),
            custom_width=self.spin_width.value() if resize_idx in (2, 3) else None,
            custom_height=self.spin_height.value() if resize_idx in (2, 3) else None,
            keep_aspect_ratio=self.chk_aspect_ratio.isChecked(),
            background_color=self.bg_color_rgb,
            dpi=self.spin_dpi.value(),
            sheet_name=sheet_val,
            password=pwd_val,
            enable_ocr=self.chk_enable_ocr.isChecked(),
        )


class QueueTableWidget(QTableWidget):
    """Table showing batch queue items and conversion states."""

    item_selected = Signal(str)  # filepath of selected row
    item_removed = Signal(int)   # row index

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(8)
        self.setHorizontalHeaderLabels([
            "Status",
            "Preview",
            "File Name",
            "Input",
            "Target",
            "Details",
            "Original Size",
            "Converted Size",
        ])
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        self.setColumnWidth(4, 110)

        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.verticalHeader().setDefaultSectionSize(52)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(False)
        self.setAlternatingRowColors(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        self.file_paths: List[Path] = []
        self.itemSelectionChanged.connect(self._on_selection_changed)

    def _show_context_menu(self, pos: QPoint):
        row = self.rowAt(pos.y())
        if row < 0 or row >= len(self.file_paths):
            return

        file_p = self.file_paths[row]
        menu = QMenu(self)
        
        act_open_loc = menu.addAction("📂 Open File Location")
        act_copy_path = menu.addAction("📋 Copy Full Path")
        act_inspect_meta = menu.addAction("🔍 Inspect Metadata")
        menu.addSeparator()
        act_remove = menu.addAction("🗑️ Remove from Queue")

        chosen = menu.exec(self.viewport().mapToGlobal(pos))
        if chosen == act_open_loc:
            import os
            try:
                os.startfile(str(file_p.parent))
            except Exception:
                pass
        elif chosen == act_copy_path:
            from PySide6.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            if clipboard:
                clipboard.setText(str(file_p))
        elif chosen == act_inspect_meta:
            self.selectRow(row)
            self.item_selected.emit(str(file_p))
        elif chosen == act_remove:
            self.selectRow(row)
            self.remove_selected_row()

    def _on_selection_changed(self):
        row = self.currentRow()
        if 0 <= row < len(self.file_paths):
            self.item_selected.emit(str(self.file_paths[row]))

    def add_image_item(self, file_path: Path, target_fmt: str):
        """Add a file to the conversion queue."""
        row = self.rowCount()
        self.insertRow(row)
        self.file_paths.append(file_path)

        ext = file_path.suffix.lower()

        # 0. Status
        status_item = QTableWidgetItem("⏳ Pending")
        status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        status_item.setForeground(QColor("#9ca3af"))
        self.setItem(row, 0, status_item)

        # 1. Thumbnail
        thumb_label = QLabel()
        thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb_label.setFixedSize(40, 40)

        # 5. Details
        dim_item = QTableWidgetItem("-")
        dim_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        try:
            if ext == ".pdf":
                doc = fitz.open(str(file_path))
                if len(doc) > 0:
                    pix = doc[0].get_pixmap(dpi=36)
                    qpix = fitz_pixmap_to_qpixmap(pix).scaled(
                        36, 36, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                    )
                    thumb_label.setPixmap(qpix)
                    dim_item.setText(f"{len(doc)} pgs")
                else:
                    thumb_label.setText("📄")
                    dim_item.setText("0 pgs")
                doc.close()

            elif ext in (".docx", ".doc"):
                thumb_label.setText("📘")
                thumb_label.setStyleSheet("font-size: 20px;")
                dim_item.setText("DOCX")

            elif ext == ".csv":
                thumb_label.setText("📝")
                thumb_label.setStyleSheet("font-size: 20px;")
                dim_item.setText("CSV")

            elif ext in (".xlsx", ".xls"):
                thumb_label.setText("📊")
                thumb_label.setStyleSheet("font-size: 20px;")
                dim_item.setText("Excel")

            else:
                with Image.open(file_path) as img:
                    img.thumbnail((36, 36), Image.Resampling.NEAREST)
                    thumb_label.setPixmap(pil_to_qpixmap(img))
                    dim_item.setText(f"{img.width}×{img.height}")
        except Exception:
            thumb_label.setText("📄")

        self.setCellWidget(row, 1, thumb_label)
        self.setItem(row, 5, dim_item)

        # 2. Name
        name_item = QTableWidgetItem(file_path.name)
        name_item.setToolTip(str(file_path))
        self.setItem(row, 2, name_item)

        # 3. Input format
        in_fmt = file_path.suffix.lstrip(".").upper()
        in_item = QTableWidgetItem(in_fmt)
        in_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(row, 3, in_item)

        # 4. Target format ComboBox
        combo_target = QComboBox()
        combo_target.setObjectName("TableComboBox")
        compat_formats = get_compatible_output_formats(file_path)
        combo_target.addItems(compat_formats)

        target_fmt_upper = target_fmt.upper()
        if target_fmt_upper in compat_formats:
            combo_target.setCurrentText(target_fmt_upper)
        elif compat_formats:
            combo_target.setCurrentIndex(0)

        # Fallback table item behind widget for sorting / text access
        target_item = QTableWidgetItem(combo_target.currentText())
        target_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(row, 4, target_item)

        combo_target.currentTextChanged.connect(
            lambda text, r_idx=row: self._on_row_target_changed(r_idx, text)
        )
        self.setCellWidget(row, 4, combo_target)

        # 6. Original Size
        size_bytes = file_path.stat().st_size if file_path.exists() else 0
        size_item = QTableWidgetItem(format_bytes(size_bytes))
        size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.setItem(row, 6, size_item)

        # 7. Converted Size
        out_size_item = QTableWidgetItem("-")
        out_size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.setItem(row, 7, out_size_item)

    add_file_item = add_image_item

    def _on_row_target_changed(self, row: int, new_target: str):
        """Keep underlying QTableWidgetItem synchronized with combobox selection."""
        item = self.item(row, 4)
        if item:
            item.setText(new_target)

    def get_target_format_for_row(self, row: int) -> str:
        """Get selected target format for a specific table row."""
        widget = self.cellWidget(row, 4)
        if isinstance(widget, QComboBox):
            return widget.currentText().upper()
        item = self.item(row, 4)
        return item.text().upper() if item else "JPG"

    def set_target_format_for_row(self, row: int, target_fmt: str):
        """Set target format for a specific table row."""
        widget = self.cellWidget(row, 4)
        target_fmt_upper = target_fmt.upper()
        if isinstance(widget, QComboBox):
            idx = widget.findText(target_fmt_upper)
            if idx >= 0:
                widget.setCurrentIndex(idx)
        item = self.item(row, 4)
        if item:
            item.setText(target_fmt_upper)

    def set_target_format_all(self, target_fmt: str):
        """Update target format for all compatible rows."""
        target_fmt_upper = target_fmt.upper()
        for row in range(self.rowCount()):
            widget = self.cellWidget(row, 4)
            if isinstance(widget, QComboBox):
                idx = widget.findText(target_fmt_upper)
                if idx >= 0:
                    widget.setCurrentIndex(idx)
            item = self.item(row, 4)
            if item:
                if isinstance(widget, QComboBox):
                    item.setText(widget.currentText())
                else:
                    item.setText(target_fmt_upper)

    def update_status(self, row: int, status: str, color_hex: str = "#f3f4f6"):
        item = self.item(row, 0)
        if item:
            item.setText(status)
            item.setForeground(QColor(color_hex))

    def update_converted_size(self, row: int, size_bytes: int):
        item = self.item(row, 7)
        if item:
            item.setText(format_bytes(size_bytes))
            item.setForeground(QColor("#34d399"))

    def clear_all(self):
        self.setRowCount(0)
        self.file_paths.clear()

    def remove_selected_row(self):
        row = self.currentRow()
        if 0 <= row < len(self.file_paths):
            self.removeRow(row)
            self.file_paths.pop(row)
            self.item_removed.emit(row)
