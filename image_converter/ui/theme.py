"""
Modern dark styling and CSS theme for Image Converter.
"""

DARK_STYLESHEET = """
QMainWindow {
    background-color: #0f1117;
    color: #f3f4f6;
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
    font-size: 13px;
}

QWidget {
    background-color: transparent;
    color: #f3f4f6;
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
}

/* Scrollbars */
QScrollBar:vertical {
    background: #181b22;
    width: 8px;
    margin: 0;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #374151;
    min-height: 20px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #4b5563;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar:horizontal {
    background: #181b22;
    height: 8px;
    margin: 0;
    border-radius: 4px;
}
QScrollBar::handle:horizontal {
    background: #374151;
    min-width: 20px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal:hover {
    background: #4b5563;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* Card Frames */
QFrame#CardFrame {
    background-color: #1a1d26;
    border: 1px solid #282c38;
    border-radius: 10px;
}

QFrame#DropZone {
    background-color: #141720;
    border: 2px dashed #3e4458;
    border-radius: 12px;
}
QFrame#DropZone:hover {
    background-color: #191e2b;
    border-color: #6366f1;
}

/* Push Buttons */
QPushButton {
    background-color: #232734;
    color: #e5e7eb;
    border: 1px solid #363b4d;
    border-radius: 6px;
    padding: 7px 14px;
    font-weight: 500;
}
QPushButton:hover {
    background-color: #2b3040;
    border-color: #4b5563;
}
QPushButton:pressed {
    background-color: #1e212b;
}
QPushButton:disabled {
    background-color: #181a22;
    color: #6b7280;
    border-color: #252834;
}

QPushButton#PrimaryButton {
    background-color: #6366f1;
    color: #ffffff;
    border: 1px solid #4f46e5;
    font-weight: 600;
    font-size: 14px;
    padding: 10px 20px;
    border-radius: 8px;
}
QPushButton#PrimaryButton:hover {
    background-color: #4f46e5;
    border-color: #4338ca;
}
QPushButton#PrimaryButton:pressed {
    background-color: #3730a3;
}
QPushButton#PrimaryButton:disabled {
    background-color: #312e81;
    color: #9ca3af;
    border-color: #312e81;
}

QPushButton#SecondaryButton {
    background-color: #242836;
    color: #e0e7ff;
    border: 1px solid #3c4257;
    font-weight: 500;
    padding: 8px 14px;
    border-radius: 6px;
}
QPushButton#SecondaryButton:hover {
    background-color: #2e3447;
    border-color: #6366f1;
}

QPushButton#DangerButton {
    background-color: #2a1b1e;
    color: #f87171;
    border: 1px solid #451a20;
    border-radius: 6px;
    padding: 6px 12px;
}
QPushButton#DangerButton:hover {
    background-color: #3b1e22;
    border-color: #ef4444;
}

QPushButton#SuccessButton {
    background-color: #064e3b;
    color: #6ee7b7;
    border: 1px solid #047857;
    border-radius: 6px;
    padding: 8px 14px;
}
QPushButton#SuccessButton:hover {
    background-color: #047857;
    color: #ffffff;
}

/* Combo Box */
QComboBox {
    background-color: #222633;
    color: #f3f4f6;
    border: 1px solid #363b4d;
    border-radius: 6px;
    padding: 6px 12px;
    min-width: 100px;
}
QComboBox:hover {
    border-color: #6366f1;
}
QComboBox::drop-down {
    border: none;
    padding-right: 8px;
}
QComboBox QAbstractItemView {
    background-color: #1a1d26;
    color: #f3f4f6;
    border: 1px solid #363b4d;
    selection-background-color: #6366f1;
    selection-color: #ffffff;
    border-radius: 6px;
    padding: 4px;
}

/* Line Edit & Spin Box */
QLineEdit, QSpinBox, QDoubleSpinBox {
    background-color: #222633;
    color: #f3f4f6;
    border: 1px solid #363b4d;
    border-radius: 6px;
    padding: 6px 10px;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #6366f1;
}

/* Slider */
QSlider::groove:horizontal {
    height: 6px;
    background: #282c38;
    border-radius: 3px;
}
QSlider::sub-page:horizontal {
    background: #6366f1;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #ffffff;
    border: 2px solid #6366f1;
    width: 16px;
    margin-top: -5px;
    margin-bottom: -5px;
    border-radius: 8px;
}
QSlider::handle:horizontal:hover {
    background: #e0e7ff;
    border-color: #4f46e5;
}

/* Checkbox & Radio Button */
QCheckBox, QRadioButton {
    spacing: 8px;
    color: #e5e7eb;
}
QCheckBox::indicator, QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border-radius: 3px;
    border: 1px solid #4b5563;
    background-color: #222633;
}
QRadioButton::indicator {
    border-radius: 8px;
}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {
    border-color: #6366f1;
}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    background-color: #6366f1;
    border-color: #4f46e5;
}

/* Table Widget */
QTableWidget {
    background-color: #141720;
    alternate-background-color: #171b25;
    border: 1px solid #282c38;
    border-radius: 8px;
    gridline-color: #222633;
    selection-background-color: #2d3345;
    selection-color: #ffffff;
}
QTableWidget::item {
    padding: 6px 8px;
    border-bottom: 1px solid #1e222e;
}
QTableWidget::item:selected {
    background-color: #2a3144;
}
QHeaderView::section {
    background-color: #1c202b;
    color: #9ca3af;
    padding: 8px 10px;
    border: none;
    border-bottom: 2px solid #282c38;
    font-weight: 600;
    font-size: 11px;
    text-transform: uppercase;
}

/* Progress Bar */
QProgressBar {
    background-color: #1e222e;
    border: 1px solid #2d3345;
    border-radius: 6px;
    height: 14px;
    text-align: center;
    color: #f3f4f6;
    font-size: 11px;
    font-weight: 600;
}
QProgressBar::chunk {
    background-color: #6366f1;
    border-radius: 5px;
}

/* Group Box */
QGroupBox {
    border: 1px solid #2c3140;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 14px;
    font-weight: 600;
    color: #cbd5e1;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    background-color: #1a1d26;
    color: #a5b4fc;
}

/* Labels */
QLabel {
    color: #e5e7eb;
}
QLabel#MutedLabel {
    color: #9ca3af;
    font-size: 12px;
}
QLabel#HeaderLabel {
    font-size: 18px;
    font-weight: 700;
    color: #ffffff;
}
QLabel#SectionTitle {
    font-size: 14px;
    font-weight: 600;
    color: #e0e7ff;
}
"""
