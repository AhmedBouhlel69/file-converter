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
    QHBoxLayout,
    QPushButton,
)


class NavRailWidget(QFrame):
    """Compact segmented navigation for the workspace inspector."""

    tab_changed = Signal(int)  # Emits selected tab index

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NavRail")
        self.setFixedHeight(46)

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(4, 4, 4, 4)
        self.layout.setSpacing(4)

        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True)
        self.buttons: List[QPushButton] = []

        tabs: List[Tuple[str, str, str]] = [
            ("01", "Output", "Choose output format and conversion options"),
            ("02", "Inspect", "Preview the selected file and review its metadata"),
            ("03", "Results", "Review batch results and storage savings"),
        ]

        for idx, (icon, label, tooltip) in enumerate(tabs):
            btn = QPushButton(f"{icon}  {label}")
            btn.setCheckable(True)
            btn.setToolTip(tooltip)
            btn.setAccessibleName(f"{label} inspector tab")
            btn.setObjectName("NavButton")
            btn.setMinimumHeight(36)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            
            btn.clicked.connect(lambda checked=False, i=idx: self._on_button_clicked(i))
            
            self.btn_group.addButton(btn, idx)
            self.buttons.append(btn)
            self.layout.addWidget(btn, stretch=1)

        if self.buttons:
            self.buttons[0].setChecked(True)

    def _on_button_clicked(self, index: int):
        self.tab_changed.emit(index)

    def set_active_tab(self, index: int):
        if 0 <= index < len(self.buttons):
            self.buttons[index].setChecked(True)
            self.tab_changed.emit(index)
