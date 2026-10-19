"""Prepare full-size cutouts off-thread, then publish on the GUI thread."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QMimeData, QUrl
from PySide6.QtGui import QImage, QImageReader

MAX_CLIPBOARD_PIXELS = 120_000_000


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
