"""
Stats and conversion metrics display widget.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from image_converter.ui.components import format_bytes
from image_converter.ui.theme import repolish


class StatsCard(QFrame):
    """Card displaying a single metric title and highlighted value."""

    def __init__(self, title: str, initial_val: str = "-", icon: str = "📈", parent=None):
        super().__init__(parent)
        self.setObjectName("StatsCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        head_layout = QHBoxLayout()
        icon_lbl = QLabel(icon)
        icon_lbl.setProperty("role", "metricIcon")
        head_layout.addWidget(icon_lbl)

        title_lbl = QLabel(title)
        title_lbl.setProperty("role", "metricTitle")
        head_layout.addWidget(title_lbl)
        head_layout.addStretch()
        layout.addLayout(head_layout)

        self.val_lbl = QLabel(initial_val)
        self.val_lbl.setProperty("role", "metricValue")
        layout.addWidget(self.val_lbl)

    def set_value(self, val: str, color_hex: str | None = None):
        self.val_lbl.setText(val)
        state = ""
        if color_hex in {"#55e0b4", "#34d399"}:
            state = "success"
        elif color_hex in {"#ff8291", "#f87171"}:
            state = "error"
        elif color_hex in {"#f2c66d", "#fbbf24"}:
            state = "warning"
        elif color_hex:
            state = "accent"
        self.val_lbl.setProperty("state", state)
        repolish(self.val_lbl)


class StatsWidget(QFrame):
    """Panel displaying summary cards and statistics of conversion batches."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("InspectorContent")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 4, 2, 4)
        layout.setSpacing(10)

        title = QLabel("Latest results")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        self.lbl_subtitle = QLabel("Complete a batch to see success rate, speed, and storage impact.")
        self.lbl_subtitle.setObjectName("MutedLabel")
        self.lbl_subtitle.setWordWrap(True)
        layout.addWidget(self.lbl_subtitle)

        # 2x3 Grid of Metric Cards
        grid = QGridLayout()
        grid.setSpacing(10)

        self.card_succeeded = StatsCard("Successful", "0", "✓")
        self.card_failed = StatsCard("Needs attention", "0", "!")
        self.card_time = StatsCard("Elapsed", "0.0s", "◷")
        self.card_in_size = StatsCard("Input", "0 B", "↓")
        self.card_out_size = StatsCard("Output", "0 B", "↑")
        self.card_savings = StatsCard("Space saved", "0 B (0%)", "◇")

        grid.addWidget(self.card_succeeded, 0, 0)
        grid.addWidget(self.card_failed, 0, 1)
        grid.addWidget(self.card_time, 1, 0)
        grid.addWidget(self.card_savings, 1, 1)
        grid.addWidget(self.card_in_size, 2, 0)
        grid.addWidget(self.card_out_size, 2, 1)

        layout.addLayout(grid)

        # Details / Breakdown box
        self.details_box = QFrame()
        self.details_box.setObjectName("InnerCard")
        det_layout = QVBoxLayout(self.details_box)
        det_layout.setContentsMargins(8, 8, 8, 8)
        det_layout.setSpacing(6)

        det_title = QLabel("Batch summary")
        det_title.setObjectName("SectionTitle")
        self.lbl_highlights = QLabel("No batches executed in this session yet.")
        self.lbl_highlights.setObjectName("MutedLabel")
        self.lbl_highlights.setWordWrap(True)

        det_layout.addWidget(det_title)
        det_layout.addWidget(self.lbl_highlights)
        layout.addWidget(self.details_box)

        layout.addStretch()

    def update_stats(
        self,
        success_count: int,
        fail_count: int,
        elapsed_sec: float,
        in_bytes: int,
        out_bytes: int,
    ):
        self.card_succeeded.set_value(str(success_count), "#55e0b4" if success_count > 0 else None)
        self.card_failed.set_value(str(fail_count), "#ff8291" if fail_count > 0 else None)
        self.card_time.set_value(f"{elapsed_sec:.2f}s", "#68d7ff")
        self.card_in_size.set_value(format_bytes(in_bytes))
        self.card_out_size.set_value(format_bytes(out_bytes))

        delta = in_bytes - out_bytes
        if in_bytes > 0:
            pct = (delta / in_bytes) * 100.0
            if delta > 0:
                self.card_savings.set_value(f"-{format_bytes(delta)} ({pct:.1f}%)", "#55e0b4")
            elif delta < 0:
                self.card_savings.set_value(f"+{format_bytes(-delta)}", "#f2c66d")
            else:
                self.card_savings.set_value("0 B (0%)", None)
        else:
            self.card_savings.set_value("0 B (0%)", None)

        speed_mb = (in_bytes / (1024 * 1024)) / elapsed_sec if elapsed_sec > 0 else 0
        self.lbl_highlights.setText(
            f"Converted {success_count} file(s) with {fail_count} failure(s).\n"
            f"Average throughput: ~{speed_mb:.2f} MB/s.\n"
            f"Net size change: {format_bytes(abs(delta))} "
            f"({'reduced' if delta >= 0 else 'expanded'})."
        )
