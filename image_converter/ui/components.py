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
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from image_converter.cli import collect_convertible_files
from image_converter.core.engine import (
    ConversionConfig,
    FORMAT_EXTENSIONS,
    get_file_metadata,
    get_image_metadata,
    get_supported_output_formats,
)


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
    """Interactive drag and drop landing box for files and folders."""

    files_added = Signal(list)  # list of Path objects

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(140)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)

        self.title_lbl = QLabel("📁 Drag & Drop Files or Folders Here")
        self.title_lbl.setStyleSheet("font-size: 16px; font-weight: 600; color: #cbd5e1;")
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.sub_lbl = QLabel("Supports PDF, Word (.docx), Excel (.xlsx), CSV, and Images (HEIC, JPG, PNG, WEBP, & more)")
        self.sub_lbl.setObjectName("MutedLabel")
        self.sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        btn_layout = QHBoxLayout()
        btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_layout.setSpacing(12)

        self.btn_browse_files = QPushButton("Browse Files...")
        self.btn_browse_files.setObjectName("SecondaryButton")
        self.btn_browse_files.clicked.connect(self._browse_files)

        self.btn_browse_folder = QPushButton("Browse Folder...")
        self.btn_browse_folder.setObjectName("SecondaryButton")
        self.btn_browse_folder.clicked.connect(self._browse_folder)

        btn_layout.addWidget(self.btn_browse_files)
        btn_layout.addWidget(self.btn_browse_folder)

        layout.addWidget(self.title_lbl)
        layout.addWidget(self.sub_lbl)
        layout.addLayout(btn_layout)

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
            "All Supported Files (*.jpg *.jpeg *.png *.heic *.heif *.webp *.bmp *.tiff *.tif *.gif *.ico *.pdf *.docx *.csv *.xlsx);;"
            "Documents (*.pdf *.docx);;"
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

        layout.addWidget(self.info_frame)
        layout.addStretch()

    def set_image(self, file_path: Optional[str | Path]):
        """Load and display preview thumbnail for the given file."""
        if not file_path or not Path(file_path).is_file():
            self.clear_preview()
            return

        p = Path(file_path)
        ext = p.suffix.lower()
        self.lbl_name.setText(p.name)
        self.lbl_size.setText(format_bytes(p.stat().st_size) if p.exists() else "-")

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

            # 5. Standard Image Preview
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
        self.preview_lbl.setPixmap(QPixmap())
        self.preview_lbl.setText("Select a file to preview")
        self.lbl_name.setText("-")
        self.lbl_dim.setText("-")
        self.lbl_format.setText("-")
        self.lbl_size.setText("-")


FilePreviewWidget = ImagePreviewWidget


class ConversionSettingsWidget(QFrame):
    """Controls for output format, quality, resizing, DPI, sheet, and destination."""

    settings_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CardFrame")
        self.setMinimumWidth(260)
        self.setMaximumWidth(360)

        self.bg_color_rgb = (255, 255, 255)  # default white

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel("CONVERSION SETTINGS")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        # Target Format
        fmt_layout = QHBoxLayout()
        fmt_lbl = QLabel("Target Format:")
        fmt_lbl.setStyleSheet("font-weight: 600;")
        self.combo_format = QComboBox()
        self.combo_format.addItems(get_supported_output_formats())
        self.combo_format.currentTextChanged.connect(self._on_format_changed)
        fmt_layout.addWidget(fmt_lbl)
        fmt_layout.addWidget(self.combo_format)
        layout.addLayout(fmt_layout)

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
        layout.addWidget(self.frame_dpi)

        # Excel sheet name option
        self.frame_sheet = QFrame()
        sheet_layout = QHBoxLayout(self.frame_sheet)
        sheet_layout.setContentsMargins(0, 0, 0, 0)
        sheet_layout.addWidget(QLabel("Sheet Name:"))
        self.line_sheet = QLineEdit()
        self.line_sheet.setPlaceholderText("First / Active sheet")
        self.line_sheet.textChanged.connect(self.settings_changed)
        sheet_layout.addWidget(self.line_sheet)
        layout.addWidget(self.frame_sheet)

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
        layout.addWidget(self.quality_group)

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

        layout.addWidget(self.resize_box)

        # Transparency background color
        self.frame_bg = QFrame()
        bg_box = QHBoxLayout(self.frame_bg)
        bg_box.setContentsMargins(0, 0, 0, 0)
        bg_box.addWidget(QLabel("Alpha Background:"))
        self.btn_color = QPushButton("■ Color")
        self.btn_color.setStyleSheet("color: white; font-weight: bold; background-color: #374151;")
        self.btn_color.clicked.connect(self._pick_bg_color)
        bg_box.addWidget(self.btn_color)
        layout.addWidget(self.frame_bg)

        # Metadata options
        self.chk_preserve_exif = QCheckBox("Preserve EXIF Metadata")
        self.chk_preserve_exif.setChecked(True)
        self.chk_auto_orient = QCheckBox("Auto-orient Photos (EXIF)")
        self.chk_auto_orient.setChecked(True)

        layout.addWidget(self.chk_preserve_exif)
        layout.addWidget(self.chk_auto_orient)

        # Output Folder Selection
        out_box = QGroupBox("Destination")
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

        layout.addWidget(out_box)
        layout.addStretch()

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

        return ConversionConfig(
            target_format=fmt,
            quality=self.slider_quality.value(),
            lossless=self.chk_lossless.isChecked() if fmt == "WEBP" else False,
            preserve_metadata=self.chk_preserve_exif.isChecked(),
            auto_orient=self.chk_auto_orient.isChecked(),
            resize_mode=resize_mode,
            resize_percent=float(self.spin_percent.value()),
            custom_width=self.spin_width.value() if resize_idx in (2, 3) else None,
            custom_height=self.spin_height.value() if resize_idx in (2, 3) else None,
            keep_aspect_ratio=self.chk_aspect_ratio.isChecked(),
            background_color=self.bg_color_rgb,
            dpi=self.spin_dpi.value(),
            sheet_name=sheet_val,
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
        self.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)

        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.verticalHeader().setDefaultSectionSize(48)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(False)
        self.setAlternatingRowColors(True)

        self.file_paths: List[Path] = []
        self.itemSelectionChanged.connect(self._on_selection_changed)

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

        # 4. Target format
        target_item = QTableWidgetItem(target_fmt)
        target_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        target_item.setForeground(QColor("#818cf8"))
        self.setItem(row, 4, target_item)

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

    def set_target_format_all(self, target_fmt: str):
        """Update target format column for all rows."""
        for row in range(self.rowCount()):
            item = self.item(row, 4)
            if item:
                item.setText(target_fmt)

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
