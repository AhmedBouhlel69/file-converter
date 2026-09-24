"""Top-level PDF Tools workspace using the existing PDF dialogs."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from image_converter.ui.theme import set_eyebrow, set_variant


class PdfToolsPage(QFrame):
    merge_requested = Signal()
    split_requested = Signal()
    organize_requested = Signal()
    compress_requested = Signal()

    TOOLS = (
        (
            "Merge",
            "Combine files into one PDF",
            "Arrange PDFs and images in the exact order you want, then export a single document.",
            ("PDF and image inputs", "Drag-friendly ordering", "One combined output"),
            "Open merge workspace",
            "merge_requested",
        ),
        (
            "Split",
            "Split a PDF with precision",
            "Create one file per page, fixed-size chunks, or a set of custom page ranges.",
            ("Single pages", "Every N pages", "Custom ranges"),
            "Open split workspace",
            "split_requested",
        ),
        (
            "Organize",
            "Rebuild page order visually",
            "Preview pages, move them, rotate them, duplicate them, or remove them before saving.",
            ("Page thumbnails", "Reorder and rotate", "Non-destructive save"),
            "Open page organizer",
            "organize_requested",
        ),
        (
            "Compress",
            "Reduce PDF file size",
            "Choose a balanced, maximum, or lossless profile and see the achieved reduction.",
            ("Three compression profiles", "Original stays untouched", "Clear savings report"),
            "Open compression workspace",
            "compress_requested",
        ),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PdfToolsPage")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(16)

        eyebrow = QLabel("PDF WORKSPACE")
        set_eyebrow(eyebrow)
        title = QLabel("PDF tools")
        title.setObjectName("AppTitle")
        subtitle = QLabel("Choose a focused workflow. Your existing PDF engine and output behavior stay unchanged.")
        subtitle.setObjectName("MutedLabel")
        subtitle.setWordWrap(True)
        layout.addWidget(eyebrow)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        nav_surface = QFrame()
        nav_surface.setObjectName("ToolbarSurface")
        nav_layout = QHBoxLayout(nav_surface)
        nav_layout.setContentsMargins(4, 4, 4, 4)
        nav_layout.setSpacing(4)
        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)
        self.nav_buttons = []
        for index, tool in enumerate(self.TOOLS):
            button = QPushButton(tool[0])
            button.setCheckable(True)
            button.setAccessibleName(f"{tool[0]} PDF tool")
            set_variant(button, "mode")
            button.clicked.connect(lambda _checked=False, page=index: self.set_active_tool(page))
            self.button_group.addButton(button, index)
            self.nav_buttons.append(button)
            nav_layout.addWidget(button)
        nav_layout.addStretch()
        layout.addWidget(nav_surface)

        self.stack = QStackedWidget()
        for label, heading, description, bullets, action_text, signal_name in self.TOOLS:
            self.stack.addWidget(
                self._build_tool_section(label, heading, description, bullets, action_text, signal_name)
            )
        layout.addWidget(self.stack, stretch=1)
        self.set_active_tool(0)

    def _build_tool_section(self, label, heading, description, bullets, action_text, signal_name):
        page = QWidget()
        outer = QHBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch(1)

        section = QFrame()
        section.setObjectName("ToolSection")
        section.setMaximumWidth(720)
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(28, 28, 28, 28)
        section_layout.setSpacing(12)

        eyebrow = QLabel(label.upper())
        set_eyebrow(eyebrow)
        title = QLabel(heading)
        title.setObjectName("SectionTitleLarge")
        body = QLabel(description)
        body.setObjectName("MutedLabel")
        body.setWordWrap(True)
        section_layout.addWidget(eyebrow)
        section_layout.addWidget(title)
        section_layout.addWidget(body)
        section_layout.addSpacing(8)

        for bullet in bullets:
            row = QLabel(f"•  {bullet}")
            row.setAccessibleName(bullet)
            section_layout.addWidget(row)

        section_layout.addStretch()
        action = QPushButton(action_text)
        set_variant(action, "primary")
        action.setAccessibleDescription(f"Open the {label.lower()} PDF dialog")
        signal = getattr(self, signal_name)
        action.clicked.connect(lambda _checked=False, target=signal: target.emit())
        section_layout.addWidget(action)

        outer.addWidget(section, stretch=4)
        outer.addStretch(1)
        return page

    def set_active_tool(self, index: int):
        if 0 <= index < self.stack.count():
            self.stack.setCurrentIndex(index)
            self.nav_buttons[index].setChecked(True)
