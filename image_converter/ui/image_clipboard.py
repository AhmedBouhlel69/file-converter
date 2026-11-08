"""Prepare full-size cutouts off-thread, then publish on the GUI thread.

Also reads images *from* the clipboard (screenshots, copied pictures, copied
files) so they can be pasted straight into a queue.
"""

from __future__ import annotations

import os
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QMimeData, QObject, QRunnable, Signal, QUrl
from PySide6.QtGui import QImage, QImageReader

MAX_CLIPBOARD_PIXELS = 120_000_000
MAX_PASTE_BYTES = 25 * 1024 * 1024
PASTE_IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".jpe", ".png", ".webp", ".bmp", ".dib", ".tif", ".tiff"})
PASTE_MAX_AGE_SECONDS = 2 * 24 * 3600


def file_signature(path: Path) -> tuple[int, int, int, int]:
    """Detect removal/replacement while a copy request is being prepared."""
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


@dataclass(frozen=True)
class ClipboardImage:
    path: Path
    signature: tuple[int, int, int, int]
    image: QImage
    png: QByteArray


def load_clipboard_image(path: Path) -> ClipboardImage:
    """Decode the actual PNG/WebP export without preview scaling/checkerboard.

    This function performs I/O, decoding and encoding and belongs in a worker.
    QImage/QByteArray are value objects; no widgets or clipboard are used here.
    """
    signature = file_signature(path)
    contents = QByteArray(path.read_bytes())
    buffer = QBuffer(contents)
    if not buffer.open(QIODevice.OpenModeFlag.ReadOnly):
        raise ValueError("Could not read the saved cutout")
    reader = QImageReader(buffer)
    reader.setAutoTransform(True)
    if bytes(reader.format()).lower() not in (b"png", b"webp"):
        raise ValueError("The saved cutout is not a readable PNG or WebP image")
    size = reader.size()
    if not size.isValid() or size.width() * size.height() > MAX_CLIPBOARD_PIXELS:
        raise ValueError("The saved cutout exceeds the 120 megapixel copy limit")
    image = reader.read()
    if image.isNull():
        raise ValueError(f"Could not read the saved cutout: {reader.errorString()}")
    png = QByteArray()
    encoded = QBuffer(png)
    if not encoded.open(QIODevice.OpenModeFlag.WriteOnly) or not image.save(encoded, "PNG"):
        raise ValueError("Could not prepare the cutout for copying")
    if file_signature(path) != signature:
        raise ValueError("The saved cutout changed while preparing to copy; try again")
    return ClipboardImage(path, signature, image, png)


def clipboard_mime_data(result: ClipboardImage) -> QMimeData:
    """Build clipboard formats on the GUI thread; QClipboard takes ownership.

    Qt maps the image to native DIB/DIBV5 and local URLs to Windows CF_HDROP.
    Explicit PNG bytes additionally preserve alpha for PNG-aware paste targets.
    """
    mime = QMimeData()
    mime.setData("image/png", result.png)
    mime.setImageData(result.image)
    mime.setUrls([QUrl.fromLocalFile(str(result.path))])
    if os.name == "nt":
        # QMimeData's documented platform-specific format name exposes the
        # registered Windows PNG format alongside Qt's native image formats.
        mime.setData('application/x-qt-windows-mime;value="PNG"', result.png)
    return mime


def paste_directory() -> Path:
    """Private scratch folder for images pasted from the clipboard."""
    folder = Path(tempfile.gettempdir()) / "UniversalFileConverter" / "pasted"
    folder.mkdir(parents=True, exist_ok=True)
    try:
        folder.chmod(0o700)
    except OSError:
        pass
    return folder


def is_pasted_file(path: Path) -> bool:
    try:
        return path.resolve().parent == paste_directory().resolve()
    except OSError:
        return False


def discard_pasted_file(path: Path) -> None:
    """Delete a scratch copy; never touches a file outside the paste folder."""
    try:
        if is_pasted_file(path):
            path.unlink(missing_ok=True)
    except OSError:
        pass


def purge_stale_pasted_files(max_age_seconds: float = PASTE_MAX_AGE_SECONDS) -> int:
    """Remove scratch copies left behind by earlier sessions (they can be private)."""
    removed = 0
    cutoff = time.time() - max_age_seconds
    try:
        for entry in paste_directory().iterdir():
            try:
                if entry.is_file() and entry.stat().st_mtime < cutoff:
                    entry.unlink()
                    removed += 1
            except OSError:
                continue
    except OSError:
        pass
    return removed


def _unique_paste_path(suffix: str, folder: Path | None = None) -> Path:
    folder = folder or paste_directory()
    stamp = datetime.now().strftime("pasted-%Y%m%d-%H%M%S")
    candidate, number = folder / f"{stamp}{suffix}", 1
    while candidate.exists():
        number += 1
        candidate = folder / f"{stamp}-{number}{suffix}"
    return candidate


def save_pasted_image(image: QImage, folder: Path | None = None) -> Path:
    """Write a pasted bitmap to ``folder`` (default: the scratch folder); return its path.

    PNG keeps transparency and is lossless. A very large opaque picture that would
    exceed the 25 MiB processing limit as PNG is stored as high-quality JPEG instead.
    """
    if image.isNull():
        raise ValueError("The clipboard image is empty or unreadable")
    if image.width() * image.height() > MAX_CLIPBOARD_PIXELS:
        raise ValueError("The clipboard image exceeds the 120 megapixel limit")
    if folder is not None:
        folder.mkdir(parents=True, exist_ok=True)
    target = _unique_paste_path(".png", folder)
    if not image.save(str(target), "PNG"):
        target.unlink(missing_ok=True)
        raise ValueError("Could not save the clipboard image")
    if target.stat().st_size > MAX_PASTE_BYTES and not image.hasAlphaChannel():
        jpeg = target.with_suffix(".jpg")
        if image.convertToFormat(QImage.Format.Format_RGB888).save(str(jpeg), "JPEG", 95):
            target.unlink(missing_ok=True)
            target = jpeg
    return target


@dataclass(frozen=True)
class ClipboardContent:
    """What a clipboard/drop payload offers, in order of preference."""

    files: list[Path] = field(default_factory=list)
    image: QImage | None = None

    @property
    def empty(self) -> bool:
        return not self.files and self.image is None


def inspect_mime(
    mime: QMimeData, suffixes: frozenset[str] | None = PASTE_IMAGE_SUFFIXES
) -> ClipboardContent:
    """Find pasteable content: copied files, then a bitmap, then pasted paths.

    ``suffixes`` limits which copied files count; ``None`` accepts any file.
    Qt returns ``None`` when the clipboard is empty or locked by another program.

    Copied files win over bitmap data because the original file keeps its quality
    and name. Nothing here touches the disk beyond checking that paths exist.
    """
    if mime is None:
        return ClipboardContent()
    files: list[Path] = []
    if mime.hasUrls():
        for url in mime.urls():
            if not url.isLocalFile():
                continue
            candidate = Path(url.toLocalFile())
            try:
                if candidate.is_dir() or (
                    candidate.is_file() and (suffixes is None or candidate.suffix.lower() in suffixes)
                ):
                    files.append(candidate)
            except OSError:
                continue
    if files:
        return ClipboardContent(files=files)
    if mime.hasImage():
        image = QImage(mime.imageData())
        if not image.isNull():
            return ClipboardContent(image=image)
    if mime.hasText():
        for line in mime.text().splitlines()[:50]:
            text = line.strip().strip('"')
            if not text or len(text) > 1024:
                continue
            try:
                candidate = Path(text).expanduser()
                if candidate.is_file() and (suffixes is None or candidate.suffix.lower() in suffixes):
                    files.append(candidate)
            except (OSError, ValueError):
                continue
    return ClipboardContent(files=files)


class PasteSignals(QObject):
    done = Signal(object, str)  # saved Path or None, error text


class PasteTask(QRunnable):
    """Encode a pasted bitmap off the GUI thread."""

    def __init__(self, image: QImage, folder: Path | None = None) -> None:
        super().__init__()
        self.image = image
        self.folder = folder
        self.signals = PasteSignals()

    def run(self) -> None:
        path, error = None, ""
        try:
            path = save_pasted_image(self.image, self.folder)
        except Exception as exc:  # reported to the user, never raised in a pool thread
            error = str(exc) or "Could not paste the image"
        self.signals.done.emit(path, error)
