"""Model/view queue with asynchronous presentation-only file analysis."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

import fitz
from PIL import Image
from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QPoint,
    QRect,
    QRunnable,
    QSize,
    Qt,
    QThreadPool,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QMenu,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
)

from image_converter.core.engine import get_file_metadata
from image_converter.ui.components import get_compatible_output_formats, format_bytes
from image_converter.ui.theme import (
    ACCENT,
    BORDER,
    DANGER,
    FOCUS_RING,
    SUCCESS,
    SURFACE_2,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    WARNING,
)

logger = logging.getLogger(__name__)


@dataclass
class QueueEntry:
    path: Path
    target_format: str
    default_format: str
    status: str = "Queued"
    progress: int = 0
    input_size: int = 0
    detail: str = "Analyzing…"
    thumbnail: Optional[QImage] = None
    estimated_size: Optional[int] = None
    output_size: Optional[int] = None
    error: str = ""
    overridden: bool = False

    @property
    def display_size(self) -> str:
        if self.output_size is not None:
            return format_bytes(self.output_size)
        if self.estimated_size is not None:
            return f"~{format_bytes(self.estimated_size)}"
        return "—"

    @property
    def secondary_text(self) -> str:
        file_type = self.path.suffix.lstrip(".").upper() or "FILE"
        parts = [file_type, format_bytes(self.input_size)]
        if self.detail and self.detail != "Analyzing…":
            parts.append(self.detail)
        return " · ".join(parts)


class AnalysisSignals(QObject):
    finished = Signal(str, object)
    failed = Signal(str, str)


class FileAnalysisTask(QRunnable):
    """Load dimensions/page counts and thumbnails away from the GUI thread."""

    def __init__(self, path: Path):
        super().__init__()
        # The model owns the runnable until its queued signal is delivered.
        self.setAutoDelete(False)
        self.path = path
        self.signals = AnalysisSignals()

    def run(self):
        key = str(self.path.resolve())
        try:
            result = {"detail": "", "thumbnail": None}
            ext = self.path.suffix.lower()
            meta = get_file_metadata(self.path)

            if ext == ".pdf":
                page_count = int(meta.get("page_count", 0))
                result["detail"] = f"{page_count} page{'s' if page_count != 1 else ''}"
                with fitz.open(str(self.path)) as document:
                    if document.page_count:
                        pix = document[0].get_pixmap(dpi=42, alpha=False)
                        image = QImage(
                            pix.samples,
                            pix.width,
                            pix.height,
                            pix.stride,
                            QImage.Format.Format_RGB888,
                        )
                        result["thumbnail"] = image.copy()
            elif ext in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif", ".ico", ".heic", ".heif"}:
                width = int(meta.get("width", 0))
                height = int(meta.get("height", 0))
                result["detail"] = f"{width}×{height}" if width and height else "Image"
                with Image.open(self.path) as pil_image:
                    pil_image.thumbnail((72, 72), Image.Resampling.LANCZOS)
                    rgba = pil_image.convert("RGBA")
                    raw = rgba.tobytes("raw", "RGBA")
                    image = QImage(
                        raw,
                        rgba.width,
                        rgba.height,
                        rgba.width * 4,
                        QImage.Format.Format_RGBA8888,
                    )
                    result["thumbnail"] = image.copy()
            elif ext in {".docx", ".doc", ".odt", ".rtf", ".txt"}:
                words = int(meta.get("word_count", meta.get("words", 0)) or 0)
                result["detail"] = f"{words:,} words" if words else "Document"
            elif ext in {".xlsx", ".xls", ".csv"}:
                rows = int(meta.get("rows", 0) or 0)
                cols = int(meta.get("cols", 0) or 0)
                result["detail"] = f"{rows:,} rows × {cols} cols" if rows or cols else "Spreadsheet"
            elif ext == ".pptx":
                slides = int(meta.get("slide_count", 0) or 0)
                result["detail"] = f"{slides} slide{'s' if slides != 1 else ''}"
            else:
                result["detail"] = "File"

        except Exception as exc:  # A queue row must remain usable if preview analysis fails.
            logger.debug("Queue analysis failed for %s: %s", self.path, exc)
            try:
                self.signals.failed.emit(key, str(exc))
            except RuntimeError:
                pass  # The window may have closed while analysis was finishing.
            return
        try:
            self.signals.finished.emit(key, result)
        except RuntimeError:
            pass  # The window may have closed while analysis was finishing.


class QueueTableModel(QAbstractTableModel):
    StatusColumn, PreviewColumn, FileColumn, TargetColumn, SizeColumn = range(5)

    EntryRole = Qt.ItemDataRole.UserRole + 1
    PathRole = Qt.ItemDataRole.UserRole + 2
    FormatsRole = Qt.ItemDataRole.UserRole + 3
    OverriddenRole = Qt.ItemDataRole.UserRole + 4
    ProgressRole = Qt.ItemDataRole.UserRole + 5

    count_changed = Signal(int)
    totals_changed = Signal(int, object)
    analysis_finished = Signal(int)

    HEADERS = ("Status", "Preview", "File", "Convert to", "Est. size")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.entries: List[QueueEntry] = []
        self.default_format = "JPG"
        self.quality = 90
        self._pool = QThreadPool.globalInstance()
        self._analysis_tasks: set[FileAnalysisTask] = set()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.entries)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(self.HEADERS):
                return self.HEADERS[section]
        return None

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self.entries)):
            return None
        entry = self.entries[index.row()]

        if role == self.EntryRole:
            return entry
        if role == self.PathRole:
            return str(entry.path)
        if role == self.FormatsRole:
            return get_compatible_output_formats(entry.path)
        if role == self.OverriddenRole:
            return entry.overridden
        if role == self.ProgressRole:
            return entry.progress
        if role == Qt.ItemDataRole.ToolTipRole:
            if entry.error:
                return f"{entry.path}\n\n{entry.error}"
            return str(entry.path)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if index.column() in (self.StatusColumn, self.PreviewColumn, self.TargetColumn, self.SizeColumn):
                return Qt.AlignmentFlag.AlignCenter

        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            column = index.column()
            if column == self.StatusColumn:
                return entry.status
            if column == self.FileColumn:
                return entry.path.name
            if column == self.TargetColumn:
                return entry.target_format
            if column == self.SizeColumn:
                return entry.display_size
        if role == Qt.ItemDataRole.DecorationRole and index.column() == self.PreviewColumn:
            return entry.thumbnail
        return None

    def flags(self, index: QModelIndex):
        flags = super().flags(index) | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
        if index.column() == self.TargetColumn:
            flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    def setData(self, index: QModelIndex, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid() or index.column() != self.TargetColumn:
            return False
        entry = self.entries[index.row()]
        new_target = str(value).upper()
        if new_target not in get_compatible_output_formats(entry.path):
            return False
        entry.target_format = new_target
        default_target = entry.default_format if self.default_format == "PER_FILE" else self.default_format
        entry.overridden = new_target != default_target
        self._estimate_entry(entry)
        self.dataChanged.emit(index, index, [role, self.OverriddenRole])
        self._emit_totals()
        return True

    @property
    def file_paths(self) -> List[Path]:
        return [entry.path for entry in self.entries]

    def entry(self, row: int) -> Optional[QueueEntry]:
        return self.entries[row] if 0 <= row < len(self.entries) else None

    def add_paths(self, paths: Iterable[Path], target_format: Optional[str] = None) -> List[int]:
        existing = {str(entry.path.resolve()).casefold() for entry in self.entries}
        added: List[Path] = []
        for raw_path in paths:
            path = Path(raw_path)
            if not path.is_file():
                continue
            key = str(path.resolve()).casefold()
            if key not in existing:
                existing.add(key)
                added.append(path)
        if not added:
            return []

        start = len(self.entries)
        end = start + len(added) - 1
        self.beginInsertRows(QModelIndex(), start, end)
        for path in added:
            requested = (target_format or self.default_format).upper()
            compatible = get_compatible_output_formats(path)
            selected = requested if requested in compatible else (compatible[0] if compatible else "JPG")
            entry = QueueEntry(
                path=path,
                target_format=selected,
                default_format=selected if self.default_format == "PER_FILE" else self.default_format,
                input_size=path.stat().st_size,
                overridden=False if self.default_format == "PER_FILE" else selected != self.default_format,
            )
            self._estimate_entry(entry)
            self.entries.append(entry)
        self.endInsertRows()
        self.count_changed.emit(len(self.entries))
        self._emit_totals()

        for row in range(start, end + 1):
            self._start_analysis(self.entries[row])
        return list(range(start, end + 1))

    def remove_rows(self, rows: Iterable[int]) -> List[int]:
        valid = sorted({row for row in rows if 0 <= row < len(self.entries)}, reverse=True)
        for row in valid:
            self.beginRemoveRows(QModelIndex(), row, row)
            self.entries.pop(row)
            self.endRemoveRows()
        if valid:
            self.count_changed.emit(len(self.entries))
            self._emit_totals()
        return sorted(valid)

    def clear(self):
        if not self.entries:
            return
        self.beginResetModel()
        self.entries.clear()
        self.endResetModel()
        self.count_changed.emit(0)
        self._emit_totals()

    def set_default_format(self, target_format: str):
        self.default_format = target_format.upper()
        for entry in self.entries:
            if self.default_format == "PER_FILE":
                entry.default_format = entry.target_format
                entry.overridden = False
                self._estimate_entry(entry)
                continue
            compatible = get_compatible_output_formats(entry.path)
            if not entry.overridden and self.default_format in compatible:
                entry.target_format = self.default_format
            entry.default_format = self.default_format
            entry.overridden = entry.target_format != self.default_format
            self._estimate_entry(entry)
        if self.entries:
            self.dataChanged.emit(
                self.index(0, self.TargetColumn),
                self.index(len(self.entries) - 1, self.SizeColumn),
            )
        self._emit_totals()

    def set_quality(self, quality: int):
        self.quality = max(1, min(100, int(quality)))
        for entry in self.entries:
            self._estimate_entry(entry)
        if self.entries:
            self.dataChanged.emit(
                self.index(0, self.SizeColumn),
                self.index(len(self.entries) - 1, self.SizeColumn),
            )
        self._emit_totals()

    def update_status(self, row: int, status: str, progress: Optional[int] = None, error: str = ""):
        entry = self.entry(row)
        if not entry:
            return
        entry.status = status
        if progress is not None:
            entry.progress = progress
        if error:
            entry.error = error
        index = self.index(row, self.StatusColumn)
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole, self.ProgressRole])

    def update_output_size(self, row: int, size_bytes: int):
        entry = self.entry(row)
        if not entry:
            return
        entry.output_size = size_bytes
        index = self.index(row, self.SizeColumn)
        self.dataChanged.emit(index, index)
        self._emit_totals()

    def reset_run_state(self):
        for entry in self.entries:
            entry.status = "Queued"
            entry.progress = 0
            entry.output_size = None
            entry.error = ""
        if self.entries:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.entries) - 1, self.SizeColumn))
        self._emit_totals()

    def input_total(self) -> int:
        return sum(entry.input_size for entry in self.entries)

    def estimated_total(self) -> Optional[int]:
        estimates = [entry.output_size if entry.output_size is not None else entry.estimated_size for entry in self.entries]
        return sum(estimates) if estimates and all(value is not None for value in estimates) else None

    def compatible_format_intersection(self) -> List[str]:
        if not self.entries:
            return []
        ordered = get_compatible_output_formats(self.entries[0].path)
        allowed = set(ordered)
        for entry in self.entries[1:]:
            allowed &= set(get_compatible_output_formats(entry.path))
        return [fmt for fmt in ordered if fmt in allowed]

    def has_images(self) -> bool:
        return any(entry.path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif", ".ico", ".heic", ".heif"} for entry in self.entries)

    def has_documents(self) -> bool:
        return any(entry.path.suffix.lower() in {".pdf", ".doc", ".docx", ".odt", ".rtf", ".txt", ".pptx", ".xls", ".xlsx", ".csv"} for entry in self.entries)

    def _estimate_entry(self, entry: QueueEntry):
        target = entry.target_format.upper()
        ratios = {
            "JPG": 0.42,
            "JPEG": 0.42,
            "WEBP": 0.30,
            "HEIC": 0.28,
            "PNG": 0.95,
            "BMP": 2.1,
            "TIFF": 1.25,
            "GIF": 0.75,
            "ICO": 0.25,
            "PDF": 1.05,
            "DOCX": 0.82,
            "XLSX": 0.85,
            "CSV": 0.55,
            "TXT": 0.25,
            "JSON": 0.45,
            "HTML": 0.60,
            "PPTX": 0.90,
            "ODT": 0.82,
            "RTF": 0.75,
            "STRIP_METADATA": 0.98,
            "CLEAN": 0.98,
        }
        ratio = ratios.get(target)
        if ratio is None or entry.input_size <= 0:
            entry.estimated_size = None
            return
        if target in {"JPG", "JPEG", "WEBP", "HEIC"}:
            ratio *= 0.55 + (self.quality / 100.0) * 0.55
        entry.estimated_size = max(1, int(entry.input_size * ratio))

    def _start_analysis(self, entry: QueueEntry):
        task = FileAnalysisTask(entry.path)
        self._analysis_tasks.add(task)
        task.signals.finished.connect(self._on_analysis_finished)
        task.signals.failed.connect(self._on_analysis_failed)
        self._pool.start(task)

    def _on_analysis_finished(self, key: str, result: dict):
        self._analysis_tasks = {
            task for task in self._analysis_tasks if str(task.path.resolve()) != key
        }
        for row, entry in enumerate(self.entries):
            if str(entry.path.resolve()) == key:
                entry.detail = result.get("detail") or "File"
                entry.thumbnail = result.get("thumbnail")
                self.dataChanged.emit(
                    self.index(row, self.PreviewColumn),
                    self.index(row, self.FileColumn),
                )
                self.analysis_finished.emit(row)
                break

    def _on_analysis_failed(self, key: str, _message: str):
        self._analysis_tasks = {
            task for task in self._analysis_tasks if str(task.path.resolve()) != key
        }
        for row, entry in enumerate(self.entries):
            if str(entry.path.resolve()) == key:
                entry.detail = "Details unavailable"
                self.dataChanged.emit(self.index(row, self.FileColumn), self.index(row, self.FileColumn))
                break

    def _emit_totals(self):
        self.totals_changed.emit(self.input_total(), self.estimated_total())


class FileCellDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        painter.save()
        option = QStyleOptionViewItem(option)
        self.initStyleOption(option, index)
        style = option.widget.style() if option.widget else QApplication.style()
        style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, option, painter, option.widget)

        entry: QueueEntry = index.data(QueueTableModel.EntryRole)
        rect = option.rect.adjusted(10, 6, -8, -5)
        name_font = QFont(option.font)
        name_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(name_font)
        painter.setPen(QColor(TEXT_PRIMARY))
        metrics = painter.fontMetrics()
        name = metrics.elidedText(entry.path.name, Qt.TextElideMode.ElideMiddle, rect.width())
        painter.drawText(rect.adjusted(0, 0, 0, -18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)

        secondary_font = QFont(option.font)
        secondary_font.setPointSize(max(9, secondary_font.pointSize() - 1))
        painter.setFont(secondary_font)
        painter.setPen(QColor(TEXT_SECONDARY))
        secondary = painter.fontMetrics().elidedText(entry.secondary_text, Qt.TextElideMode.ElideRight, rect.width())
        painter.drawText(rect.adjusted(0, 22, 0, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, secondary)
        painter.restore()

    def sizeHint(self, option, index):
        return QSize(260, 58)


class PreviewDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        painter.save()
        style = option.widget.style() if option.widget else QApplication.style()
        style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, option, painter, option.widget)
        image = index.data(Qt.ItemDataRole.DecorationRole)
        target = option.rect.adjusted(8, 8, -8, -8)
        if isinstance(image, QImage) and not image.isNull():
            scaled = image.scaled(target.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            x = target.x() + (target.width() - scaled.width()) // 2
            y = target.y() + (target.height() - scaled.height()) // 2
            painter.drawImage(QPoint(x, y), scaled)
        else:
            painter.setPen(QPen(QColor(BORDER), 1))
            painter.setBrush(QColor(SURFACE_2))
            painter.drawRoundedRect(target.adjusted(3, 3, -3, -3), 6, 6)
            painter.setPen(QColor(TEXT_SECONDARY))
            painter.drawText(target, Qt.AlignmentFlag.AlignCenter, "FILE")
        painter.restore()


class StatusDelegate(QStyledItemDelegate):
    COLORS = {
        "Queued": TEXT_SECONDARY,
        "Converting": FOCUS_RING,
        "Done": SUCCESS,
        "Failed": DANGER,
        "Warning": WARNING,
        "Cancelled": WARNING,
    }

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        painter.save()
        style = option.widget.style() if option.widget else QApplication.style()
        style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, option, painter, option.widget)
        status = str(index.data(Qt.ItemDataRole.DisplayRole) or "Queued")
        color = QColor(self.COLORS.get(status, TEXT_SECONDARY))
        center_y = option.rect.center().y()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(QPoint(option.rect.x() + 13, center_y), 4, 4)
        painter.setPen(color)
        label = "Failed · Retry" if status == "Failed" else status
        painter.drawText(option.rect.adjusted(23, 0, -4, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, label)

        if status == "Converting":
            progress = int(index.data(QueueTableModel.ProgressRole) or 0)
            bar = QRect(option.rect.x() + 23, option.rect.bottom() - 10, max(28, option.rect.width() - 31), 3)
            painter.fillRect(bar, QColor("#2C4059"))
            fill = QRect(bar)
            fill.setWidth(int(bar.width() * progress / 100))
            painter.fillRect(fill, QColor(ACCENT))
        painter.restore()


class TargetFormatDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        combo = QComboBox(parent)
        combo.setProperty("compact", True)
        combo.addItems(index.data(QueueTableModel.FormatsRole) or [])
        combo.currentTextChanged.connect(lambda _text: self.commitData.emit(combo))
        return combo

    def setEditorData(self, editor: QComboBox, index: QModelIndex):
        editor.setCurrentText(str(index.data(Qt.ItemDataRole.EditRole)))
        editor.setProperty("overridden", bool(index.data(QueueTableModel.OverriddenRole)))
        editor.style().unpolish(editor)
        editor.style().polish(editor)

    def setModelData(self, editor: QComboBox, model, index):
        model.setData(index, editor.currentText(), Qt.ItemDataRole.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect.adjusted(3, 7, -3, -7))

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        painter.save()
        style = option.widget.style() if option.widget else QApplication.style()
        style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, option, painter, option.widget)
        overridden = bool(index.data(QueueTableModel.OverriddenRole))
        rect = option.rect.adjusted(5, 9, -5, -9)
        painter.setPen(QPen(QColor("#9589FF" if overridden else BORDER), 1))
        painter.setBrush(QColor("#282050" if overridden else SURFACE_2))
        painter.drawRoundedRect(rect, 7, 7)
        painter.setPen(QColor("#E3DDFF" if overridden else TEXT_PRIMARY))
        painter.drawText(rect.adjusted(9, 0, -20, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, str(index.data()))
        painter.setPen(QPen(QColor(TEXT_SECONDARY), 1.4))
        x = rect.right() - 11
        y = rect.center().y()
        painter.drawLine(x - 3, y - 2, x, y + 1)
        painter.drawLine(x, y + 1, x + 3, y - 2)
        painter.restore()


class QueueTableView(QTableView):
    """Five-column queue view with compatibility helpers for the existing glue."""

    item_selected = Signal(str)
    item_removed = Signal(int)
    tool_merge_requested = Signal(list)
    tool_split_requested = Signal(object)
    tool_organize_requested = Signal(object)
    tool_compress_requested = Signal(object)
    tool_image_compress_requested = Signal(list)
    retry_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.queue_model = QueueTableModel(self)
        self.setModel(self.queue_model)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.CurrentChanged
            | QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(58)
        self.horizontalHeader().setStretchLastSection(False)
        self.horizontalHeader().setSectionResizeMode(self.queue_model.StatusColumn, self.horizontalHeader().ResizeMode.Fixed)
        self.horizontalHeader().setSectionResizeMode(self.queue_model.PreviewColumn, self.horizontalHeader().ResizeMode.Fixed)
        self.horizontalHeader().setSectionResizeMode(self.queue_model.FileColumn, self.horizontalHeader().ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(self.queue_model.TargetColumn, self.horizontalHeader().ResizeMode.Fixed)
        self.horizontalHeader().setSectionResizeMode(self.queue_model.SizeColumn, self.horizontalHeader().ResizeMode.ResizeToContents)
        self.setColumnWidth(self.queue_model.StatusColumn, 112)
        self.setColumnWidth(self.queue_model.PreviewColumn, 74)
        self.setColumnWidth(self.queue_model.TargetColumn, 118)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setItemDelegateForColumn(self.queue_model.StatusColumn, StatusDelegate(self))
        self.setItemDelegateForColumn(self.queue_model.PreviewColumn, PreviewDelegate(self))
        self.setItemDelegateForColumn(self.queue_model.FileColumn, FileCellDelegate(self))
        self.setItemDelegateForColumn(self.queue_model.TargetColumn, TargetFormatDelegate(self))
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self.setAccessibleName("Conversion queue")
        self.setAccessibleDescription("Five-column list of files waiting to be converted.")

    @property
    def file_paths(self):
        return self.queue_model.file_paths

    def rowCount(self):
        return self.queue_model.rowCount()

    def columnCount(self):
        return self.queue_model.columnCount()

    def currentRow(self):
        return self.currentIndex().row()

    def add_file_item(self, file_path: Path, target_fmt: str):
        self.queue_model.add_paths([file_path], target_fmt)

    add_image_item = add_file_item

    def add_files(self, paths: Iterable[Path], target_fmt: str):
        return self.queue_model.add_paths(paths, target_fmt)

    def get_selected_rows(self) -> List[int]:
        return sorted({index.row() for index in self.selectionModel().selectedRows()})

    def get_selected_file_paths(self) -> List[Path]:
        return [self.file_paths[row] for row in self.get_selected_rows() if 0 <= row < len(self.file_paths)]

    def get_target_format_for_row(self, row: int) -> str:
        entry = self.queue_model.entry(row)
        return entry.target_format if entry else "JPG"

    def set_target_format_for_row(self, row: int, target_fmt: str):
        self.queue_model.setData(self.queue_model.index(row, self.queue_model.TargetColumn), target_fmt)

    def set_target_format_all(self, target_fmt: str):
        self.queue_model.set_default_format(target_fmt)

    def update_status(self, row: int, status: str, _color_hex: str = ""):
        normalized = {
            "Queued": "Queued",
            "Working": "Converting",
            "Done": "Done",
            "Warning": "Warning",
            "Failed": "Failed",
        }.get(status, status)
        self.queue_model.update_status(row, normalized)

    def update_converted_size(self, row: int, size_bytes: int):
        self.queue_model.update_output_size(row, size_bytes)

    def clear_all(self):
        self.queue_model.clear()

    def remove_selected_rows(self) -> List[int]:
        rows = self.get_selected_rows()
        if not rows and self.currentRow() >= 0:
            rows = [self.currentRow()]
        removed = self.queue_model.remove_rows(rows)
        for row in removed:
            self.item_removed.emit(row)
        return removed

    def remove_selected_row(self):
        self.remove_selected_rows()

    def mouseReleaseEvent(self, event):
        index = self.indexAt(event.position().toPoint())
        if index.isValid() and index.column() == self.queue_model.StatusColumn:
            entry = self.queue_model.entry(index.row())
            if entry and entry.status == "Failed":
                self.retry_requested.emit(index.row())
                event.accept()
                return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        index = self.currentIndex()
        if (
            index.isValid()
            and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space)
            and self.queue_model.entry(index.row()).status == "Failed"
        ):
            self.retry_requested.emit(index.row())
            event.accept()
            return
        super().keyPressEvent(event)

    def _on_selection_changed(self, *_args):
        row = self.currentRow()
        if 0 <= row < len(self.file_paths):
            self.item_selected.emit(str(self.file_paths[row]))

    def _show_context_menu(self, pos: QPoint):
        index = self.indexAt(pos)
        if not index.isValid():
            return
        row = index.row()
        if row not in self.get_selected_rows():
            self.selectRow(row)
        selected = self.get_selected_file_paths()
        path = self.queue_model.entry(row).path
        menu = QMenu(self)
        open_location = menu.addAction("Open file location")
        copy_path = menu.addAction("Copy full path")
        inspect = menu.addAction("Inspect file")
        menu.addSeparator()
        retry = None
        if self.queue_model.entry(row).status == "Failed":
            retry = menu.addAction("Retry conversion")
        split = organize = compress = image_compress = None
        if len(selected) == 1 and path.suffix.lower() == ".pdf":
            split = menu.addAction("Split PDF…")
            organize = menu.addAction("Organize pages…")
            compress = menu.addAction("Compress PDF…")
        image_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif", ".ico", ".heic", ".heif"}
        selected_images = [candidate for candidate in selected if candidate.suffix.lower() in image_exts]
        if selected_images:
            image_compress = menu.addAction(
                f"Compress {len(selected_images)} image{'s' if len(selected_images) != 1 else ''}…"
            )
        merge = menu.addAction(f"Merge {len(selected)} selected file{'s' if len(selected) != 1 else ''}…")
        menu.addSeparator()
        remove = menu.addAction("Remove from queue")
        chosen = menu.exec(self.viewport().mapToGlobal(pos))
        if chosen == open_location:
            import os
            os.startfile(str(path.parent))
        elif chosen == copy_path:
            QApplication.clipboard().setText(str(path))
        elif chosen == inspect:
            self.item_selected.emit(str(path))
        elif retry and chosen == retry:
            self.retry_requested.emit(row)
        elif split and chosen == split:
            self.tool_split_requested.emit(path)
        elif organize and chosen == organize:
            self.tool_organize_requested.emit(path)
        elif compress and chosen == compress:
            self.tool_compress_requested.emit(path)
        elif image_compress and chosen == image_compress:
            self.tool_image_compress_requested.emit(selected_images)
        elif chosen == merge:
            self.tool_merge_requested.emit(selected)
        elif chosen == remove:
            self.remove_selected_rows()
