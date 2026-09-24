"""Top-level image tools workspace using the existing conversion engine."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from image_converter.ui.theme import set_eyebrow, set_variant


class ImageToolsPage(QFrame):
    compress_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ImageToolsPage")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(16)

        eyebrow = QLabel("IMAGE WORKSPACE")
        set_eyebrow(eyebrow)
        title = QLabel("Image tools")
        title.setObjectName("AppTitle")
        subtitle = QLabel("Compress image batches with quality, format, resize, and metadata controls.")
        subtitle.setObjectName("MutedLabel")
        subtitle.setWordWrap(True)
        layout.addWidget(eyebrow)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        content = QWidget()
        outer = QHBoxLayout(content)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch(1)

        section = QFrame()
        section.setObjectName("ToolSection")
        section.setMaximumWidth(720)
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(28, 28, 28, 28)
        section_layout.setSpacing(12)

        label = QLabel("COMPRESS")
        set_eyebrow(label)
        heading = QLabel("Reduce image file size")
        heading.setObjectName("SectionTitleLarge")
        body = QLabel(
            "Create smaller image copies with WebP, JPEG, PNG optimization, optional resizing, and metadata removal."
        )
        body.setObjectName("MutedLabel")
        body.setWordWrap(True)
        section_layout.addWidget(label)
        section_layout.addWidget(heading)
        section_layout.addWidget(body)
        section_layout.addSpacing(8)

        for bullet in ("Batch image inputs", "Quality and max-size controls", "Originals stay untouched"):
            row = QLabel(f"-  {bullet}")
            row.setAccessibleName(bullet)
            section_layout.addWidget(row)

        section_layout.addStretch()
        action = QPushButton("Open image compressor")
        set_variant(action, "primary")
        action.setAccessibleDescription("Open the image compression dialog")
        action.clicked.connect(self.compress_requested.emit)
        section_layout.addWidget(action)

        outer.addWidget(section, stretch=4)
        outer.addStretch(1)
        layout.addWidget(content, stretch=1)
