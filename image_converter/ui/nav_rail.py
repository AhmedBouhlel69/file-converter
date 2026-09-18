"""
Navigation Rail widget for left navigation sidebar.
Provides compact and expanded states for switching main panels.
"""

from __future__ import annotations

from typing import List, Tuple
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QPushButton,
    QVBoxLayout,
)


class NavRailWidget(QFrame):
    """Vertical navigation rail with icon buttons and active state indicator."""

    tab_changed = Signal(int)  # Emits selected tab index

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NavRail")
        self.setFixedWidth(74)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(4, 12, 4, 12)
        self.layout.setSpacing(8)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True)
        self.buttons: List[QPushButton] = []

        tabs: List[Tuple[str, str, str]] = [
            ("⚙️", "Settings", "Conversion Settings and Target Formats"),
            ("🔍", "Preview", "Selected File Inspector and Metadata Preview"),
            ("📊", "Stats", "Batch Conversion Statistics and Savings"),
        ]

        for idx, (icon, label, tooltip) in enumerate(tabs):
            btn = QPushButton(f"{icon}\n{label}")
            btn.setCheckable(True)
            btn.setToolTip(tooltip)
            btn.setObjectName("NavButton")
            btn.setFixedSize(64, 56)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            
            btn.clicked.connect(lambda checked=False, i=idx: self._on_button_clicked(i))
            
            self.btn_group.addButton(btn, idx)
            self.buttons.append(btn)
            self.layout.addWidget(btn)

        if self.buttons:
            self.buttons[0].setChecked(True)

        self.layout.addStretch()

    def _on_button_clicked(self, index: int):
        self.tab_changed.emit(index)

    def set_active_tab(self, index: int):
        if 0 <= index < len(self.buttons):
            self.buttons[index].setChecked(True)
            self.tab_changed.emit(index)
