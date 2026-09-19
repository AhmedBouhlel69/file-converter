"""
PDF Toolkit UI Components
Provides:
1. ToolCardWidget & ToolkitDashboardWidget: Categorized browser for all 26 tools.
2. PDFViewerWidget: PyMuPDF document previewer with zoom, page navigation, and scaling.
3. SignatureCanvasWidget: Freehand signature drawing, cursive text typing, and image upload.
4. ToolWorkspaceWidget: Complete 5-step operational workflow for all tools.
"""

from __future__ import annotations

import dataclasses
import io
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

import fitz  # PyMuPDF
from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice, QPoint, QRect, QSize, Qt, Signal, QThread
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
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
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# Lazy import — engine functions are only loaded when _execute_tool runs
def _get_toolkit_functions():
    """Import all toolkit functions lazily (called only when a tool is executed)."""
    import image_converter.core.pdf_toolkit_engine as _tk
    return _tk

from image_converter.ui.components import format_bytes


# ===========================================================================
# 1. TOOL REGISTRY & METADATA
# ===========================================================================

@dataclasses.dataclass
class ToolDefinition:
    id: str
    name: str
    category: str
    icon: str
    description: str
    accepted_exts: List[str]
    allow_multiple: bool = False
    badge: str = ""


ALL_TOOLS: List[ToolDefinition] = [
    # 1. Organize
    ToolDefinition("merge_pdf", "Merge PDF", "Organize", "📑", "Combine multiple PDF documents into a single file with custom ordering.", [".pdf"], allow_multiple=True),
    ToolDefinition("split_pdf", "Split PDF", "Organize", "✂️", "Split a PDF by page ranges, every N pages, or into individual files.", [".pdf"]),
    ToolDefinition("remove_pages", "Remove Pages", "Organize", "🗑️", "Select and permanently delete unwanted pages from a PDF document.", [".pdf"]),
    ToolDefinition("extract_pages", "Extract Pages", "Organize", "📤", "Extract specific pages or page ranges into a brand new PDF.", [".pdf"]),
    ToolDefinition("organize_pages", "Organize Pages", "Organize", "🔀", "Reorder, duplicate, rotate, or delete pages in a PDF document.", [".pdf"]),
    ToolDefinition("scan_to_pdf", "Scan to PDF", "Organize", "📷", "Convert scanned images or photos into a unified, formatted PDF.", [".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"], allow_multiple=True),
    ToolDefinition("rotate_pdf", "Rotate PDF", "Organize", "🔄", "Rotate all, odd, even, or custom pages by 90°, 180°, or 270°.", [".pdf"]),

    # 2. Optimize
    ToolDefinition("compress_pdf", "Compress PDF", "Optimize", "⚡", "Reduce file size with Low, Medium, or High compression and savings badge.", [".pdf"]),
    ToolDefinition("repair_pdf", "Repair PDF", "Optimize", "🩺", "Salvage broken, corrupted, or damaged PDFs by rebuilding xref tables.", [".pdf"]),
    ToolDefinition("ocr_pdf", "OCR PDF", "Optimize", "🔍", "Convert image-only scanned PDFs into searchable text documents.", [".pdf"]),

    # 3. Convert To PDF
    ToolDefinition("images_to_pdf", "JPG to PDF", "Convert To", "🖼️", "Convert JPG, PNG, WebP, BMP, and TIFF images into vector PDFs.", [".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"], allow_multiple=True),
    ToolDefinition("word_to_pdf", "Word to PDF", "Convert To", "📄", "Convert Microsoft Word (.docx, .doc) documents to PDF format.", [".docx", ".doc"]),
    ToolDefinition("powerpoint_to_pdf", "PowerPoint to PDF", "Convert To", "📊", "Convert Microsoft PowerPoint (.pptx) presentations to PDF slides.", [".pptx"]),
    ToolDefinition("excel_to_pdf", "Excel to PDF", "Convert To", "📈", "Convert Excel (.xlsx, .xls) and CSV spreadsheets into formatted PDF tables.", [".xlsx", ".xls", ".csv"]),
    ToolDefinition("html_to_pdf", "HTML to PDF", "Convert To", "🌐", "Convert HTML files or web pages into clean, vector-rendered PDFs.", [".html", ".htm"]),

    # 4. Convert From PDF
    ToolDefinition("pdf_to_images", "PDF to JPG / Images", "Convert From", "🌄", "Export PDF pages as JPG/PNG/WebP images or extract embedded photos.", [".pdf"]),
    ToolDefinition("pdf_to_word", "PDF to Word", "Convert From", "📝", "Convert PDF documents into editable Microsoft Word (.docx) files.", [".pdf"]),
    ToolDefinition("pdf_to_powerpoint", "PDF to PowerPoint", "Convert From", "🖥️", "Convert PDF documents into PowerPoint presentation slides.", [".pdf"]),
    ToolDefinition("pdf_to_excel", "PDF to Excel", "Convert From", "📊", "Detect and extract data tables from PDF into XLSX or CSV sheets.", [".pdf"]),
    ToolDefinition("pdf_to_pdfa", "PDF to PDF/A", "Convert From", "🏛️", "Standardize PDFs into the ISO PDF/A archival format for long-term storage.", [".pdf"]),

    # 5. Edit PDF
    ToolDefinition("edit_pdf", "Edit PDF", "Edit", "✏️", "Add custom text, image stamps, or shapes directly onto PDF pages.", [".pdf"]),
    ToolDefinition("add_page_numbers", "Add Page Numbers", "Edit", "🔢", "Insert customized page numbering in headers or footers.", [".pdf"]),
    ToolDefinition("add_watermark", "Add Watermark", "Edit", "💧", "Add text or image watermarks with custom opacity, angle, and position.", [".pdf"]),
    ToolDefinition("crop_pdf", "Crop PDF", "Edit", "📐", "Trim margins or adjust visible bounding box across pages.", [".pdf"]),
    ToolDefinition("pdf_forms", "PDF Forms", "Edit", "📋", "Inspect interactive form fields, fill values, add fields, or export data.", [".pdf"]),

    # 6. PDF Security
    ToolDefinition("protect_pdf", "Protect PDF", "Security", "🔒", "Encrypt PDF with AES-256 password and restrict print/copy/edit permissions.", [".pdf"]),
    ToolDefinition("unlock_pdf", "Unlock PDF", "Security", "🔓", "Remove password protection from an encrypted PDF.", [".pdf"]),
    ToolDefinition("sign_pdf", "Sign PDF", "Security", "✍️", "Add visual electronic signatures via freehand drawing, cursive typing, or stamp.", [".pdf"]),
    ToolDefinition("redact_pdf", "Redact PDF", "Security", "⬛", "Permanently black-out sensitive text or rectangular areas forensically.", [".pdf"]),

    # 7. AI & Intelligence
    ToolDefinition("ai_summarizer", "AI Summarizer", "AI & Intelligence", "🧠", "Generate executive summaries and key takeaway bullet points (offline NLP or Gemini).", [".pdf"]),
    ToolDefinition("translate_pdf", "Translate PDF", "AI & Intelligence", "🌍", "Translate document text to another language while preserving structure.", [".pdf"]),
    ToolDefinition("pdf_to_markdown", "PDF to Markdown", "AI & Intelligence", "📑", "Convert PDF to GitHub Flavored Markdown, preserving headings, lists, and tables.", [".pdf"]),
    ToolDefinition("compare_pdf", "Compare PDF", "AI & Intelligence", "⚖️", "Compare two PDF documents side-by-side with visual and text diff highlighting.", [".pdf"], allow_multiple=True),
]

CATEGORIES: List[str] = [
    "All Tools",
    "Organize",
    "Optimize",
    "Convert To",
    "Convert From",
    "Edit",
    "Security",
    "AI & Intelligence",
]


# ===========================================================================
# 2. TOOL CARD WIDGET & DASHBOARD
# ===========================================================================

class ToolCardWidget(QFrame):
    """Interactive card representing an individual PDF tool."""

    clicked = Signal(str)

    def __init__(self, tool: ToolDefinition, parent=None):
        super().__init__(parent)
        self.tool = tool
        self.setObjectName("ToolCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(220, 140)
        self.setSizePolicy(self.sizePolicy().horizontalPolicy(), self.sizePolicy().verticalPolicy())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        # Top row: icon + category badge
        top_row = QHBoxLayout()
        lbl_icon = QLabel(tool.icon)
        lbl_icon.setStyleSheet("font-size: 24px; background: transparent;")
        top_row.addWidget(lbl_icon)
        top_row.addStretch()

        badge = QLabel(tool.category)
        badge.setObjectName("CategoryBadge")
        badge.setStyleSheet(
            "background-color: #232838; color: #a5b4fc; font-size: 11px; "
            "font-weight: 600; padding: 2px 8px; border-radius: 4px; border: 1px solid #373e56;"
        )
        top_row.addWidget(badge)
        layout.addLayout(top_row)

        # Title
        lbl_title = QLabel(tool.name)
        lbl_title.setObjectName("ToolCardTitle")
        lbl_title.setStyleSheet("font-size: 15px; font-weight: 600; color: #f3f4f6;")
        layout.addWidget(lbl_title)

        # Description
        lbl_desc = QLabel(tool.description)
        lbl_desc.setWordWrap(True)
        lbl_desc.setObjectName("ToolCardDesc")
        lbl_desc.setStyleSheet("font-size: 12px; color: #9ca3af; line-height: 1.3;")
        layout.addWidget(lbl_desc, stretch=1)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.tool.id)
        super().mousePressEvent(event)


class ToolkitDashboardWidget(QWidget):
    """Categorized dashboard displaying all PDF tools with real-time search & filters."""

    tool_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cards: List[Tuple[ToolCardWidget, ToolDefinition]] = []
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 16, 20, 16)
        main_layout.setSpacing(14)

        # Header banner
        header_layout = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        title = QLabel("🛠️ PDF Toolkit Hub")
        title.setStyleSheet("font-size: 22px; font-weight: 700; color: #f8fafc;")
        subtitle = QLabel("26 professional tools to organize, optimize, convert, edit, protect, and analyze your PDFs")
        subtitle.setStyleSheet("font-size: 13px; color: #94a3b8;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header_layout.addLayout(title_box)
        header_layout.addStretch()

        # Search bar
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search tools (e.g. merge, compress, sign, redact, ocr)...")
        self.search_input.setFixedWidth(340)
        self.search_input.setStyleSheet(
            "background-color: #1a1d26; color: #f3f4f6; border: 1px solid #363b4d; "
            "border-radius: 8px; padding: 8px 14px; font-size: 13px;"
        )
        self.search_input.textChanged.connect(self._filter_cards)
        header_layout.addWidget(self.search_input)

        main_layout.addLayout(header_layout)

        # Category Filter Pills
        pills_layout = QHBoxLayout()
        pills_layout.setSpacing(8)
        self.category_group = QButtonGroup(self)
        self.category_group.setExclusive(True)

        for idx, cat in enumerate(CATEGORIES):
            btn = QPushButton(cat)
            btn.setCheckable(True)
            btn.setObjectName("CategoryPill")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton { background-color: #1a1d26; color: #94a3b8; border: 1px solid #282c38; "
                "border-radius: 16px; padding: 6px 14px; font-size: 12px; font-weight: 500; } "
                "QPushButton:hover { background-color: #242938; color: #f1f5f9; border-color: #3b4256; } "
                "QPushButton:checked { background-color: #4f46e5; color: #ffffff; border-color: #6366f1; font-weight: 600; }"
            )
            btn.clicked.connect(self._filter_cards)
            self.category_group.addButton(btn, idx)
            pills_layout.addWidget(btn)
            if idx == 0:
                btn.setChecked(True)

        pills_layout.addStretch()
        main_layout.addLayout(pills_layout)

        # Scrollable Cards Grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        self.grid = QGridLayout(container)
        self.grid.setContentsMargins(4, 8, 4, 16)
        self.grid.setSpacing(14)

        for tool in ALL_TOOLS:
            card = ToolCardWidget(tool)
            card.clicked.connect(self.tool_selected.emit)
            self.cards.append((card, tool))

        self._relayout_cards()
        scroll.setWidget(container)
        main_layout.addWidget(scroll, stretch=1)

    def _relayout_cards(self):
        # Clear existing grid
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        # Determine active category & search
        active_cat_btn = self.category_group.checkedButton()
        active_cat = active_cat_btn.text() if active_cat_btn else "All Tools"
        query = self.search_input.text().strip().lower()

        visible_cards = []
        for card, tool in self.cards:
            match_cat = (active_cat == "All Tools") or (tool.category.lower() == active_cat.lower())
            match_search = (
                not query
                or query in tool.name.lower()
                or query in tool.description.lower()
                or query in tool.category.lower()
            )
            if match_cat and match_search:
                visible_cards.append(card)

        # Arrange in 3 columns
        cols = 3
        for idx, card in enumerate(visible_cards):
            r = idx // cols
            c = idx % cols
            self.grid.addWidget(card, r, c)

    def _filter_cards(self):
        self._relayout_cards()


# ===========================================================================
# 3. PDF VIEWER WIDGET (PyMuPDF Native)
# ===========================================================================

class PDFViewerWidget(QWidget):
    """High-performance PyMuPDF document previewer with zoom and page navigation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc: Optional[fitz.Document] = None
        self.current_page: int = 0
        self.zoom_factor: float = 1.0
        self.current_pdf_path: Optional[str] = None

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(8, 4, 8, 4)
        toolbar.setSpacing(6)

        self.btn_prev = QPushButton("◀ Prev")
        self.btn_prev.setObjectName("SecondaryButton")
        self.btn_prev.setFixedWidth(70)
        self.btn_prev.clicked.connect(self._prev_page)

        self.lbl_page_info = QLabel("Page 0 / 0")
        self.lbl_page_info.setStyleSheet("font-weight: 600; color: #cbd5e1; min-width: 90px; text-align: center;")
        self.lbl_page_info.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_next = QPushButton("Next ▶")
        self.btn_next.setObjectName("SecondaryButton")
        self.btn_next.setFixedWidth(70)
        self.btn_next.clicked.connect(self._next_page)

        toolbar.addWidget(self.btn_prev)
        toolbar.addWidget(self.lbl_page_info)
        toolbar.addWidget(self.btn_next)
        toolbar.addSpacing(12)

        self.btn_zoom_out = QPushButton("🔍 -")
        self.btn_zoom_out.setObjectName("SecondaryButton")
        self.btn_zoom_out.setFixedWidth(50)
        self.btn_zoom_out.clicked.connect(self._zoom_out)

        self.lbl_zoom = QLabel("100%")
        self.lbl_zoom.setStyleSheet("color: #94a3b8; font-size: 11px;")

        self.btn_zoom_in = QPushButton("🔍 +")
        self.btn_zoom_in.setObjectName("SecondaryButton")
        self.btn_zoom_in.setFixedWidth(50)
        self.btn_zoom_in.clicked.connect(self._zoom_in)

        self.btn_fit = QPushButton("Fit Width")
        self.btn_fit.setObjectName("SecondaryButton")
        self.btn_fit.setFixedWidth(80)
        self.btn_fit.clicked.connect(self._fit_width)

        toolbar.addWidget(self.btn_zoom_out)
        toolbar.addWidget(self.lbl_zoom)
        toolbar.addWidget(self.btn_zoom_in)
        toolbar.addWidget(self.btn_fit)
        toolbar.addStretch()

        layout.addLayout(toolbar)

        # Scroll area for page canvas
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setStyleSheet("background-color: #12141c; border: 1px solid #232734; border-radius: 8px;")

        self.lbl_canvas = QLabel()
        self.lbl_canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_canvas.setStyleSheet("background-color: transparent;")
        self.scroll_area.setWidget(self.lbl_canvas)

        layout.addWidget(self.scroll_area, stretch=1)
        self._update_nav_state()

    def load_document(self, pdf_path: str | Path, password: Optional[str] = None):
        """Load and display PDF from file path."""
        p = Path(pdf_path).resolve()
        if not p.is_file():
            return

        if self.doc:
            self.doc.close()

        try:
            self.doc = fitz.open(str(p))
            if self.doc.is_encrypted and password:
                self.doc.authenticate(password)
            self.current_pdf_path = str(p)
            self.current_page = 0
            self._render_page()
        except Exception as exc:
            self.lbl_canvas.setText(f"Unable to render PDF preview: {exc}")

    def _render_page(self):
        if not self.doc or len(self.doc) == 0:
            self.lbl_canvas.setText("No document loaded")
            self._update_nav_state()
            return

        total = len(self.doc)
        self.current_page = max(0, min(total - 1, self.current_page))
        page = self.doc[self.current_page]

        # Calculate zoom matrix
        dpi = int(120 * self.zoom_factor)
        pix = page.get_pixmap(dpi=dpi)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(img)
        self.lbl_canvas.setPixmap(pixmap)

        self.lbl_page_info.setText(f"Page {self.current_page + 1} / {total}")
        self.lbl_zoom.setText(f"{int(self.zoom_factor * 100)}%")
        self._update_nav_state()

    def _prev_page(self):
        if self.doc and self.current_page > 0:
            self.current_page -= 1
            self._render_page()

    def _next_page(self):
        if self.doc and self.current_page < len(self.doc) - 1:
            self.current_page += 1
            self._render_page()

    def _zoom_in(self):
        self.zoom_factor = min(3.0, self.zoom_factor + 0.25)
        self._render_page()

    def _zoom_out(self):
        self.zoom_factor = max(0.5, self.zoom_factor - 0.25)
        self._render_page()

    def _fit_width(self):
        self.zoom_factor = 1.0
        self._render_page()

    def _update_nav_state(self):
        total = len(self.doc) if self.doc else 0
        self.btn_prev.setEnabled(self.doc is not None and self.current_page > 0)
        self.btn_next.setEnabled(self.doc is not None and self.current_page < total - 1)
        self.btn_zoom_in.setEnabled(self.doc is not None)
        self.btn_zoom_out.setEnabled(self.doc is not None)
        self.btn_fit.setEnabled(self.doc is not None)

    def close_doc(self):
        if self.doc:
            self.doc.close()
            self.doc = None


# ===========================================================================
# 4. SIGNATURE CANVAS WIDGET
# ===========================================================================

class DrawCanvas(QWidget):
    """Drawing area for freehand signatures."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StaticContents)
        self.setStyleSheet("background-color: #ffffff; border-radius: 6px;")
        self.pen_color = QColor(10, 20, 80)
        self.pen_width = 3
        self.lines: List[List[QPoint]] = []
        self.current_line: List[QPoint] = []

    def set_pen_color(self, color: QColor):
        self.pen_color = color

    def set_pen_width(self, width: int):
        self.pen_width = width

    def clear(self):
        self.lines.clear()
        self.current_line.clear()
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.current_line = [event.position().toPoint()]
            self.lines.append(self.current_line)
            self.update()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self.current_line:
            self.current_line.append(event.position().toPoint())
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), Qt.GlobalColor.white)

        pen = QPen(self.pen_color, self.pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)

        for line in self.lines:
            if len(line) > 1:
                for i in range(len(line) - 1):
                    painter.drawLine(line[i], line[i + 1])
            elif len(line) == 1:
                painter.drawPoint(line[0])

    def to_png_bytes(self) -> bytes:
        img = QImage(self.size(), QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(self.pen_color, self.pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        for line in self.lines:
            if len(line) > 1:
                for i in range(len(line) - 1):
                    painter.drawLine(line[i], line[i + 1])
            elif len(line) == 1:
                painter.drawPoint(line[0])
        painter.end()

        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(buffer, "PNG")
        return bytes(buffer.data())


class SignatureCanvasWidget(QWidget):
    """Complete signature creation widget supporting Draw, Type, and Upload tabs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.uploaded_image_bytes: Optional[bytes] = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(
            "QTabWidget::pane { border: 1px solid #363b4d; border-radius: 6px; } "
            "QTabBar::tab { background-color: #1a1d26; color: #94a3b8; padding: 6px 14px; border-top-left-radius: 6px; border-top-right-radius: 6px; } "
            "QTabBar::tab:selected { background-color: #242838; color: #f8fafc; font-weight: 600; border-bottom: 2px solid #6366f1; }"
        )

        # Tab 1: Draw
        tab_draw = QWidget()
        layout_draw = QVBoxLayout(tab_draw)
        self.draw_canvas = DrawCanvas()
        self.draw_canvas.setFixedHeight(140)
        layout_draw.addWidget(self.draw_canvas)

        controls = QHBoxLayout()
        btn_black = QPushButton("Black")
        btn_black.setObjectName("SecondaryButton")
        btn_black.clicked.connect(lambda: self.draw_canvas.set_pen_color(QColor(0, 0, 0)))
        btn_blue = QPushButton("Navy Blue")
        btn_blue.setObjectName("SecondaryButton")
        btn_blue.clicked.connect(lambda: self.draw_canvas.set_pen_color(QColor(10, 30, 100)))

        btn_clear = QPushButton("Clear")
        btn_clear.setObjectName("DangerButton")
        btn_clear.clicked.connect(self.draw_canvas.clear)

        controls.addWidget(btn_black)
        controls.addWidget(btn_blue)
        controls.addStretch()
        controls.addWidget(btn_clear)
        layout_draw.addLayout(controls)
        self.tabs.addTab(tab_draw, "✍️ Draw")

        # Tab 2: Type
        tab_type = QWidget()
        layout_type = QVBoxLayout(tab_type)
        self.txt_type_sig = QLineEdit()
        self.txt_type_sig.setPlaceholderText("Type full name for signature...")
        self.txt_type_sig.setStyleSheet("background-color: #1a1d26; color: #f3f4f6; border: 1px solid #363b4d; border-radius: 6px; padding: 8px;")
        layout_type.addWidget(self.txt_type_sig)
        self.lbl_type_preview = QLabel("Jane Doe")
        self.lbl_type_preview.setStyleSheet("background-color: #ffffff; color: #0a1450; font-family: 'Segoe Script', 'Brush Script MT', cursive; font-size: 26px; padding: 20px; border-radius: 6px; text-align: center;")
        self.lbl_type_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.txt_type_sig.textChanged.connect(lambda t: self.lbl_type_preview.setText(t or "Jane Doe"))
        layout_type.addWidget(self.lbl_type_preview)
        self.tabs.addTab(tab_type, "⌨️ Type")

        # Tab 3: Upload
        tab_upload = QWidget()
        layout_upload = QVBoxLayout(tab_upload)
        self.btn_choose_stamp = QPushButton("📁 Select Signature Image (PNG)")
        self.btn_choose_stamp.setObjectName("SecondaryButton")
        self.btn_choose_stamp.clicked.connect(self._choose_signature_file)
        self.lbl_upload_info = QLabel("No file chosen")
        self.lbl_upload_info.setStyleSheet("color: #94a3b8; font-size: 12px;")
        layout_upload.addWidget(self.btn_choose_stamp)
        layout_upload.addWidget(self.lbl_upload_info)
        layout_upload.addStretch()
        self.tabs.addTab(tab_upload, "📁 Upload")

        layout.addWidget(self.tabs)

    def _choose_signature_file(self):
        f, _ = QFileDialog.getOpenFileName(self, "Choose Signature Image", "", "Images (*.png *.jpg *.jpeg)")
        if f:
            with open(f, "rb") as fh:
                self.uploaded_image_bytes = fh.read()
            self.lbl_upload_info.setText(Path(f).name)

    def get_signature_data(self) -> Union[bytes, str]:
        tab_idx = self.tabs.currentIndex()
        if tab_idx == 0:  # Draw
            return self.draw_canvas.to_png_bytes()
        elif tab_idx == 1:  # Type
            return self.txt_type_sig.text().strip() or "Digitally Signed"
        else:  # Upload
            return self.uploaded_image_bytes or b""


# ===========================================================================
# 5. BACKGROUND WORKER FOR TOOLKIT OPERATIONS
# ===========================================================================

class ToolkitWorker(QThread):
    """Background worker executing toolkit operations without freezing UI."""

    finished_result = Signal(bool, object, str)  # success, result_data, message

    def __init__(self, task_fn: Callable[[], Any], parent=None):
        super().__init__(parent)
        self.task_fn = task_fn

    def run(self):
        try:
            res = self.task_fn()
            self.finished_result.emit(True, res, "Completed successfully")
        except Exception as exc:
            self.finished_result.emit(False, None, str(exc))


# ===========================================================================
# 6. TOOL WORKSPACE WIDGET (Unified 5-Step Architecture)
# ===========================================================================

class ToolWorkspaceWidget(QWidget):
    """
    Universal 5-step workspace:
    Upload -> Configure -> Process -> Preview/Result -> Save
    """

    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_tool: Optional[ToolDefinition] = None
        self.loaded_files: List[str] = []
        self.last_output_path: Optional[str] = None
        self.worker: Optional[ToolkitWorker] = None

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 12, 16, 14)
        main_layout.setSpacing(10)

        # 1. Top Breadcrumb & Navigation
        top_bar = QHBoxLayout()
        top_bar.setSpacing(12)

        self.btn_back = QPushButton("← Back to Toolkit")
        self.btn_back.setObjectName("SecondaryButton")
        self.btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_back.clicked.connect(self.back_requested.emit)
        top_bar.addWidget(self.btn_back)

        self.lbl_tool_badge = QLabel("Category")
        self.lbl_tool_badge.setObjectName("CategoryBadge")
        self.lbl_tool_badge.setStyleSheet(
            "background-color: #232838; color: #a5b4fc; font-size: 11px; "
            "font-weight: 600; padding: 3px 10px; border-radius: 4px; border: 1px solid #373e56;"
        )
        top_bar.addWidget(self.lbl_tool_badge)

        self.lbl_tool_title = QLabel("Tool Name")
        self.lbl_tool_title.setStyleSheet("font-size: 18px; font-weight: 700; color: #f8fafc;")
        top_bar.addWidget(self.lbl_tool_title)

        top_bar.addStretch()
        main_layout.addLayout(top_bar)

        # 2. Main Horizontal Splitter (Left: Controls / Right: Preview)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: Controls Scroll Area
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.setSpacing(12)

        # Step 1: Upload Box
        grp_upload = QGroupBox("1. Upload Source Files")
        grp_upload.setObjectName("CardFrame")
        layout_up = QVBoxLayout(grp_upload)

        btn_row = QHBoxLayout()
        self.btn_pick_files = QPushButton("➕ Select File(s)")
        self.btn_pick_files.setObjectName("PrimaryButton")
        self.btn_pick_files.clicked.connect(self._browse_input_files)
        btn_row.addWidget(self.btn_pick_files)

        self.btn_clear_files = QPushButton("Clear")
        self.btn_clear_files.setObjectName("SecondaryButton")
        self.btn_clear_files.clicked.connect(self._clear_input_files)
        btn_row.addWidget(self.btn_clear_files)
        layout_up.addLayout(btn_row)

        self.lbl_file_count = QLabel("0 file(s) loaded")
        self.lbl_file_count.setStyleSheet("color: #94a3b8; font-size: 12px;")
        layout_up.addWidget(self.lbl_file_count)

        self.file_list_table = QTableWidget(0, 2)
        self.file_list_table.setHorizontalHeaderLabels(["Filename", "Size"])
        self.file_list_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.file_list_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.file_list_table.setFixedHeight(110)
        layout_up.addWidget(self.file_list_table)
        left_layout.addWidget(grp_upload)

        # Step 2: Dynamic Configuration Box
        self.grp_config = QGroupBox("2. Configure Tool Settings")
        self.grp_config.setObjectName("CardFrame")
        self.config_layout = QVBoxLayout(self.grp_config)
        left_layout.addWidget(self.grp_config)

        # Step 3: Action Execution Box
        grp_action = QGroupBox("3. Process & Output")
        grp_action.setObjectName("CardFrame")
        layout_act = QVBoxLayout(grp_action)

        self.btn_process = QPushButton("🚀 Run Tool")
        self.btn_process.setObjectName("PrimaryButton")
        self.btn_process.setFixedHeight(40)
        self.btn_process.clicked.connect(self._execute_tool)
        layout_act.addWidget(self.btn_process)

        self.prog_bar = QProgressBar()
        self.prog_bar.setVisible(False)
        layout_act.addWidget(self.prog_bar)

        self.lbl_process_status = QLabel("Ready")
        self.lbl_process_status.setStyleSheet("color: #94a3b8; font-size: 12px;")
        layout_act.addWidget(self.lbl_process_status)

        out_btn_row = QHBoxLayout()
        self.btn_save_as = QPushButton("💾 Save As...")
        self.btn_save_as.setObjectName("SuccessButton")
        self.btn_save_as.setEnabled(False)
        self.btn_save_as.clicked.connect(self._save_output_as)

        self.btn_open_folder = QPushButton("📂 Open Folder")
        self.btn_open_folder.setObjectName("SecondaryButton")
        self.btn_open_folder.setEnabled(False)
        self.btn_open_folder.clicked.connect(self._open_output_folder)

        out_btn_row.addWidget(self.btn_save_as)
        out_btn_row.addWidget(self.btn_open_folder)
        layout_act.addLayout(out_btn_row)

        left_layout.addWidget(grp_action)
        left_layout.addStretch()

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFixedWidth(400)
        left_scroll.setWidget(left_container)
        splitter.addWidget(left_scroll)

        # Right: Output / Preview Stack
        self.right_stack = QStackedWidget()

        # Page 0: PDF Document Viewer
        self.pdf_viewer = PDFViewerWidget()
        self.right_stack.addWidget(self.pdf_viewer)

        # Page 1: Text / Markdown / HTML Diff Viewer
        self.txt_viewer = QTextBrowser()
        self.txt_viewer.setStyleSheet("background-color: #12141c; color: #f3f4f6; border: 1px solid #282c38; border-radius: 8px; padding: 12px; font-family: Consolas, monospace;")
        self.right_stack.addWidget(self.txt_viewer)

        splitter.addWidget(self.right_stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        main_layout.addWidget(splitter, stretch=1)

    # -----------------------------------------------------------------------
    # Setup for selected tool
    # -----------------------------------------------------------------------
    def load_tool(self, tool_id: str):
        """Configure workspace controls specifically for the given tool."""
        found = [t for t in ALL_TOOLS if t.id == tool_id]
        if not found:
            return

        self.current_tool = found[0]
        self.lbl_tool_badge.setText(self.current_tool.category)
        self.lbl_tool_title.setText(f"{self.current_tool.icon} {self.current_tool.name}")
        self.btn_process.setText(f"🚀 {self.current_tool.name}")
        self._clear_input_files()
        self._build_tool_config_ui()
        self.right_stack.setCurrentIndex(0)

    def _clear_input_files(self):
        self.loaded_files.clear()
        self.file_list_table.setRowCount(0)
        self.lbl_file_count.setText("0 file(s) loaded")
        self.btn_save_as.setEnabled(False)
        self.btn_open_folder.setEnabled(False)
        self.last_output_path = None
        self.lbl_process_status.setText("Ready")
        self.pdf_viewer.close_doc()
        self.txt_viewer.clear()

    def _browse_input_files(self):
        if not self.current_tool:
            return

        exts = " ".join([f"*{e}" for e in self.current_tool.accepted_exts])
        filter_str = f"{self.current_tool.name} Inputs ({exts});;All Files (*.*)"

        if self.current_tool.allow_multiple:
            files, _ = QFileDialog.getOpenFileNames(self, f"Select Files for {self.current_tool.name}", "", filter_str)
            if files:
                self.loaded_files.extend(files)
        else:
            file, _ = QFileDialog.getOpenFileName(self, f"Select File for {self.current_tool.name}", "", filter_str)
            if file:
                self.loaded_files = [file]

        self._refresh_file_list()

    def _refresh_file_list(self):
        self.file_list_table.setRowCount(len(self.loaded_files))
        for idx, f in enumerate(self.loaded_files):
            p = Path(f)
            self.file_list_table.setItem(idx, 0, QTableWidgetItem(p.name))
            size_str = format_bytes(p.stat().st_size) if p.exists() else "0 B"
            self.file_list_table.setItem(idx, 1, QTableWidgetItem(size_str))

        self.lbl_file_count.setText(f"{len(self.loaded_files)} file(s) loaded")
        if self.loaded_files:
            first = self.loaded_files[0]
            if Path(first).suffix.lower() == ".pdf":
                self.pdf_viewer.load_document(first)
                self.right_stack.setCurrentIndex(0)

    # -----------------------------------------------------------------------
    # Dynamic Configuration Panels
    # -----------------------------------------------------------------------
    def _build_tool_config_ui(self):
        # Clear existing config widgets
        while self.config_layout.count():
            item = self.config_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        tid = self.current_tool.id if self.current_tool else ""

        if tid == "compress_pdf":
            self.lbl_comp = QLabel("Compression Level:")
            self.cmb_comp = QComboBox()
            self.cmb_comp.addItems(["Medium (Recommended - Balanced)", "Low (Print Quality)", "High (Maximum Compression)"])
            self.config_layout.addWidget(self.lbl_comp)
            self.config_layout.addWidget(self.cmb_comp)

        elif tid == "split_pdf":
            self.lbl_split_mode = QLabel("Split Mode:")
            self.cmb_split_mode = QComboBox()
            self.cmb_split_mode.addItems(["Custom Page Ranges (e.g. 1-2, 3-5)", "Every N Pages", "Extract Every Page as Single File"])
            self.lbl_split_param = QLabel("Page Ranges or N:")
            self.txt_split_param = QLineEdit("1-2, 3-5")
            self.config_layout.addWidget(self.lbl_split_mode)
            self.config_layout.addWidget(self.cmb_split_mode)
            self.config_layout.addWidget(self.lbl_split_param)
            self.config_layout.addWidget(self.txt_split_param)

        elif tid in ("remove_pages", "extract_pages"):
            self.lbl_pages = QLabel("Target Pages (e.g. 1, 3, 5-8):")
            self.txt_pages = QLineEdit("1, 3")
            self.config_layout.addWidget(self.lbl_pages)
            self.config_layout.addWidget(self.txt_pages)

        elif tid == "rotate_pdf":
            self.lbl_rot_angle = QLabel("Rotation Angle:")
            self.cmb_rot_angle = QComboBox()
            self.cmb_rot_angle.addItems(["90° Clockwise", "180° Half-Turn", "270° Counter-Clockwise"])
            self.lbl_rot_target = QLabel("Apply To:")
            self.cmb_rot_target = QComboBox()
            self.cmb_rot_target.addItems(["All Pages", "Odd Pages Only", "Even Pages Only", "Custom Pages"])
            self.txt_rot_custom = QLineEdit("")
            self.txt_rot_custom.setPlaceholderText("e.g. 1, 3-5 (if Custom Pages selected)")
            self.config_layout.addWidget(self.lbl_rot_angle)
            self.config_layout.addWidget(self.cmb_rot_angle)
            self.config_layout.addWidget(self.lbl_rot_target)
            self.config_layout.addWidget(self.cmb_rot_target)
            self.config_layout.addWidget(self.txt_rot_custom)

        elif tid == "add_watermark":
            self.lbl_wm_type = QLabel("Watermark Type:")
            self.cmb_wm_type = QComboBox()
            self.cmb_wm_type.addItems(["Text Watermark", "Image Watermark"])
            self.lbl_wm_text = QLabel("Watermark Text:")
            self.txt_wm_text = QLineEdit("CONFIDENTIAL")
            self.lbl_wm_opacity = QLabel("Opacity: 30%")
            self.sld_wm_opacity = QSlider(Qt.Orientation.Horizontal)
            self.sld_wm_opacity.setRange(5, 100)
            self.sld_wm_opacity.setValue(30)
            self.sld_wm_opacity.valueChanged.connect(lambda v: self.lbl_wm_opacity.setText(f"Opacity: {v}%"))
            self.config_layout.addWidget(self.lbl_wm_type)
            self.config_layout.addWidget(self.cmb_wm_type)
            self.config_layout.addWidget(self.lbl_wm_text)
            self.config_layout.addWidget(self.txt_wm_text)
            self.config_layout.addWidget(self.lbl_wm_opacity)
            self.config_layout.addWidget(self.sld_wm_opacity)

        elif tid == "add_page_numbers":
            self.lbl_pn_pos = QLabel("Position:")
            self.cmb_pn_pos = QComboBox()
            self.cmb_pn_pos.addItems(["Bottom Center", "Bottom Right", "Bottom Left", "Top Right", "Top Center"])
            self.lbl_pn_fmt = QLabel("Format String:")
            self.txt_pn_fmt = QLineEdit("Page {n} of {total}")
            self.chk_skip_first = QCheckBox("Skip cover / first page")
            self.config_layout.addWidget(self.lbl_pn_pos)
            self.config_layout.addWidget(self.cmb_pn_pos)
            self.config_layout.addWidget(self.lbl_pn_fmt)
            self.config_layout.addWidget(self.txt_pn_fmt)
            self.config_layout.addWidget(self.chk_skip_first)

        elif tid == "protect_pdf":
            self.lbl_pw = QLabel("Document Password:")
            self.txt_pw = QLineEdit()
            self.txt_pw.setEchoMode(QLineEdit.EchoMode.Password)
            self.chk_pw_print = QCheckBox("Allow Printing")
            self.chk_pw_print.setChecked(True)
            self.chk_pw_copy = QCheckBox("Allow Content Copying")
            self.chk_pw_copy.setChecked(False)
            self.config_layout.addWidget(self.lbl_pw)
            self.config_layout.addWidget(self.txt_pw)
            self.config_layout.addWidget(self.chk_pw_print)
            self.config_layout.addWidget(self.chk_pw_copy)

        elif tid == "unlock_pdf":
            self.lbl_unlock_pw = QLabel("Enter Password to Decrypt:")
            self.txt_unlock_pw = QLineEdit()
            self.txt_unlock_pw.setEchoMode(QLineEdit.EchoMode.Password)
            self.config_layout.addWidget(self.lbl_unlock_pw)
            self.config_layout.addWidget(self.txt_unlock_pw)

        elif tid == "sign_pdf":
            self.sig_canvas = SignatureCanvasWidget()
            self.lbl_signer = QLabel("Signer Name:")
            self.txt_signer = QLineEdit("Jane Doe")
            self.chk_sig_date = QCheckBox("Add Current Date Stamp")
            self.chk_sig_date.setChecked(True)
            self.config_layout.addWidget(self.sig_canvas)
            self.config_layout.addWidget(self.lbl_signer)
            self.config_layout.addWidget(self.txt_signer)
            self.config_layout.addWidget(self.chk_sig_date)

        elif tid == "redact_pdf":
            self.lbl_redact_terms = QLabel("Search Terms to Erase (comma-separated):")
            self.txt_redact_terms = QLineEdit("CONFIDENTIAL, PRIVATE, SSN")
            self.lbl_redact_notice = QLabel("⚠️ Forensic permanent sanitization: glyphs and image pixels will be permanently eradicated.")
            self.lbl_redact_notice.setWordWrap(True)
            self.lbl_redact_notice.setStyleSheet("color: #fbbf24; font-size: 11px;")
            self.config_layout.addWidget(self.lbl_redact_terms)
            self.config_layout.addWidget(self.txt_redact_terms)
            self.config_layout.addWidget(self.lbl_redact_notice)

        elif tid == "ai_summarizer":
            self.lbl_sum_len = QLabel("Summary Detail:")
            self.cmb_sum_len = QComboBox()
            self.cmb_sum_len.addItems(["Medium (Executive Summary)", "Short (3-5 Bullet Points)", "Detailed (Section Breakdown)"])
            self.chk_use_gemini = QCheckBox("Use Gemini API (if key configured)")
            self.config_layout.addWidget(self.lbl_sum_len)
            self.config_layout.addWidget(self.cmb_sum_len)
            self.config_layout.addWidget(self.chk_use_gemini)

        elif tid == "translate_pdf":
            self.lbl_trans_lang = QLabel("Target Language:")
            self.cmb_trans_lang = QComboBox()
            self.cmb_trans_lang.addItems(["Spanish (es)", "French (fr)", "German (de)", "Italian (it)", "Portuguese (pt)", "Chinese (zh)", "Japanese (ja)", "Arabic (ar)"])
            self.config_layout.addWidget(self.lbl_trans_lang)
            self.config_layout.addWidget(self.cmb_trans_lang)

        elif tid == "compare_pdf":
            self.lbl_comp_info = QLabel("Select 2 PDF files to compare text & layout differences.")
            self.lbl_comp_info.setWordWrap(True)
            self.lbl_comp_info.setStyleSheet("color: #cbd5e1; font-size: 12px;")
            self.config_layout.addWidget(self.lbl_comp_info)

        elif tid == "pdf_to_images":
            self.lbl_img_fmt = QLabel("Image Format:")
            self.cmb_img_fmt = QComboBox()
            self.cmb_img_fmt.addItems(["JPG", "PNG", "WEBP"])
            self.lbl_img_dpi = QLabel("DPI Resolution:")
            self.cmb_img_dpi = QComboBox()
            self.cmb_img_dpi.addItems(["150 DPI (Recommended)", "300 DPI (High Quality)", "72 DPI (Web)"])
            self.config_layout.addWidget(self.lbl_img_fmt)
            self.config_layout.addWidget(self.cmb_img_fmt)
            self.config_layout.addWidget(self.lbl_img_dpi)
            self.config_layout.addWidget(self.cmb_img_dpi)

        else:
            # Default options
            lbl_generic = QLabel("Configure standard processing options:")
            lbl_generic.setStyleSheet("color: #94a3b8; font-size: 12px;")
            self.config_layout.addWidget(lbl_generic)

    # -----------------------------------------------------------------------
    # Execution & Processing Workflow
    # -----------------------------------------------------------------------
    def _execute_tool(self):
        if not self.current_tool:
            return

        if not self.loaded_files:
            QMessageBox.warning(self, "No Input Files", "Please add at least one input file to process.")
            return

        tid = self.current_tool.id
        self.btn_process.setEnabled(False)
        self.prog_bar.setVisible(True)
        self.prog_bar.setRange(0, 0)  # Indeterminate progress
        self.lbl_process_status.setText("Processing document in background...")

        temp_dir = tempfile.mkdtemp(prefix="toolkit_out_")
        in_file = self.loaded_files[0]
        in_p = Path(in_file)

        # Build execution lambda
        _tk = _get_toolkit_functions()  # lazy import all toolkit functions
        task_fn = None

        if tid == "merge_pdf":
            out_file = os.path.join(temp_dir, f"merged_{int(datetime.datetime.now().timestamp())}.pdf")
            task_fn = lambda: _tk.merge_pdfs(self.loaded_files, out_file)

        elif tid == "split_pdf":
            mode_text = self.cmb_split_mode.currentText()
            mode = "ranges" if "Ranges" in mode_text else ("every_n" if "Every N" in mode_text else "all_single")
            param = self.txt_split_param.text().strip()
            n_val = int(param) if param.isdigit() else 1
            task_fn = lambda: _tk.split_pdf(in_file, temp_dir, mode=mode, ranges=param, n=n_val)

        elif tid == "remove_pages":
            out_file = os.path.join(temp_dir, f"{in_p.stem}_removed.pdf")
            pages = self.txt_pages.text().strip()
            task_fn = lambda: _tk.remove_pages(in_file, out_file, pages)

        elif tid == "extract_pages":
            out_file = os.path.join(temp_dir, f"{in_p.stem}_extracted.pdf")
            pages = self.txt_pages.text().strip()
            task_fn = lambda: _tk.extract_pages(in_file, out_file, pages)

        elif tid == "organize_pages":
            out_file = os.path.join(temp_dir, f"{in_p.stem}_organized.pdf")
            doc_len = len(fitz.open(in_file))
            order = list(range(doc_len))
            task_fn = lambda: _tk.organize_pages(in_file, out_file, order)

        elif tid in ("scan_to_pdf", "images_to_pdf"):
            out_file = os.path.join(temp_dir, f"scanned_{int(datetime.datetime.now().timestamp())}.pdf")
            task_fn = lambda: _tk.images_to_pdf(self.loaded_files, out_file)

        elif tid == "rotate_pdf":
            out_file = os.path.join(temp_dir, f"{in_p.stem}_rotated.pdf")
            angle_str = self.cmb_rot_angle.currentText()
            angle = 90 if "90" in angle_str else (180 if "180" in angle_str else 270)
            target_str = self.cmb_rot_target.currentText().lower()
            target = "all" if "all" in target_str else ("odd" if "odd" in target_str else ("even" if "even" in target_str else "custom"))
            custom_p = self.txt_rot_custom.text().strip() if target == "custom" else None
            task_fn = lambda: _tk.rotate_pdf(in_file, out_file, angle=angle, page_target=target, custom_pages=custom_p)

        elif tid == "compress_pdf":
            out_file = os.path.join(temp_dir, f"{in_p.stem}_compressed.pdf")
            lvl_text = self.cmb_comp.currentText().lower()
            lvl = "high" if "high" in lvl_text else ("low" if "low" in lvl_text else "medium")
            task_fn = lambda: _tk.compress_pdf(in_file, out_file, level=lvl)

        elif tid == "repair_pdf":
            out_file = os.path.join(temp_dir, f"{in_p.stem}_repaired.pdf")
            task_fn = lambda: _tk.repair_pdf(in_file, out_file)

        elif tid == "ocr_pdf":
            out_file = os.path.join(temp_dir, f"{in_p.stem}_searchable.pdf")
            task_fn = lambda: _tk.ocr_pdf(in_file, out_file)

        elif tid == "word_to_pdf":
            out_file = os.path.join(temp_dir, f"{in_p.stem}.pdf")
            task_fn = lambda: _tk.word_to_pdf(in_file, out_file)

        elif tid == "powerpoint_to_pdf":
            out_file = os.path.join(temp_dir, f"{in_p.stem}.pdf")
            task_fn = lambda: _tk.powerpoint_to_pdf(in_file, out_file)

        elif tid == "excel_to_pdf":
            out_file = os.path.join(temp_dir, f"{in_p.stem}.pdf")
            task_fn = lambda: _tk.excel_to_pdf(in_file, out_file)

        elif tid == "html_to_pdf":
            out_file = os.path.join(temp_dir, f"{in_p.stem}.pdf")
            task_fn = lambda: _tk.html_to_pdf(in_file, out_file)

        elif tid == "pdf_to_images":
            dpi_map = {"150": 150, "300": 300, "72": 72}
            dpi = dpi_map.get(self.cmb_img_dpi.currentText()[:3], 150)
            fmt = self.cmb_img_fmt.currentText()
            task_fn = lambda: _tk.pdf_to_images(in_file, temp_dir, dpi=dpi, fmt=fmt)

        elif tid == "pdf_to_word":
            out_file = os.path.join(temp_dir, f"{in_p.stem}.docx")
            task_fn = lambda: _tk.pdf_to_word(in_file, out_file)

        elif tid == "pdf_to_powerpoint":
            out_file = os.path.join(temp_dir, f"{in_p.stem}.pptx")
            task_fn = lambda: _tk.pdf_to_powerpoint(in_file, out_file)

        elif tid == "pdf_to_excel":
            out_file = os.path.join(temp_dir, f"{in_p.stem}.xlsx")
            task_fn = lambda: _tk.pdf_to_excel(in_file, out_file)

        elif tid == "pdf_to_pdfa":
            out_file = os.path.join(temp_dir, f"{in_p.stem}_pdfa.pdf")
            task_fn = lambda: _tk.pdf_to_pdfa(in_file, out_file)

        elif tid == "edit_pdf":
            out_file = os.path.join(temp_dir, f"{in_p.stem}_edited.pdf")
            task_fn = lambda: _tk.edit_pdf_content(in_file, out_file, text_items=[{"page": 1, "text": "Edited with PDF Toolkit", "rect": (50, 50, 300, 80), "fontsize": 14}])

        elif tid == "add_page_numbers":
            out_file = os.path.join(temp_dir, f"{in_p.stem}_numbered.pdf")
            pos = self.cmb_pn_pos.currentText().lower().replace(" ", "_")
            fmt = self.txt_pn_fmt.text().strip()
            skip = self.chk_skip_first.isChecked()
            task_fn = lambda: _tk.add_page_numbers(in_file, out_file, position=pos, format_str=fmt, skip_first=skip)

        elif tid == "add_watermark":
            out_file = os.path.join(temp_dir, f"{in_p.stem}_watermarked.pdf")
            wm_text = self.txt_wm_text.text().strip()
            op = self.sld_wm_opacity.value() / 100.0
            task_fn = lambda: _tk.add_watermark(in_file, out_file, text=wm_text, opacity=op)

        elif tid == "crop_pdf":
            out_file = os.path.join(temp_dir, f"{in_p.stem}_cropped.pdf")
            task_fn = lambda: _tk.crop_pdf(in_file, out_file, margins=(20, 20, 20, 20))

        elif tid == "pdf_forms":
            out_file = os.path.join(temp_dir, f"{in_p.stem}_form_data.json")
            task_fn = lambda: _tk.export_form_data(in_file, out_file)

        elif tid == "protect_pdf":
            out_file = os.path.join(temp_dir, f"{in_p.stem}_protected.pdf")
            pw = self.txt_pw.text().strip()
            if not pw:
                QMessageBox.warning(self, "Password Required", "Please enter a password to encrypt this PDF.")
                self.btn_process.setEnabled(True)
                self.prog_bar.setVisible(False)
                return
            allow_pr = self.chk_pw_print.isChecked()
            allow_cp = self.chk_pw_copy.isChecked()
            task_fn = lambda: _tk.protect_pdf(in_file, out_file, user_password=pw, allow_print=allow_pr, allow_copy=allow_cp)

        elif tid == "unlock_pdf":
            out_file = os.path.join(temp_dir, f"{in_p.stem}_unlocked.pdf")
            pw = self.txt_unlock_pw.text().strip()
            task_fn = lambda: _tk.unlock_pdf(in_file, out_file, password=pw)

        elif tid == "sign_pdf":
            out_file = os.path.join(temp_dir, f"{in_p.stem}_signed.pdf")
            sig_data = self.sig_canvas.get_signature_data()
            signer = self.txt_signer.text().strip()
            add_d = self.chk_sig_date.isChecked()
            task_fn = lambda: _tk.sign_pdf(in_file, out_file, signature_data=sig_data, signer_name=signer, add_date=add_d)

        elif tid == "redact_pdf":
            out_file = os.path.join(temp_dir, f"{in_p.stem}_redacted.pdf")
            raw_terms = self.txt_redact_terms.text()
            terms = [t.strip() for t in raw_terms.split(",") if t.strip()]
            task_fn = lambda: _tk.redact_pdf(in_file, out_file, search_terms=terms)

        elif tid == "ai_summarizer":
            len_str = "short" if "Short" in self.cmb_sum_len.currentText() else ("detailed" if "Detailed" in self.cmb_sum_len.currentText() else "medium")
            use_gem = self.chk_use_gemini.isChecked()
            task_fn = lambda: _tk.summarize_pdf(in_file, length=len_str, use_gemini=use_gem)

        elif tid == "translate_pdf":
            code = self.cmb_trans_lang.currentText().split("(")[-1].rstrip(")")
            out_file = os.path.join(temp_dir, f"{in_p.stem}_translated.txt")
            task_fn = lambda: _tk.translate_pdf(in_file, target_lang=code, output_path=out_file)

        elif tid == "pdf_to_markdown":
            out_file = os.path.join(temp_dir, f"{in_p.stem}.md")
            task_fn = lambda: _tk.pdf_to_markdown(in_file, output_path=out_file)

        elif tid == "compare_pdf":
            file2 = self.loaded_files[1] if len(self.loaded_files) > 1 else in_file
            out_file = os.path.join(temp_dir, f"compare_report.html")
            task_fn = lambda: _tk.compare_pdfs(in_file, file2, output_report_path=out_file)

        if not task_fn:
            self.lbl_process_status.setText("Tool configuration pending.")
            self.btn_process.setEnabled(True)
            self.prog_bar.setVisible(False)
            return

        self.worker = ToolkitWorker(task_fn)
        self.worker.finished_result.connect(self._on_worker_finished)
        self.worker.start()

    def _on_worker_finished(self, success: bool, result_data: Any, message: str):
        self.btn_process.setEnabled(True)
        self.prog_bar.setVisible(False)

        if not success:
            self.lbl_process_status.setText(f"❌ Error: {message}")
            QMessageBox.critical(self, "Processing Error", f"Operation failed:\n{message}")
            return

        self.lbl_process_status.setText("✅ Operation finished successfully!")
        self.btn_save_as.setEnabled(True)
        self.btn_open_folder.setEnabled(True)

        # Handle result preview
        if isinstance(result_data, str) and os.path.isfile(result_data):
            self.last_output_path = result_data
            p = Path(result_data)
            if p.suffix.lower() == ".pdf":
                self.pdf_viewer.load_document(result_data)
                self.right_stack.setCurrentIndex(0)
            elif p.suffix.lower() in (".txt", ".md", ".json", ".html"):
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                if p.suffix.lower() == ".html":
                    self.txt_viewer.setHtml(content)
                else:
                    self.txt_viewer.setPlainText(content)
                self.right_stack.setCurrentIndex(1)

        elif isinstance(result_data, list) and result_data and os.path.isfile(result_data[0]):
            self.last_output_path = result_data[0]
            first = result_data[0]
            if Path(first).suffix.lower() == ".pdf":
                self.pdf_viewer.load_document(first)
                self.right_stack.setCurrentIndex(0)
            else:
                self.txt_viewer.setPlainText(f"Generated {len(result_data)} files:\n" + "\n".join(result_data))
                self.right_stack.setCurrentIndex(1)

        elif isinstance(result_data, dict):
            # Dict results (e.g. compress stats, summarizer, comparison)
            if "output_path" in result_data and result_data["output_path"] and os.path.isfile(result_data["output_path"]):
                self.last_output_path = result_data["output_path"]
                if Path(self.last_output_path).suffix.lower() == ".pdf":
                    self.pdf_viewer.load_document(self.last_output_path)
                    self.right_stack.setCurrentIndex(0)

            if "summary" in result_data:
                # Summarizer output
                text = f"=== DOCUMENT SUMMARY ===\n{result_data.get('summary', '')}\n\n=== KEY POINTS ===\n"
                for pt in result_data.get("key_points", []):
                    text += f"• {pt}\n"
                text += f"\nWord Count: {result_data.get('word_count', 0)} (Original: {result_data.get('original_word_count', 0)})"
                self.txt_viewer.setPlainText(text)
                self.right_stack.setCurrentIndex(1)

            elif "savings_percent" in result_data:
                # Compression output
                orig = format_bytes(result_data["original_size"])
                comp = format_bytes(result_data["compressed_size"])
                pct = result_data["savings_percent"]
                msg = (
                    f"🎉 Compression Complete!\n\n"
                    f"Original Size:   {orig}\n"
                    f"Compressed Size: {comp}\n"
                    f"Space Saved:     {pct}% ({format_bytes(result_data['saved_bytes'])})"
                )
                self.lbl_process_status.setText(f"✅ Saved {pct}% ({comp})")
                QMessageBox.information(self, "Compression Savings", msg)

            elif "text_diff_html" in result_data:
                # Comparison HTML diff
                self.txt_viewer.setHtml(result_data["text_diff_html"])
                self.right_stack.setCurrentIndex(1)

    def _save_output_as(self):
        if not self.last_output_path or not os.path.isfile(self.last_output_path):
            QMessageBox.information(self, "Save Output", "No generated file to save.")
            return

        src = Path(self.last_output_path)
        dest, _ = QFileDialog.getSaveFileName(self, "Save Converted Document", src.name, f"Files (*{src.suffix});;All Files (*.*)")
        if dest:
            import shutil
            shutil.copy2(self.last_output_path, dest)
            QMessageBox.information(self, "Saved", f"File saved successfully to:\n{dest}")

    def _open_output_folder(self):
        if not self.last_output_path:
            return
        folder = Path(self.last_output_path).parent
        if sys.platform == "win32":
            os.startfile(folder)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])
