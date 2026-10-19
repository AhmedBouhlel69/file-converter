"""Dedicated local background-removal workspace."""

from __future__ import annotations

from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, QUrl, Signal
from PySide6.QtGui import (
    QAction, QColor, QDesktopServices, QImage, QImageReader, QKeySequence,
    QPainter, QShortcut,
)
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QProgressBar, QPushButton, QScrollArea, QSizePolicy,
    QSpinBox, QSplitter, QVBoxLayout, QWidget,
)

from image_converter.core.background_removal import (
    BackgroundRemovalConfig, IMAGE_EXTENSIONS, MODEL_PROFILES, plan_tasks,
)
from image_converter.ui.background_worker import BackgroundRemovalWorker
from image_converter.ui.image_clipboard import (
    clipboard_mime_data, file_signature, load_clipboard_image,
)
from image_converter.ui.theme import repolish, set_eyebrow, set_variant


class _PreviewSignals(QObject):
    ready = Signal(int, QImage)


class _PreviewTask(QRunnable):
    def __init__(self, generation, path, cancelled):
        super().__init__()
        self.generation, self.path, self.cancelled = generation, path, cancelled
        self.signals = _PreviewSignals()

    def run(self):
        image = QImage()
        reader = None
        try:
            if not self.cancelled.is_set() and self.path.is_file():
                reader = QImageReader(str(self.path))
                reader.setAutoTransform(True)
                size = reader.size()
                if size.isValid() and size.width() * size.height() <= 120_000_000:
                    reader.setScaledSize(size.scaled(QSize(1200, 900), Qt.AspectRatioMode.KeepAspectRatio))
                    image = reader.read()
        except OSError:
            pass
        finally:
            # Release the file handle before notifying the UI. Windows can
            # otherwise reject moving/deleting an already displayed preview.
            reader = None
            self.signals.ready.emit(self.generation, image)


class _CopySignals(QObject):
    ready = Signal(int, object, str)


class _CopyTask(QRunnable):
    def __init__(self, generation, path):
        super().__init__()
        self.generation, self.path = generation, path
        self.signals = _CopySignals()

    def run(self):
        result, error = None, ""
        try:
            result = load_clipboard_image(self.path)
        except Exception as exc:
            error = str(exc) or "Could not read the saved cutout"
        self.signals.ready.emit(self.generation, result, error)


class CutoutPreview(QFrame):
    """Bounded preview with a checkerboard that makes transparency visible."""

    def __init__(self, placeholder: str, parent=None):
        super().__init__(parent)
        self.placeholder = placeholder
        self.image = QImage()
        self._generation = 0
        self._cancel_preview = Event()
        self._tasks = {}
        self._loading = False
        self.setMinimumSize(160, 150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAccessibleName(placeholder)

    def set_path(self, path: Path | None):
        self._cancel_preview.set()
        self._cancel_preview = Event()
        self._generation += 1
        self.image = QImage()
        self._loading = path is not None
        if path:
            task = _PreviewTask(self._generation, path, self._cancel_preview)
            self._tasks[self._generation] = task
            task.signals.ready.connect(self._preview_ready)
            QThreadPool.globalInstance().start(task)
        self.update()

    def _preview_ready(self, generation, image):
        self._tasks.pop(generation, None)
        if generation == self._generation:
            self._loading = False
            self.image = image
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#13243A"))
        if self.image.isNull():
            painter.setPen(QColor("#B8C7D9"))
            painter.drawText(self.rect().adjusted(15, 10, -15, -10),
                             Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                             "Loading preview…" if self._loading else self.placeholder)
            return
        size = self.image.size().scaled(self.size() - QSize(20, 20), Qt.AspectRatioMode.KeepAspectRatio)
        x, y = (self.width() - size.width()) // 2, (self.height() - size.height()) // 2
        painter.save()
        painter.setClipRect(x, y, size.width(), size.height())
        for row in range(y, y + size.height(), 14):
            for column in range(x, x + size.width(), 14):
                color = "#D2D8E1" if ((row - y) // 14 + (column - x) // 14) % 2 else "#F0F3F7"
                painter.fillRect(column, row, 14, 14, QColor(color))
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(x, y, self.image.scaled(size, Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation))
        painter.restore()


class BackgroundRemovalPage(QFrame):
    queue_requested = Signal()
    busy_changed = Signal(bool)

    IMAGE_FILTER = "Images (*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff)"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("BackgroundRemovalPage")
        self.setAcceptDrops(True)
        self.files: list[Path] = []
        self.outputs: dict[Path, Path] = {}
        self.worker: BackgroundRemovalWorker | None = None
        self.tasks = []
        self._results = []
        self._cancelled = False
        self._last_output: Path | None = None
        self._copy_generation = 0
        self._copy_tasks = {}
        self._copy_busy = False
        self._copy_errors: set[Path] = set()
        self.start_guard = None
        self._build_ui()

    @property
    def is_running(self) -> bool:
        return self.worker is not None

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(12)
        eyebrow = QLabel("IMAGE STUDIO")
        set_eyebrow(eyebrow)
        title = QLabel("Background removal")
        title.setObjectName("AppTitle")
        subtitle = QLabel("Create clean cutouts locally. Drop JPEG, PNG, WebP, BMP, or TIFF images here.")
        subtitle.setObjectName("MutedLabel")
        subtitle.setWordWrap(True)
        layout.addWidget(eyebrow)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        queue = QFrame()
        queue.setObjectName("WorkspaceCard")
        left = QVBoxLayout(queue)
        left.setContentsMargins(14, 14, 14, 14)
        heading = QHBoxLayout()
        label = QLabel("Image queue")
        label.setObjectName("SectionTitle")
        self.count_label = QLabel("0 IMAGES")
        self.count_label.setObjectName("CountBadge")
        heading.addWidget(label)
        heading.addStretch()
        heading.addWidget(self.count_label)
        left.addLayout(heading)
        add_row = QHBoxLayout()
        self.btn_add = QPushButton("Add images")
        self.btn_add.clicked.connect(self.browse_images)
        self.btn_queue = QPushButton("Use conversion queue")
        self.btn_queue.clicked.connect(self.queue_requested.emit)
        set_variant(self.btn_add, "secondary")
        set_variant(self.btn_queue, "ghost")
        add_row.addWidget(self.btn_add)
        add_row.addWidget(self.btn_queue)
        left.addLayout(add_row)
        self.file_list = QListWidget()
        self.file_list.setAccessibleName("Background removal image queue")
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.file_list.setWordWrap(True)
        self.file_list.currentRowChanged.connect(self._show_selection)
        left.addWidget(self.file_list, stretch=1)
        remove_row = QHBoxLayout()
        self.btn_remove = QPushButton("Remove selected")
        self.btn_remove.clicked.connect(self.remove_selected)
        self.btn_clear = QPushButton("Clear")
        self.btn_clear.clicked.connect(self.clear_files)
        set_variant(self.btn_remove, "ghost")
        set_variant(self.btn_clear, "danger")
        remove_row.addWidget(self.btn_remove)
        remove_row.addStretch()
        remove_row.addWidget(self.btn_clear)
        left.addLayout(remove_row)
        hint = QLabel("Up to 25 MiB and 120 megapixels per image. Originals stay untouched.")
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        left.addWidget(hint)
        splitter.addWidget(queue)

        workspace = QWidget()
        right = QVBoxLayout(workspace)
        right.setContentsMargins(0, 0, 0, 0)
        previews = QHBoxLayout()
        for name, attribute, placeholder in (
            ("ORIGINAL", "before_preview", "Select an image to preview"),
            ("RESULT", "after_preview", "Your cutout will appear here"),
        ):
            card = QFrame()
            card.setObjectName("WorkspaceCard")
            card_layout = QVBoxLayout(card)
            caption = QLabel(name)
            set_eyebrow(caption)
            preview = CutoutPreview(placeholder)
            setattr(self, attribute, preview)
            caption_row = QHBoxLayout()
            caption_row.addWidget(caption)
            caption_row.addStretch()
            if attribute == "after_preview":
                self.btn_copy = QPushButton("Copy image")
                self.btn_copy.setEnabled(False)
                self.btn_copy.setToolTip("Copy the full-size cutout, including transparency (Ctrl+C)")
                set_variant(self.btn_copy, "secondary")
                self.btn_copy.clicked.connect(self.copy_result)
                caption_row.addWidget(self.btn_copy)
            card_layout.addLayout(caption_row)
            card_layout.addWidget(preview, stretch=1)
            previews.addWidget(card)
        self.after_preview.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.after_preview.setToolTip("Copy image with Ctrl+C or right-click")
        self.after_preview.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        self.copy_action = QAction("Copy image", self.after_preview)
        self.copy_action.setEnabled(False)
        self.copy_action.triggered.connect(self.copy_result)
        self.after_preview.addAction(self.copy_action)
        self._copy_shortcuts = []
        for widget in (self.after_preview, self.file_list):
            shortcut = QShortcut(QKeySequence.StandardKey.Copy, widget)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.setEnabled(False)
            shortcut.activated.connect(self.copy_result)
            self._copy_shortcuts.append(shortcut)
        right.addLayout(previews, stretch=3)

        self.settings = QFrame()
        self.settings.setObjectName("WorkspaceCard")
        options = QVBoxLayout(self.settings)
        options.setAlignment(Qt.AlignmentFlag.AlignTop)
        grid = QGridLayout()
        self.combo_model = QComboBox()
        for profile in MODEL_PROFILES:
            self.combo_model.addItem(profile.title(), profile)
        self.combo_format = QComboBox()
        self.combo_format.addItems(["PNG", "WEBP"])
        grid.addWidget(QLabel("Model"), 0, 0)
        grid.addWidget(self.combo_model, 0, 1)
        grid.addWidget(QLabel("Output"), 0, 2)
        grid.addWidget(self.combo_format, 0, 3)
        self.model_hint = QLabel()
        self.model_hint.setObjectName("MutedLabel")
        self.model_hint.setWordWrap(True)
        self.combo_model.currentIndexChanged.connect(self._update_model_hint)
        self._update_model_hint()
        grid.addWidget(self.model_hint, 1, 0, 1, 4)
        self.txt_output = QLineEdit()
        self.txt_output.setPlaceholderText("Same folder as each source image")
        self.txt_output.setAccessibleName("Background removal output folder")
        browse_output = QPushButton("Browse…")
        browse_output.clicked.connect(self._browse_output)
        grid.addWidget(QLabel("Save to"), 2, 0)
        grid.addWidget(self.txt_output, 2, 1, 1, 2)
        grid.addWidget(browse_output, 2, 3)
        options.addLayout(grid)
        toggles = QHBoxLayout()
        self.chk_mask = QCheckBox("Also save mask")
        self.chk_metadata = QCheckBox("Keep EXIF metadata")
        toggles.addWidget(self.chk_mask)
        toggles.addWidget(self.chk_metadata)
        toggles.addStretch()
        options.addLayout(toggles)
        self.btn_advanced = QPushButton("Show advanced settings")
        self.btn_advanced.setCheckable(True)
        set_variant(self.btn_advanced, "ghost")
        options.addWidget(self.btn_advanced, alignment=Qt.AlignmentFlag.AlignLeft)
        self.advanced = QWidget()
        advanced = QGridLayout(self.advanced)
        advanced.setContentsMargins(0, 0, 0, 0)
        self.spin_feather = QDoubleSpinBox()
        self.spin_feather.setRange(0, 20)
        self.spin_feather.setSingleStep(0.2)
        self.spin_edge = QSpinBox()
        self.spin_edge.setRange(-5, 5)
        self.chk_two_pass = QCheckBox("Two-pass refinement")
        self.chk_crop = QCheckBox("Crop to subject")
        self.spin_padding = QSpinBox()
        self.spin_padding.setRange(0, 2000)
        self.spin_padding.setSuffix(" px")
        self.txt_fill = QLineEdit()
        self.txt_fill.setPlaceholderText("Transparent (or #ffffff)")
        self.txt_model_dir = QLineEdit()
        self.txt_model_dir.setPlaceholderText("Automatic: local, bundled, or cache")
        browse_model = QPushButton("Browse…")
        browse_model.clicked.connect(self._browse_models)
        advanced.addWidget(QLabel("Feather"), 0, 0)
        advanced.addWidget(self.spin_feather, 0, 1)
        advanced.addWidget(QLabel("Edge shift"), 0, 2)
        advanced.addWidget(self.spin_edge, 0, 3)
        advanced.addWidget(self.chk_two_pass, 1, 0, 1, 2)
        advanced.addWidget(self.chk_crop, 1, 2)
        advanced.addWidget(self.spin_padding, 1, 3)
        advanced.addWidget(QLabel("Background"), 2, 0)
        advanced.addWidget(self.txt_fill, 2, 1, 1, 3)
        advanced.addWidget(QLabel("Model folder"), 3, 0)
        advanced.addWidget(self.txt_model_dir, 3, 1, 1, 2)
        advanced.addWidget(browse_model, 3, 3)
        self.advanced.hide()
        self.btn_advanced.toggled.connect(self._toggle_advanced)
        options.addWidget(self.advanced)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.settings)
        scroll.setMinimumHeight(215)
        right.addWidget(scroll, stretch=2)
        splitter.addWidget(workspace)
        splitter.setSizes([340, 940])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter, stretch=1)

        footer = QFrame()
        footer.setObjectName("WorkspaceCard")
        bottom = QHBoxLayout(footer)
        status_layout = QVBoxLayout()
        self.lbl_status = QLabel("Add images to get started")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setObjectName("StatusLabel")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setMaximumHeight(12)
        self.progress.hide()
        status_layout.addWidget(self.lbl_status)
        status_layout.addWidget(self.progress)
        bottom.addLayout(status_layout, stretch=1)
        self.btn_open = QPushButton("Open output folder")
        self.btn_open.setEnabled(False)
        self.btn_open.clicked.connect(self.open_output_folder)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.cancel)
        self.btn_cancel.hide()
        self.btn_start = QPushButton("Remove background")
        set_variant(self.btn_start, "primary")
        self.btn_start.setEnabled(False)
        self.btn_start.clicked.connect(self.start)
        bottom.addWidget(self.btn_open)
        bottom.addWidget(self.btn_cancel)
        bottom.addWidget(self.btn_start)
        layout.addWidget(footer)

    def _toggle_advanced(self, checked):
        self.advanced.setVisible(checked)
        self.btn_advanced.setText("Hide advanced settings" if checked else "Show advanced settings")

    def _update_model_hint(self, *_args):
        if self.combo_model.currentData() in ("quality", "portrait"):
            self.model_hint.setText(
                "Quality and Portrait require at least 8 GiB of free RAM. "
                "Choose Fast or Balanced when memory is limited."
            )
        else:
            self.model_hint.setText(
                "Efficient local processing: 2 CPU threads. "
                "The model is released after each batch. Fast uses the least RAM."
            )

    def browse_images(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Choose images for background removal", "", self.IMAGE_FILTER)
        self.add_files([Path(path) for path in files])

    def _browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Save cutouts to", self.txt_output.text())
        if folder:
            self.txt_output.setText(folder)

    def _browse_models(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose installed model folder", self.txt_model_dir.text())
        if folder:
            self.txt_model_dir.setText(folder)

    def add_files(self, paths):
        if self.is_running:
            return
        known = {path.resolve() for path in self.files}
        ignored = 0
        for raw in paths:
            path = Path(raw)
            candidates = sorted(path.rglob("*")) if path.is_dir() else [path]
            for candidate in candidates:
                if not candidate.is_file() or candidate.suffix.lower() not in IMAGE_EXTENSIONS:
                    ignored += 1
                    continue
                resolved = candidate.resolve()
                if resolved in known:
                    continue
                known.add(resolved)
                self.files.append(resolved)
                item = QListWidgetItem(f"{resolved.name}\nQueued")
                item.setToolTip(str(resolved))
                item.setSizeHint(QSize(220, 70))
                self.file_list.addItem(item)
        self._refresh_count()
        if self.file_list.currentRow() < 0 and self.files:
            self.file_list.setCurrentRow(0)
        if ignored:
            self._set_status("Some files were skipped. Use JPEG, PNG, WebP, BMP, or TIFF.", "warning")

    def _refresh_count(self):
        count = len(self.files)
        self.count_label.setText(f"{count} IMAGE{'S' if count != 1 else ''}")
        self.btn_start.setEnabled(bool(count) and not self.is_running)
        self._set_status(f"{count} image{'s' if count != 1 else ''} ready · Transparent PNG or lossless WebP" if count else "Add images to get started")

    def remove_selected(self):
        if self.is_running:
            return
        rows = sorted({self.file_list.row(item) for item in self.file_list.selectedItems()}, reverse=True)
        for row in rows:
            self.outputs.pop(self.files.pop(row), None)
            self.file_list.takeItem(row)
        self._refresh_count()
        self._show_selection(self.file_list.currentRow())

    def clear_files(self):
        if self.is_running:
            return
        self.files.clear()
        self.outputs.clear()
        self.file_list.clear()
        self._refresh_count()
        self._show_selection(-1)

    def _show_selection(self, row):
        self._copy_generation += 1
        self._copy_busy = False
        source = self.files[row] if 0 <= row < len(self.files) else None
        self.before_preview.set_path(source)
        self.after_preview.set_path(self.outputs.get(source))
        self._refresh_copy()

    def _selected_output(self):
        row = self.file_list.currentRow()
        source = self.files[row] if 0 <= row < len(self.files) else None
        path = self.outputs.get(source)
        try:
            return path if path and path.is_file() else None
        except OSError:
            return None

    def _refresh_copy(self):
        path = self._selected_output()
        enabled = bool(path and path not in self._copy_errors and not self._copy_busy)
        self.btn_copy.setEnabled(enabled)
        self.btn_copy.setText("Copying…" if self._copy_busy else "Copy image")
        self.copy_action.setEnabled(enabled)
        for shortcut in self._copy_shortcuts:
            shortcut.setEnabled(enabled)

    def copy_result(self):
        """Copy only the selected source's current successful saved output."""
        path = self._selected_output()
        if path is None or path in self._copy_errors or self._copy_busy:
            self._refresh_copy()
            return
        self._copy_generation += 1
        generation = self._copy_generation
        self._copy_busy = True
        self._refresh_copy()
        self._set_status("Preparing the full-size image for copying…")
        task = _CopyTask(generation, path)
        self._copy_tasks[generation] = task
        task.signals.ready.connect(self._copy_ready)
        QThreadPool.globalInstance().start(task)

    def _copy_ready(self, generation, result, error):
        task = self._copy_tasks.pop(generation, None)
        if generation != self._copy_generation:
            return
        self._copy_busy = False
        path = self._selected_output()
        if task is None:
            self._refresh_copy()
            return
        if path != task.path:
            self._set_status("Could not copy image. The saved cutout is no longer available.", "error")
            self._refresh_copy()
            return
        if not error:
            try:
                if result is None or file_signature(path) != result.signature:
                    error = "The saved cutout changed while preparing to copy; try again"
            except OSError:
                error = "The saved cutout is no longer available"
        if error:
            self._copy_errors.add(path)
            self._set_status(f"Could not copy image. {error}", "error")
        else:
            QApplication.clipboard().setMimeData(clipboard_mime_data(result))
            self._set_status("Copied image. Paste with Ctrl+V.", "success")
        self._refresh_copy()

    def _set_status(self, message, state=""):
        self.lbl_status.setText(message)
        self.lbl_status.setProperty("state", state)
        repolish(self.lbl_status)

    def _config(self):
        return BackgroundRemovalConfig(
            model=self.combo_model.currentData(),
            model_dir=self.txt_model_dir.text().strip() or None,
            output_format=self.combo_format.currentText(),
            bg_color=self.txt_fill.text().strip() or None,
            crop=self.chk_crop.isChecked(), padding=self.spin_padding.value(),
            feather=self.spin_feather.value(), edge_shift=self.spin_edge.value(),
            two_pass=self.chk_two_pass.isChecked(), save_mask=self.chk_mask.isChecked(),
            keep_metadata=self.chk_metadata.isChecked(),
        )

    def start(self):
        if self.is_running or not self.files:
            return
        if self.start_guard is not None:
            blocked = self.start_guard()
            if blocked:
                self._set_status(blocked, "warning")
                return
        try:
            config = self._config()
            self.tasks = plan_tasks(self.files, self.txt_output.text().strip() or None,
                                    config.output_format, save_mask=config.save_mask)
        except Exception as exc:
            self._set_status(str(exc), "error")
            return
        self._results = []
        self._cancelled = False
        self.outputs.clear()
        self._copy_errors.clear()
        self._show_selection(self.file_list.currentRow())
        for index, path in enumerate(self.files):
            self.file_list.item(index).setText(f"{path.name}\nQueued")
        self.worker = BackgroundRemovalWorker(self.tasks, config, self)
        self.worker.file_completed.connect(self._file_completed)
        self.worker.progress_updated.connect(self._progress_updated)
        self.worker.batch_completed.connect(self._batch_completed)
        self.worker.finished.connect(self._worker_finished)
        self._set_busy(True)
        self.progress.setRange(0, 0)
        self.progress.show()
        self._set_status("Loading model and removing backgrounds…")
        self.worker.start()

    def _set_busy(self, busy):
        for widget in (self.btn_add, self.btn_queue, self.btn_remove, self.btn_clear, self.settings):
            widget.setEnabled(not busy)
        self.btn_start.setEnabled(not busy and bool(self.files))
        self.btn_cancel.setVisible(busy)
        self.btn_cancel.setEnabled(busy)
        self.busy_changed.emit(busy)

    def _file_completed(self, index, result):
        if not 0 <= index < len(self.files):
            return
        source = self.files[index]
        item = self.file_list.item(index)
        if result.success:
            destination = Path(result.output_path)
            self._copy_errors.discard(destination)
            self.outputs[source] = destination
            self._last_output = destination.parent
            self.btn_open.setEnabled(True)
            item.setText(f"{source.name}\nDone · {destination.suffix.lstrip('.').upper()}")
            item.setToolTip(str(destination))
        else:
            self.outputs.pop(source, None)
            cancelled = self._cancelled and "cancelled" in (result.error_message or "").lower()
            item.setText(f"{source.name}\n{'Cancelled' if cancelled else 'Failed'}")
            item.setToolTip(result.error_message or "Background removal failed")
        if self.file_list.currentRow() == index:
            self._show_selection(index)

    def _progress_updated(self, completed, total):
        self.progress.setRange(0, total)
        self.progress.setValue(completed)
        if not self._cancelled:
            self._set_status(f"Processed {completed} of {total} images")

    def _batch_completed(self, results, cancelled):
        self._results, self._cancelled = results, cancelled

    def _worker_finished(self):
        worker, self.worker = self.worker, None
        if worker:
            worker.deleteLater()
        self._set_busy(False)
        self.progress.hide()
        success = sum(result.success for result in self._results)
        failures = [result for result in self._results if not result.success and not (
            self._cancelled and "cancelled" in (result.error_message or "").lower()
        )]
        completed = {Path(result.input_path).resolve() for result in self._results}
        if self._cancelled:
            for row, source in enumerate(self.files):
                if source not in completed:
                    self.file_list.item(row).setText(f"{source.name}\nCancelled")
        message = f"{'Cancelled' if self._cancelled else 'Complete'} · {success} saved · {len(failures)} failed"
        if failures:
            message += f" · {failures[0].error_message}"
        self._set_status(message, "warning" if self._cancelled or failures else "success")

    def cancel(self):
        if self.worker:
            self._cancelled = True
            self.worker.cancel()
            self.btn_cancel.setEnabled(False)
            self._set_status("Cancelling after the current image finishes…", "warning")

    def open_output_folder(self):
        if self._last_output:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_output)))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not self.is_running:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if self.is_running:
            event.ignore()
            return
        self.add_files([Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()])
        event.acceptProposedAction()
