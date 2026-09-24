"""Central visual system, design tokens, icons, and QSS helpers."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QLabel, QWidget


# Color tokens
BG = "#07111F"
SURFACE_1 = "#0D1B2E"
SURFACE_2 = "#13243A"
BORDER = "#476380"
TEXT_PRIMARY = "#F4F8FF"
TEXT_SECONDARY = "#B8C7D9"
ACCENT = "#6654E8"
ACCENT_HOVER = "#5946D0"
DANGER = "#FF8090"
SUCCESS = "#55E0B4"
FOCUS_RING = "#67DFFF"

# Additional semantic colors used by the same system.
WARNING = "#F2C66D"
DISABLED = "#8092A8"
SELECTION = "#2B4167"

# Spacing, radius, and type tokens
SPACING = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "xxl": 32}
RADII = {"sm": 6, "md": 10, "lg": 14}
TYPE_SCALE = {
    "page_title": 24,
    "section_title": 16,
    "body": 13,
    "secondary": 12,
    "eyebrow": 11,
}

ASSET_DIR = Path(__file__).resolve().parent / "assets"
CHEVRON_DOWN = (ASSET_DIR / "chevron-down.svg").as_posix()

TOKENS = {
    "bg": BG,
    "surface_1": SURFACE_1,
    "surface_2": SURFACE_2,
    "border": BORDER,
    "text_primary": TEXT_PRIMARY,
    "text_secondary": TEXT_SECONDARY,
    "accent": ACCENT,
    "accent_hover": ACCENT_HOVER,
    "danger": DANGER,
    "success": SUCCESS,
    "focus_ring": FOCUS_RING,
    "warning": WARNING,
    "disabled": DISABLED,
    "selection": SELECTION,
    "space_1": SPACING["xs"],
    "space_2": SPACING["sm"],
    "space_3": SPACING["md"],
    "space_4": SPACING["lg"],
    "space_6": SPACING["xl"],
    "radius_1": RADII["sm"],
    "radius_2": RADII["md"],
    "radius_3": RADII["lg"],
    "page_title": TYPE_SCALE["page_title"],
    "section_title": TYPE_SCALE["section_title"],
    "body": TYPE_SCALE["body"],
    "secondary": TYPE_SCALE["secondary"],
    "eyebrow": TYPE_SCALE["eyebrow"],
    "chevron_down": CHEVRON_DOWN,
}


QSS_TEMPLATE = r"""
QMainWindow, QDialog, QWidget#centralWidget {{
    background-color: {bg};
    color: {text_primary};
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: {body}px;
}}

QWidget {{
    background-color: transparent;
    color: {text_primary};
    font-family: "Segoe UI", Arial, sans-serif;
}}

QToolTip {{
    background-color: {surface_2};
    color: {text_primary};
    border: 1px solid {border};
    border-radius: {radius_1}px;
    padding: {space_2}px {space_3}px;
}}

/* Typography */
QLabel#AppTitle {{
    color: {text_primary};
    font-size: {page_title}px;
    font-weight: 700;
}}

QLabel#HeaderLabel, QLabel#SectionTitleLarge {{
    color: {text_primary};
    font-size: {section_title}px;
    font-weight: 700;
}}

QLabel#SectionTitle, QLabel[role="sectionTitle"] {{
    color: {text_primary};
    font-size: {section_title}px;
    font-weight: 650;
}}

QLabel#Eyebrow, QLabel[role="eyebrow"] {{
    color: {focus_ring};
    font-size: {eyebrow}px;
    font-weight: 700;
}}

QLabel#MutedLabel, QLabel[role="secondary"] {{
    color: {text_secondary};
    font-size: {secondary}px;
}}

QLabel#StatusLabel {{
    color: {text_primary};
    font-size: {body}px;
    font-weight: 650;
}}

QLabel[state="warning"] {{
    color: {warning};
    font-weight: 650;
}}

QLabel[state="success"] {{
    color: {success};
    font-weight: 650;
}}

QLabel[state="error"] {{
    color: {danger};
    font-weight: 650;
}}

QLabel[state="accent"] {{
    color: {focus_ring};
    font-weight: 650;
}}

QLabel[role="metricIcon"] {{
    color: {focus_ring};
    font-size: 16px;
    font-weight: 700;
}}

QLabel[role="metricTitle"] {{
    color: {text_secondary};
    font-size: {eyebrow}px;
    font-weight: 700;
}}

QLabel[role="metricValue"] {{
    color: {text_primary};
    font-size: 20px;
    font-weight: 700;
}}

QLabel[role="fileGlyph"] {{
    font-size: 20px;
}}

QLabel#PrivacyBadge {{
    background-color: #10342F;
    color: #7EF0CB;
    border: 1px solid #2D806D;
    border-radius: 11px;
    padding: 4px 9px;
    font-size: {eyebrow}px;
    font-weight: 700;
}}

QLabel#CountBadge {{
    background-color: {surface_2};
    color: {text_secondary};
    border-radius: 9px;
    padding: 3px 8px;
    font-size: {eyebrow}px;
    font-weight: 700;
}}

/* Tonal surfaces: borders are reserved for structure and interaction. */
QFrame#HeaderBar, QFrame#AppHeader {{
    background-color: transparent;
    border: none;
}}

QFrame#WorkspaceCard, QFrame#InspectorCard, QFrame#CardFrame,
QFrame#BottomDock, QFrame#PdfToolsPage, QFrame#ImageToolsPage {{
    background-color: {surface_1};
    border: none;
    border-radius: {radius_3}px;
}}

QFrame#InnerCard, QLabel#InnerCard, QFrame#StatsCard,
QFrame#SettingsSection, QFrame#ToolSection {{
    background-color: {surface_2};
    border: none;
    border-radius: {radius_2}px;
}}

QFrame#ToolbarSurface {{
    background-color: {surface_2};
    border: none;
    border-radius: {radius_2}px;
}}

QFrame#DragOverlay {{
    background-color: rgba(7, 17, 31, 232);
    border: 3px dashed {focus_ring};
    border-radius: {radius_3}px;
}}

QLabel#DragOverlayTitle {{
    color: {text_primary};
    font-size: 22px;
    font-weight: 700;
}}

/* Buttons use dynamic variant properties. */
QPushButton, QToolButton {{
    background-color: {surface_2};
    color: {text_primary};
    border: 1px solid {border};
    border-radius: {radius_2}px;
    padding: 8px 13px;
    font-weight: 600;
}}

QPushButton:hover, QToolButton:hover {{
    background-color: #1A304B;
    border-color: #6383A5;
}}

QPushButton:pressed, QToolButton:pressed {{
    background-color: #0E1D30;
}}

QPushButton:focus, QToolButton:focus {{
    border: 2px solid {focus_ring};
    padding: 7px 12px;
}}

QPushButton:disabled, QToolButton:disabled {{
    background-color: #0D1928;
    color: {disabled};
    border-color: #2C4159;
}}

QPushButton[variant="primary"], QToolButton[variant="primary"] {{
    background-color: {accent};
    color: #FFFFFF;
    border: 1px solid #8C80FF;
    padding: 9px 15px;
    font-weight: 700;
}}

QPushButton[variant="primary"]:hover, QToolButton[variant="primary"]:hover {{
    background-color: {accent_hover};
    border-color: #A69CFF;
}}

QPushButton[variant="primary"]:disabled, QToolButton[variant="primary"]:disabled {{
    background-color: #25344A;
    color: {disabled};
    border-color: #3D526B;
}}

QPushButton[variant="secondary"], QToolButton[variant="secondary"] {{
    background-color: {surface_2};
    color: {text_primary};
    border: 1px solid {border};
}}

QPushButton[variant="ghost"], QToolButton[variant="ghost"] {{
    background-color: transparent;
    color: {text_secondary};
    border: 1px solid transparent;
}}

QPushButton[variant="ghost"]:hover, QToolButton[variant="ghost"]:hover {{
    background-color: {surface_2};
    color: {text_primary};
    border-color: {border};
}}

QPushButton[variant="danger"], QToolButton[variant="danger"] {{
    background-color: transparent;
    color: {text_secondary};
    border: 1px solid transparent;
}}

QPushButton[variant="danger"]:hover, QToolButton[variant="danger"]:hover {{
    background-color: #3C202C;
    color: #FFD5DA;
    border-color: {danger};
}}

QPushButton[variant="success"] {{
    background-color: #164A3F;
    color: #A9FFE2;
    border: 1px solid #3B9E85;
}}

QPushButton[variant="mode"] {{
    background-color: transparent;
    color: {text_secondary};
    border: 1px solid transparent;
    border-radius: {radius_2}px;
    padding: 7px 14px;
}}

QPushButton[variant="mode"]:hover {{
    background-color: {surface_2};
    color: {text_primary};
}}

QPushButton[variant="mode"]:checked {{
    background-color: {surface_2};
    color: {text_primary};
    border-color: {border};
}}

QPushButton[variant="link"] {{
    background-color: transparent;
    color: {focus_ring};
    border: none;
    padding: 4px 0;
    text-align: left;
}}

QPushButton[variant="link"]:hover {{
    color: #B8F3FF;
    text-decoration: underline;
}}

/* Inputs */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: #091625;
    color: {text_primary};
    border: 1px solid {border};
    border-radius: {radius_2}px;
    padding: 7px 10px;
    selection-background-color: {accent};
}}

QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{
    border-color: #6584A4;
}}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 2px solid {focus_ring};
    padding: 6px 9px;
}}

QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{
    background-color: #0B1725;
    color: {disabled};
    border-color: #30445B;
}}

QComboBox::drop-down {{
    border: none;
    width: 28px;
}}

QComboBox::down-arrow {{
    image: url("{chevron_down}");
    width: 14px;
    height: 14px;
}}

QComboBox QAbstractItemView {{
    background-color: {surface_2};
    color: {text_primary};
    border: 1px solid {border};
    border-radius: {radius_2}px;
    padding: 4px;
    selection-background-color: {selection};
}}

QComboBox[compact="true"] {{
    padding: 4px 26px 4px 8px;
    min-height: 24px;
    font-size: {secondary}px;
    font-weight: 650;
}}

QComboBox[overridden="true"] {{
    color: #D9D2FF;
    border-color: #9589FF;
    background-color: #282050;
}}

QCheckBox, QRadioButton {{
    color: {text_primary};
    spacing: 8px;
}}

QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    background-color: #091625;
    border: 1px solid #65809E;
    border-radius: 4px;
}}

QRadioButton::indicator {{
    border-radius: 8px;
}}

QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {focus_ring};
}}

QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background-color: {accent};
    border-color: #A89DFF;
}}

QCheckBox:focus, QRadioButton:focus {{
    color: {focus_ring};
}}

QGroupBox {{
    background-color: {surface_2};
    border: none;
    border-radius: {radius_2}px;
    margin-top: 12px;
    padding: 15px 10px 10px 10px;
    color: {text_primary};
    font-weight: 650;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 9px;
    padding: 0 4px;
    color: {text_secondary};
}}

QSlider::groove:horizontal {{
    height: 6px;
    background: #2C4059;
    border-radius: 3px;
}}

QSlider::sub-page:horizontal {{
    background: {accent};
    border-radius: 3px;
}}

QSlider::handle:horizontal {{
    background: #FFFFFF;
    border: 2px solid {accent};
    width: 16px;
    margin: -6px 0;
    border-radius: 9px;
}}

/* Empty state and drag target */
QFrame#DropZone {{
    background-color: #0A192A;
    border: 2px dashed #587694;
    border-radius: {radius_3}px;
}}

QFrame#DropZone:hover {{
    background-color: #0E2238;
    border-color: {focus_ring};
}}

QFrame#DropZone[dragActive="true"] {{
    background-color: #102A44;
    border-color: {focus_ring};
}}

/* Table and list views */
QTableView, QTableWidget, QListWidget {{
    background-color: #091625;
    alternate-background-color: #0B192A;
    color: {text_primary};
    border: none;
    border-radius: {radius_2}px;
    gridline-color: transparent;
    selection-background-color: {selection};
    selection-color: {text_primary};
}}

QTableView::item, QTableWidget::item {{
    border-bottom: 1px solid #294058;
    padding: 5px 8px;
}}

QTableView::item:selected, QTableWidget::item:selected,
QListWidget::item:selected {{
    background-color: {selection};
    color: {text_primary};
}}

QTableView:focus, QTableWidget:focus, QListWidget:focus {{
    border: 2px solid {focus_ring};
}}

QHeaderView::section {{
    background-color: {surface_1};
    color: {text_secondary};
    padding: 9px 10px;
    border: none;
    border-bottom: 1px solid {border};
    font-size: {eyebrow}px;
    font-weight: 700;
}}

QListWidget::item {{
    background-color: {surface_2};
    border: 1px solid transparent;
    border-radius: {radius_2}px;
    padding: 7px;
    margin: 3px;
}}

QListWidget::item:hover {{
    border-color: {border};
}}

/* Settings tabs */
QTabWidget::pane {{
    border: none;
    background-color: transparent;
    top: -1px;
}}

QTabBar::tab {{
    background-color: transparent;
    color: {text_secondary};
    padding: 9px 12px;
    border: none;
    border-bottom: 2px solid transparent;
    font-size: {secondary}px;
    font-weight: 650;
}}

QTabBar::tab:hover {{
    color: {text_primary};
}}

QTabBar::tab:selected {{
    color: {text_primary};
    border-bottom: 2px solid {accent};
}}

QTabBar::tab:disabled {{
    color: {disabled};
}}

QTabBar:focus {{
    border-bottom: 2px solid {focus_ring};
}}

QProgressBar {{
    background-color: #091625;
    color: {text_primary};
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
}}

QProgressBar::chunk {{
    background-color: {accent};
    border-radius: 4px;
}}

/* Scrollbars */
QScrollBar:vertical {{
    background: transparent;
    width: 9px;
    margin: 2px;
}}

QScrollBar::handle:vertical {{
    background: #496782;
    min-height: 24px;
    border-radius: 4px;
}}

QScrollBar::handle:vertical:hover {{
    background: #6485A4;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    height: 0;
    background: transparent;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 9px;
}}

QScrollBar::handle:horizontal {{
    background: #496782;
    min-width: 24px;
    border-radius: 4px;
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    width: 0;
    background: transparent;
}}

QSplitter::handle:horizontal {{
    background: transparent;
    width: 10px;
}}

QSplitter::handle:horizontal:hover {{
    background: #2C425B;
    border-radius: 4px;
}}
"""

DARK_STYLESHEET = QSS_TEMPLATE.format(**TOKENS)


def apply_theme(target) -> None:
    """Install the one centralized stylesheet on an app or top-level widget."""
    target.setStyleSheet(DARK_STYLESHEET)


def repolish(widget: QWidget) -> None:
    """Refresh QSS after changing a dynamic property."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def set_variant(widget: QWidget, variant: str) -> None:
    widget.setProperty("variant", variant)
    repolish(widget)


def set_eyebrow(label: QLabel) -> None:
    """Apply accessible eyebrow typography without unsupported QSS spacing."""
    label.setProperty("role", "eyebrow")
    font = QFont(label.font())
    font.setPointSize(TYPE_SCALE["eyebrow"])
    font.setWeight(QFont.Weight.DemiBold)
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.1)
    label.setFont(font)


def icon(name: str) -> QIcon:
    return QIcon(str(ASSET_DIR / f"{name}.svg"))
