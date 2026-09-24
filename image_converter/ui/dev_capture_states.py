"""Capture deterministic offscreen screenshots of the redesigned UI states.

Run from the repository root:
    python -m image_converter.ui.dev_capture_states
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# This must be configured before any Qt import.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import fitz
from docx import Document
from openpyxl import Workbook
from PIL import Image, ImageDraw
from PySide6.QtCore import QThreadPool
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from image_converter.ui.main_window import ImageConverterMainWindow
from image_converter.ui.theme import apply_theme, set_variant


def _load_offscreen_font() -> None:
    """The Windows offscreen platform does not always discover system fonts."""
    if sys.platform == "win32":
        segoe = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "segoeui.ttf"
        if segoe.exists():
            QFontDatabase.addApplicationFont(str(segoe))


def _create_samples(folder: Path) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)

    image_path = folder / "campaign-hero.png"
    image = Image.new("RGB", (1280, 720), "#6654E8")
    draw = ImageDraw.Draw(image)
    draw.rectangle((90, 90, 1190, 630), outline="#67DFFF", width=12)
    image.save(image_path)

    pdf_path = folder / "quarterly-report.pdf"
    pdf = fitz.open()
    for number in range(1, 4):
        page = pdf.new_page()
        page.insert_text((72, 96), f"Quarterly report — page {number}", fontsize=20)
    pdf.save(pdf_path)
    pdf.close()

    document_path = folder / "meeting-notes.docx"
    document = Document()
    document.add_heading("Meeting notes", level=1)
    document.add_paragraph("A representative document used for UI state capture.")
    document.save(document_path)

    sheet_path = folder / "regional-sales.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Region", "Revenue"])
    sheet.append(["North", 42000])
    sheet.append(["South", 37000])
    workbook.save(sheet_path)

    return [image_path, pdf_path, document_path, sheet_path]


def _settle(app: QApplication, milliseconds: int = 250) -> None:
    app.processEvents()
    QTest.qWait(milliseconds)
    app.processEvents()


def capture_states(output_dir: Path, width: int = 1380, height: int = 860) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    _load_offscreen_font()
    apply_theme(app)

    window = ImageConverterMainWindow()
    window.resize(width, height)
    window.show()
    captured: list[Path] = []

    def capture(name: str) -> None:
        _settle(app)
        window.repaint()
        app.processEvents()
        destination = output_dir / f"{name}.png"
        if not window.grab().save(str(destination)):
            raise RuntimeError(f"Could not save {destination}")
        captured.append(destination)

    capture("01-empty")

    window.drag_overlay.setGeometry(window.centralWidget().rect().adjusted(4, 4, -4, -4))
    window.drag_overlay.show()
    window.drag_overlay.raise_()
    capture("02-drag-over")
    window.drag_overlay.hide()

    samples = _create_samples(output_dir / "samples")
    window.add_images(samples)
    _settle(app, 1100)
    capture("03-populated-mixed")

    window.queue_table.selectRow(0)
    _settle(app)
    capture("04-row-selected")
    window._show_batch_settings()

    model = window.queue_table.queue_model
    window._is_converting = True
    window._footer_state = "converting"
    window._active_rows = list(range(model.rowCount()))
    for row in range(model.rowCount()):
        model.update_status(row, "Converting" if row == 0 else "Queued", progress=36 if row == 0 else 0)
    window._set_queue_editing_enabled(False)
    window.progress_bar.setValue(36)
    window.progress_bar.show()
    window.lbl_status.setText(f"Converting 1 of {model.rowCount()} files · 36%")
    window.lbl_status_hint.setText("Cancel stops after the current file finishes.")
    window._refresh_queue_ui(update_status=False)
    capture("05-converting")

    window._is_converting = False
    window._footer_state = "completed"
    window._set_queue_editing_enabled(True)
    for row, entry in enumerate(model.entries):
        model.update_status(row, "Done", progress=100)
        model.update_output_size(row, max(1, int(entry.input_size * 0.72)))
    window.progress_bar.hide()
    window.btn_open_folder.show()
    window.btn_convert_more.show()
    window.lbl_status.setText(f"{model.rowCount()} converted · 1.4 MB → 980 KB")
    window.lbl_status_hint.setText("Completed in 1.42s. Your originals were not changed.")
    window._refresh_queue_ui(update_status=False)
    capture("06-completed")

    model.update_status(0, "Failed", progress=0, error="The sample file could not be decoded.")
    window._footer_state = "partial_failure"
    window.btn_open_folder.setVisible(model.rowCount() > 1)
    window.lbl_status.setText(f"{model.rowCount() - 1} converted · 1 failed")
    window.lbl_status_hint.setText("Select a failed status to retry.")
    set_variant(window.btn_convert_all, "primary")
    window._refresh_queue_ui(update_status=False)
    capture("07-error")

    window._set_app_mode(1)
    capture("08-pdf-tools")

    window.close()
    QThreadPool.globalInstance().waitForDone(3000)
    app.processEvents()
    return captured


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("scratch") / "ui-state-captures",
        help="Directory for PNG captures and generated sample files.",
    )
    parser.add_argument("--width", type=int, default=1380, help="Logical capture width.")
    parser.add_argument("--height", type=int, default=860, help="Logical capture height.")
    args = parser.parse_args()
    for path in capture_states(args.output.resolve(), args.width, args.height):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
