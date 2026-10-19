# Universal File Converter

A fast, cross-platform, local desktop and CLI file conversion application built with Python, PySide6 (Qt6), PyMuPDF, python-docx, ReportLab, pandas, openpyxl, and Pillow.

Convert between **PDF, Word (DOCX), Excel (XLSX), CSV**, and **Images (HEIC, JPG, PNG, WEBP, BMP, TIFF, GIF, ICO)** locally on your machine with zero cloud upload required.

---

## Key Features

- **Wide Format Support**:
  - **Documents**: PDF, Word (`.docx`, `.doc`), Text (`.txt`), HTML
  - **Presentations & Rich Docs**: PowerPoint (`.pptx`), OpenDocument (`.odt`), Rich Text (`.rtf`)
  - **Spreadsheets & Data**: CSV (UTF-8, UTF-16, CP1252, Latin-1), Excel (`.xlsx`, `.xls`), JSON, HTML
  - **Images**: HEIC, HEIF, JPG, JPEG, PNG, WEBP, BMP, TIFF, GIF, ICO, PPM, TGA, EPS
- **Image Compression**:
  - Desktop Image Tools workspace for batch compression to WebP, JPG, PNG, or original format.
  - Quality slider, max-width/max-height resize controls, custom output folder, and optional metadata stripping.
  - CLI compression through the existing `-q`, `--width`, `--height`, and `-f WEBP` options.
- **Background Removal**:
  - Separate top-level desktop page for batch cutouts, before/after previews, local model selection, edge/crop settings, and optional mask export.
  - Transparent PNG or lossless WebP; defaults to the `fast` model on CPU.
  - Optional `backgroundG` dependency (Python 3.11+) loads only when used; existing conversion remains available without it.
- **Privacy & Complete Metadata Deletion**:
  - Strip all EXIF tags, GPS location, camera details, and comments from images (`.jpg`, `.png`, `.webp`, `.heic`, `.tiff`, `.bmp`).
  - Strip author, title, producer, timestamps, and embedded XMP streams from PDFs.
  - Clear document core properties (author, editor, company, comments) from Word (`.docx`), Excel (`.xlsx`), PowerPoint (`.pptx`), and OpenDocument (`.odt`).
  - Standalone sanitization (`--clean-metadata`), inspection (`--inspect-metadata`), and conversion stripping (`--strip-metadata`).
- **OCR Engine**: Searchable text extraction from scanned PDFs and images via Tesseract.
- **Application Icon & Desktop Shortcut**: Custom brand icon (`app_icon.ico` & `app_icon.png`) with 1-click Windows Desktop shortcut creation.
- **Offline & Private**: 100% local processing; no files ever leave your system.
- **Standalone Word-to-PDF**: Converts Word documents to PDF without requiring Microsoft Word or Office installation.
- **Fast PDF Processing**: Uses PyMuPDF for page-by-page image rendering, text extraction, and automatic table detection.
- **Full Apple HEIC Support**: iPhone HEIC/HEIF photo decoding and encoding via `pillow-heif`.
- **Drag & Drop Desktop GUI**: Modern Dark Mode interface with real-time file previews, live metadata privacy badge, and batch progress tracking.
- **Scriptable CLI**: Complete command-line support with DPI control, quality settings, sheet selection, and directory recursion.

---

## Quick Start

### 1. Launching the Desktop GUI

Double click `launch_converter.bat`, or run from terminal:
```powershell
.\venv\Scripts\python.exe launch_converter.py
```

### 2. Using the CLI

```powershell
# Show supported formats
.\venv\Scripts\python.exe launch_converter.py --list-formats

# Local background removal (after the optional setup below)
.\venv\Scripts\python.exe launch_converter.py photo.jpg --remove-background
.\venv\Scripts\python.exe launch_converter.py photo.jpg --remove-background -o cutout.webp --save-mask
.\venv\Scripts\python.exe launch_converter.py -i ./photos --remove-background -r -o ./cutouts

# Inspect sensitive metadata in a file
.\venv\Scripts\python.exe launch_converter.py --inspect-metadata photo.jpg
.\venv\Scripts\python.exe launch_converter.py --inspect-metadata confidential.pdf

# Clean / strip all metadata directly without changing format
.\venv\Scripts\python.exe launch_converter.py --clean-metadata photo.jpg
.\venv\Scripts\python.exe launch_converter.py --clean-metadata document.pdf

# Strip metadata during format conversion
.\venv\Scripts\python.exe launch_converter.py -i photo.heic -o photo.jpg --strip-metadata
.\venv\Scripts\python.exe launch_converter.py -i contract.docx -o contract.pdf --strip-metadata

# Convert CSV to Excel (.xlsx)
.\venv\Scripts\python.exe launch_converter.py -i data.csv -o data.xlsx

# Convert CSV to printable PDF report
.\venv\Scripts\python.exe launch_converter.py -i data.csv -o report.pdf

# Convert Excel (.xlsx) to CSV
.\venv\Scripts\python.exe launch_converter.py -i sheet.xlsx -o output.csv

# Convert PDF to PNG images (at 200 DPI)
.\venv\Scripts\python.exe launch_converter.py -i document.pdf -f PNG -o ./pdf_pages --dpi 200

# Convert Word (.docx) to PDF
.\venv\Scripts\python.exe launch_converter.py -i document.docx -o document.pdf

# Convert Word (.docx) to plain text
.\venv\Scripts\python.exe launch_converter.py -i notes.docx -o notes.txt

# Convert HEIC photo to WebP
.\venv\Scripts\python.exe launch_converter.py -i photo.heic -o photo.webp -q 85 --resize-percent 50

# Compress a photo to WebP with resize bounds
.\venv\Scripts\python.exe launch_converter.py -i photo.jpg -o photo_compressed.webp -q 75 --width 1920 --height 1920

# Batch-compress a folder of images
.\venv\Scripts\python.exe launch_converter.py -i ./photos -f WEBP -q 75 --width 1920 --height 1920 -r -o ./compressed

# Batch convert an entire folder to PDF
.\venv\Scripts\python.exe launch_converter.py -i ./docs_and_images -f PDF -o ./all_pdfs
```

---

## Optional Background Removal Setup

Run these commands from the repository root using Python 3.11 or newer:

```powershell
.\venv\Scripts\python.exe -m pip install -r image_converter/requirements-background.txt

# Explicit download only when a verified fast model is not already local.
.\venv\Scripts\bgremove.exe models pull fast --model-dir backgroundG/models

# Optional additional profiles, stored in the per-user model cache.
.\venv\Scripts\bgremove.exe models pull balanced
.\venv\Scripts\bgremove.exe models pull portrait
.\venv\Scripts\bgremove.exe models pull quality
```

The app uses local ONNX models, verifies their SHA-256, and never downloads weights
during inference. The `fast` model is already available in this workspace. Choose
another installed profile with `--bg-model balanced|quality|portrait`; choose its
folder using `--bg-model-dir`, the page's model-folder setting, or
`BGREMOVE_MODEL_DIR`. The default search covers packaged models, `backgroundG/models`,
and the module's platform cache. See [the model guide](../backgroundG/MODELS.md) for
explicit install commands, provenance, model sizes, and licenses.

Quality and Portrait need at least **8 GiB of free RAM** for CPU processing. A
preflight check rejects insufficient memory before allocating the model session;
choose Fast/Balanced or free memory in other apps. The check does not enforce a
continuous memory cap. Only the currently selected model session is retained in
the idle cache when switching profiles.

Background inference now defaults to two CPU threads with idle spinning off,
fetches only its mask output, and releases its model after every batch. Two dummy
startup inferences were removed. Normal file conversion defaults to two workers;
Convert and Remove Background batches cannot overlap in the GUI. See
[runtime measurements](../docs/RUNTIME_OPTIMIZATION.md) and the separate
[training workflow](../docs/TRAINING_AND_OPTIMIZATION.md).

Use `.\venv\Scripts\bgremove.exe models check --json` from the repository root to
verify files and CPU startup readiness without constructing model sessions.
See [model readiness and guarded verification](../docs/BACKGROUND_MODELS.md) for
current results and an explicit, guarded real-image verification command.

JPEG, PNG, WebP, BMP, and TIFF inputs are supported up to 25 MiB and 120 MP per
image. Animated and multi-page images are rejected. PNG is the default; WebP is
lossless. EXIF/GPS is removed unless `--keep-metadata` is selected. Inputs and
existing outputs are protected; generated names use a unique `_nobg` suffix.
Recursive folder runs preserve subdirectories and exclude a nested output folder.
Cancellation takes effect between files. Optional masks retain the oriented input
dimensions, including when `--bg-crop` changes the cutout canvas.

Advanced options are `--bg-feather`, `--bg-edge-shift`, `--bg-two-pass`, `--bg-crop`,
and `--bg-padding`. Use `--bg-fill-color '#ffffff'` for a solid fill; omitting it
preserves transparency. Conversion's `--bg-color`, resize, OCR, and metadata
inspection/cleaning belong to the other CLI modes. Alpha matting is not included.

On the **Remove Background** page, select a completed image and click **Copy image**
above its result, use the result's context menu, or press **Ctrl+C** with the queue or
result preview focused. **Ctrl+V** pastes into compatible apps or folders. Clipboard
data includes full-resolution PNG pixels with transparency, a native image, and the
exported file URL. It never copies the scaled preview or checkerboard. Clipboard
formats and transparency support depend on the receiving app.

The fast-model sample runs and integration smoke checks validate file processing,
not measured segmentation quality. Hair, glass, tiny subjects, and low contrast
may require manual correction. The larger model profiles have not been quality
validated in this app.

Build with the optional dependencies installed to include background removal in
the executable. The spec bundles only verified local fast weights and includes
[model notices](notices/background-removal/NOTICE.txt), the upstream license,
registry, and native runtime libraries. No model download happens during packaging;
the spec prints setup guidance when the runtime or model is absent. Test the
packaged feature on the target machine before distribution.

---

## Running Tests

Automated 79-test pytest suite validates security, metadata stripping, and conversions across all formats:
```powershell
.\venv\Scripts\python.exe -m pytest image_converter/tests/ -v
```
