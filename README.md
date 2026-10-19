# Universal File Converter & PDF Toolkit

A fast, hardened, local desktop and CLI file conversion application and PDF utility built with Python, PySide6 (Qt6), PyMuPDF, python-docx, ReportLab, pandas, openpyxl, Pillow, and Windows COM automation.

Convert between **PDF, Word (DOCX), Excel (XLSX), PowerPoint (PPTX), OpenDocument (ODT), Rich Text (RTF), CSV**, and **Images (HEIC, JPG, PNG, WEBP, BMP, TIFF, GIF, ICO)** locally on your machine with zero cloud upload required.

---

## 📑 Table of Contents

- [Key Features](#-key-features)
- [Supported Formats & Conversion Matrix](#-supported-formats--conversion-matrix)
- [PDF Tools & Utilities](#-pdf-tools--utilities)
- [Image Tools & Compression](#image-tools--compression)
- [Background Removal](#background-removal)
- [Installation & Quick Start](#-installation--quick-start)
  - [Prerequisites](#prerequisites)
  - [Setup Virtual Environment](#setup-virtual-environment)
  - [Application Icon & Desktop Shortcut](#application-icon--desktop-shortcut)
  - [Launcher Command Guide](#launcher-command-guide)
- [Command Line Interface (CLI) Guide](#-command-line-interface-cli-guide)
  - [Listing Formats](#1-listing-supported-formats)
  - [Document Conversions (PDF, Word, Office)](#2-document-conversions-pdf-word-office)
  - [PDF Tools via CLI (Merge, Split, Organize, Compress)](#3-pdf-tools-via-cli)
  - [Spreadsheet & Data Conversions (CSV & Excel)](#4-spreadsheet--data-conversions-csv--excel)
  - [Image Conversions](#5-image-conversions)
  - [Advanced Options: OCR, Security, Passwords, and Concurrency](#6-advanced-options-ocr-security-passwords-and-concurrency)
  - [Privacy & Metadata Deletion](#7-privacy--metadata-deletion)
  - [Batch Directory Processing](#8-batch-directory-processing)
- [Desktop GUI Features](#-desktop-gui-features)
- [Standalone Executable Packaging](#-standalone-executable-packaging)
- [Python API Usage](#-python-api-usage)
- [Testing & Quality Assurance](#-testing--quality-assurance)
- [Architecture & Security Hardening](#-architecture--security-hardening)
- [FAQ & Troubleshooting](#-faq--troubleshooting)
- [License](#-license)

---

## 🚀 Key Features

- **Multi-Category File Conversion**:
  - **Documents**: Convert **PDF** to high-res images, Word (`.docx`), plain text, and extract data tables into Excel/CSV. Convert **Word (`.docx`)** to printable PDF, formatted text, HTML, ODT, RTF, and images.
  - **Presentations & Rich Docs**: Convert **PowerPoint (`.pptx`)** to PDF slides, responsive HTML presentations, text, and images. Convert **OpenDocument (`.odt`)** and **Rich Text (`.rtf`)** to PDF, Word (`.docx`), and text.
  - **Spreadsheets & Data**: Convert **CSV** (UTF-8, UTF-16, CP1252, Latin-1) to styled Excel workbooks (`.xlsx`), printable PDF tables, JSON, and responsive HTML. Convert **Excel (`.xlsx`)** to CSV, PDF reports, JSON, and HTML.
  - **Images**: Batch convert, resize, and compress between **HEIC, JPG, PNG, WEBP, BMP, TIFF, GIF, ICO, and PDF**.
- **Image Compression Workspace**:
  - Compress batches of images to WebP, JPG, PNG, or their original format with quality and max-dimension controls.
  - Optionally strip metadata from compressed copies and keep original source files untouched.
  - Reuses the same hardened conversion engine, output validation, and local-only processing as normal image conversion.
- **Background Removal Page**:
  - A separate desktop page for local batch cutouts, before/after previews, transparent PNG or lossless WebP, and optional grayscale masks.
  - Uses the optional `backgroundG` module on CPU with the small `fast` model by default; originals and existing outputs are protected.
- **Native PDF Toolkit**:
  - **Merge**: Combine multiple PDFs and images into a single cohesive PDF with optional hierarchical bookmark/TOC generation and atomic writes.
  - **Split**: Extract exact page ranges or burst documents into individual single-page files with strict range validation.
  - **Organize**: Visually reorder, rotate, extract, or delete pages while preserving hierarchical outline/bookmark trees.
  - **Compress**: Multi-stage PDF optimization (stream deflation, duplicate font/image consolidation) with an automatic fallback guard that guarantees output files never exceed source size.
  - **Enterprise Office COM Integration (Windows)**:
  - High-fidelity Office conversions powered by native COM automation with thread-isolated `CoInitialize`/`CoUninitialize`.
  - Hardened with `DisplayAlerts` suppression, `AutomationSecurity` macro blocking, and serialized access locks (`_ppt_com_lock`) for single-instance PowerPoint servers.
  - Pure-Python paths remain available where implemented; DOCX/XLSX/PPTX-to-PDF and RTF/ODT-to-PDF require Microsoft Office on Windows.
- **Privacy & Complete Metadata Deletion**:
  - **Images**: Strip all EXIF tags, GPS location data, camera make/model/serial numbers, IPTC profiles, and user comments.
  - **PDF Documents**: Strip title, author, subject, creator, producer, creation/modification timestamps, and embedded Adobe XMP XML packets.
  - **Office Documents**: Clean author, last modified by, company, keywords, comments, and revision histories from `.docx`, `.xlsx`, `.pptx`, and `.odt`.
  - **Live Privacy Badge**: Automatic metadata scanning in the GUI (`⚠️ Has metadata` / `🛡️ Clean`).
- **OCR Engine (Optical Character Recognition)**:
  - Extract searchable text from scanned PDFs and images via Tesseract OCR (`--ocr` flag or GUI toggle). Image-to-DOCX creates a document containing the source image; it does not produce editable OCR text.
- **Integrity & Security Hardening**:
  - **Single False-Success Gate**: All conversions pass through `_verify_and_create_result`. Empty or 0-byte outputs are immediately unlinked and returned as failures.
  - **Atomic File Operations**: Outputs are written to isolated temporary files (`.tmp_*`) and atomically swapped via `os.replace` to prevent corrupted partial writes.
  - **Table Extraction Validation**: Geometry-based validation checks coordinate grids and non-overlapping bounding boxes to avoid malformed tables.
  - **Zip-Bomb & Traversal Guards**: Enforces container ratio ceilings, max entry counts, and path traversal defenses.
- **100% Offline & Local**: Zero cloud dependencies; all processing occurs strictly on your local hardware.

---

## 🔄 Supported Formats & Conversion Matrix

| Input Format | Category | Target Output Formats |
| :--- | :--- | :--- |
| **PDF** (`.pdf`) | Document | `PNG`, `JPG`, `WEBP`, `DOCX`, `TXT`, `CSV`, `XLSX` |
| **Word** (`.docx`, `.doc`) | Document | `PDF`, `TXT`, `HTML`, `PNG`, `JPG`, `WEBP`, `ODT`, `RTF` |
| **PowerPoint** (`.pptx`) | Presentation | `PDF`, `TXT`, `HTML`, `PNG`, `JPG`, `WEBP` |
| **OpenDocument** (`.odt`) | Document | `PDF`, `DOCX`, `TXT`, `RTF` |
| **Rich Text** (`.rtf`) | Document | `PDF`, `DOCX`, `TXT`, `ODT` |
| **Plain Text** (`.txt`) | Text | `PDF`, `DOCX`, `PPTX`, `RTF`, `HTML` |
| **CSV** (`.csv`) | Spreadsheet | `XLSX`, `PDF`, `JSON`, `HTML`, `TXT` |
| **Excel** (`.xlsx`, `.xls`) | Spreadsheet | `CSV`, `PDF`, `JSON`, `HTML` |
| **Images** (HEIC, JPG, PNG, WEBP, BMP, TIFF, GIF, ICO, PPM, TGA, EPS) | Image | `JPG`, `PNG`, `WEBP`, `HEIC`, `BMP`, `TIFF`, `GIF`, `ICO`, `PDF`, `TXT` (OCR), `DOCX` (embedded image) |

---

## 🛠️ PDF Tools & Utilities

Universal File Converter provides specialized tools for direct PDF manipulation:

| Tool | Functionality | Key Features |
| :--- | :--- | :--- |
| **Merge PDFs** | Combine multiple PDFs & images | Preserves bookmarks/TOCs, upfront file validation, atomic writes |
| **Split PDF** | Break PDFs into parts or pages | Supports ranges (`1-3,5`), burst mode, rejects out-of-bound pages |
| **Organize Pages** | Reorder, delete, and rotate pages | Full hierarchical outline/TOC preservation, index validation |
| **Compress PDF** | Reduce PDF file size | Lossless & lossy stream optimization, font deduplication, fallback guard |

---

## 🖼️ Image Tools & Compression

The desktop app includes a dedicated **Image Tools** workspace for reducing image file size without changing originals.

| Tool | Functionality | Key Features |
| :--- | :--- | :--- |
| **Compress Images** | Shrink photos, screenshots, and graphics | WebP/JPG/PNG/original-format output, quality slider, max-width/max-height resize, metadata stripping |

CLI users can use the same compression path through image conversion quality and resize options:

```powershell
# WebP compression with quality and max bounds
python launch_converter.py -i photo.jpg -o photo.webp -q 75 --width 1920 --height 1920

# Batch image compression to WebP
python launch_converter.py -i ./photos -f WEBP -q 75 --width 1920 --height 1920 -r -o ./compressed
```

---

## Background Removal

Open **Remove Background** in the top navigation for its own workspace. Add images,
choose a local model and output folder, adjust optional edge/crop settings, and start
the batch. The worker reuses one CPU model session, reports each file, and supports
cancellation between images. Select a result to compare the source and cutout.

Select a completed image and click **Copy image** above the result, right-click the
result and choose **Copy image**, or press **Ctrl+C** while the image queue or result
preview has focus. Paste with **Ctrl+V** in an image editor, document, chat, or folder
that accepts images or files. Copying uses the full-resolution exported image,
including its transparency, rather than the smaller preview. The clipboard offers
PNG image data, a native image, and the exported file for compatible paste targets.
The receiving app determines which format it accepts and whether it retains alpha.

Install the optional feature from the repository root using **Python 3.11+**:

```powershell
.\venv\Scripts\python.exe -m pip install -r image_converter/requirements-background.txt

# Only needed if the fast model is not already in backgroundG/models or the cache.
# This explicit command downloads and verifies its pinned model artifact.
.\venv\Scripts\bgremove.exe models pull fast --model-dir backgroundG/models

# Install additional profiles in the shared per-user model cache.
.\venv\Scripts\bgremove.exe models pull balanced
.\venv\Scripts\bgremove.exe models pull portrait
.\venv\Scripts\bgremove.exe models pull quality
```

Normal conversion and compression remain available without this optional package.
Inference never downloads weights or uploads images. The `fast` model is already
present in this workspace. Other installed profiles (`balanced`, `quality`,
`portrait`) can be selected; install their weights explicitly using the `bgremove`
model commands. Use the page's model folder, CLI `--bg-model-dir`, or
`BGREMOVE_MODEL_DIR` to select a directory containing the registered ONNX filenames.
Without an explicit folder, the app checks bundled models, `backgroundG/models`,
then the module's platform cache. Every model is verified against its registered
SHA-256 before use. See [backgroundG/MODELS.md](backgroundG/MODELS.md) for provenance,
model sizes, and license details.

Quality and Portrait require **at least 8 GiB of free RAM** for this app's CPU
processing. The app checks memory before allocating a large model session and
returns a clear error when there is insufficient headroom. Fast and Balanced use
less memory. This is a startup check, not a hard memory limit during processing;
image size and other running programs still affect resource use.

Resource defaults favor a responsive desktop: two ONNX CPU threads, no idle
thread spinning, only the requested mask output, and session release after each
batch. Normal file conversion defaults to two concurrent workers; the GUI does
not start Convert and Remove Background batches together. The model weights and
full-resolution outputs are unchanged. See the [measured runtime improvements](docs/RUNTIME_OPTIMIZATION.md).

A separate [training workflow](docs/TRAINING_AND_OPTIMIZATION.md) prepares a
small U2NETP candidate from reviewed image/mask pairs. It keeps development
dependencies outside the app and does not replace installed weights automatically.

Check installed files and CPU startup readiness without loading model sessions:

```powershell
.\venv\Scripts\bgremove.exe models check --json
```

See [model readiness and guarded verification](docs/BACKGROUND_MODELS.md) for
the current four-profile status, exit codes and safe real-image test commands.
The [full GUI report](docs/GUI_REPORT.html) covers every page, control and dialog.

```powershell
# Transparent PNG next to the original, using a unique photo_nobg.png name.
python launch_converter.py photo.jpg --remove-background

# Lossless WebP and a full-size grayscale PNG mask.
python launch_converter.py photo.jpg --remove-background -o cutout.webp --save-mask

# Recursive batches retain relative subdirectories in the destination.
python launch_converter.py -i photos --remove-background -r -o cutouts

# Optional edge refinement, foreground crop, and a solid background fill.
python launch_converter.py photo.jpg --remove-background --bg-two-pass --bg-feather 0.8 --bg-edge-shift -1 --bg-crop --bg-padding 20 --bg-fill-color '#ffffff'
```

Supported inputs are **JPEG, PNG, WebP, BMP, and TIFF** (including `.jpg`, `.jpeg`,
`.jpe`, `.bmp`, `.dib`, `.tif`, and `.tiff` aliases), up to **25 MiB** and
**120 megapixels** per file. Animated or multi-page images are rejected. Outputs are
PNG or lossless WebP; transparency is retained unless `--bg-fill-color` is supplied.
The conversion option `--bg-color` belongs to the normal conversion workflow.
EXIF/GPS is stripped by default; `--keep-metadata` opts into preserving metadata.
Optional masks keep the oriented source dimensions even when the cutout is cropped.

The default destination uses unique `_nobg` names. An explicit output filename must
be new, match the requested format, and be used with a single input image. Existing
source files, cutouts, and masks are protected. Resize, OCR, metadata inspection,
and metadata cleaning are separate CLI modes. Advanced alpha matting is not included.

The existing `fast` examples and integration smoke checks demonstrate the pipeline,
not a measured quality benchmark. Fine hair, glass, low contrast, and tiny subjects
can need manual correction. The larger profiles have not been quality validated in
this app; their names do not establish measured performance rankings.

---

## 📦 Installation & Quick Start

### Prerequisites
- **Python 3.10+** (tested on Python 3.10 through 3.14)
- Optional background removal requires **Python 3.11+** and the additional setup above.
- Windows, macOS, or Linux (Native Microsoft Office COM features require Windows + Office installed)
- Optional Windows Office automation: install Microsoft Office and the `pywin32` package (`python -m pip install pywin32`).
- Optional OCR: install the Tesseract OCR engine; see the FAQ below.

### Setup Virtual Environment

1. Clone or navigate to the repository:
   ```bash
   cd "file converter"
   ```

2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   .\venv\Scripts\pip install -r image_converter/requirements.txt
   ```

### Application Icon & Desktop Shortcut

Universal File Converter includes a custom high-resolution application icon (`app_icon.ico` & `app_icon.png`) with support for Windows taskbar grouping (AppUserModelID), title bar, and desktop shortcuts.

```powershell
# Create Desktop shortcut with the custom application icon
.\launch_converter.bat --create-shortcut

# Or create via Python launcher
python launch_converter.py --create-shortcut
```

### Launcher Command Guide

The project provides two primary launchers: `launch_converter.bat` and `launch_converter.py`.

#### 1. Windows Batch Launcher (`launch_converter.bat`)
- **GUI Mode**: Double-click `launch_converter.bat` or run `.\launch_converter.bat` with no arguments. It launches the PySide6 GUI in the background without leaving an open terminal window.
- **CLI Mode**: Pass arguments to stream console output:
  ```powershell
  .\launch_converter.bat -i document.pdf -o document.docx
  ```

#### 2. Python Unified Launcher (`launch_converter.py`)
- **Desktop GUI**:
  ```powershell
  python launch_converter.py
  ```
- **CLI Mode**:
  ```powershell
  python launch_converter.py -i sample.csv -o sample.xlsx
  ```

---

## 💻 Command Line Interface (CLI) Guide

### 1. Listing Supported Formats
```powershell
python launch_converter.py --list-formats
```

### 2. Document Conversions (PDF, Word, Office)

#### Convert PDF to High-Resolution PNG Images
```powershell
# Default 150 DPI
python launch_converter.py -i document.pdf -f PNG -o ./output_images

# High-resolution 300 DPI
python launch_converter.py -i document.pdf -f PNG -o ./output_images --dpi 300
```

#### Convert PDF to Word (.docx)
```powershell
python launch_converter.py -i report.pdf -o report.docx
```

#### Extract Tables from PDF to CSV or Excel
```powershell
python launch_converter.py -i financial_statement.pdf -o tables.csv
python launch_converter.py -i financial_statement.pdf -o tables.xlsx
```

#### Convert Word (.docx) or PowerPoint (.pptx) to PDF
```powershell
python launch_converter.py -i proposal.docx -o proposal.pdf
python launch_converter.py -i presentation.pptx -o presentation.pdf
```

---

### 3. PDF Tools via CLI

#### Merge Multiple PDFs and Images
```powershell
python -c "from image_converter.core.pdf_tools import merge_pdfs; merge_pdfs(['doc1.pdf', 'chart.png', 'doc2.pdf'], 'merged.pdf')"
```

#### Split PDF Pages
```powershell
# Split specific page range (1-indexed)
python -c "from image_converter.core.pdf_tools import split_pdf; split_pdf('large_book.pdf', 'split_out', page_range='1-10')"

# Burst all pages into individual single-page PDFs
python -c "from image_converter.core.pdf_tools import split_pdf; split_pdf('large_book.pdf', 'split_out', burst=True)"
```

#### Compress PDF
```powershell
python -c "from image_converter.core.pdf_tools import compress_pdf; res = compress_pdf('heavy_document.pdf', 'optimized.pdf', power=2); print(res)"
```

---

### 4. Spreadsheet & Data Conversions (CSV & Excel)

#### Convert CSV to Styled Excel Workbook (.xlsx)
```powershell
python launch_converter.py -i data.csv -o data.xlsx
```

#### Convert CSV to Printable PDF Table Report
```powershell
python launch_converter.py -i customers.csv -o customers.pdf
```

#### Convert Excel (.xlsx) to CSV
```powershell
# Converts active sheet
python launch_converter.py -i workbook.xlsx -o output.csv

# Convert specific sheet by name
python launch_converter.py -i workbook.xlsx -o q3_sales.csv --sheet "Q3"
```

---

### 5. Image Conversions

#### Convert Apple HEIC Photos to JPG or PNG
```powershell
python launch_converter.py -i IMG_1234.heic -o photo.jpg -q 92
python launch_converter.py -i IMG_1234.heic -o photo.png
```

#### Convert Image with Transparency to JPG with Custom Background
```powershell
# White background
python launch_converter.py -i logo.png -o logo.jpg --bg-color "#ffffff"

# Custom dark slate background
python launch_converter.py -i icon.png -o icon.jpg --bg-color "#1f2937"
```

#### Convert and Resize Image
```powershell
# Scale down by 50%
python launch_converter.py -i banner.jpg -o banner_small.jpg --resize-percent 50

# Fit inside 1920x1080 while preserving aspect ratio
python launch_converter.py -i raw.png -o wallpaper.webp --width 1920 --height 1080
```

#### Create Windows Icon (.ico) Bundle
```powershell
# Multi-size bundle (16, 32, 48, 64, 128, 256 px)
python launch_converter.py -i logo.png -o favicon.ico
```

---

### 6. Advanced Options: OCR, Security, Passwords, and Concurrency

#### OCR Text Extraction on Scanned PDFs and Images
```powershell
# Extract text from a scanned PDF page using Tesseract OCR fallback
python launch_converter.py -i scanned_doc.pdf -o searchable.txt --ocr

# Place a receipt scan inside a Word (.docx) document
python launch_converter.py -i receipt_scan.jpg -o document.docx --ocr
```

#### Converting Password-Protected PDFs
```powershell
python launch_converter.py -i secure_statement.pdf -o statement.docx --password "mySecret123"
```

#### Multithreaded Batch Processing & Concurrency
```powershell
# Convert a directory with 8 concurrent worker threads
python launch_converter.py -i ./large_batch -f WEBP -o ./converted --workers 8
```

#### Detailed Diagnostic Logging
```powershell
python launch_converter.py -i ./documents -f PDF -o ./pdf_out -v --log-file ./converter.log
```

---

### 7. Privacy & Metadata Deletion

Universal File Converter allows you to inspect, sanitize, and completely purge tracking metadata, GPS locations, camera hardware identifiers, and office document author histories.

#### Inspect File for Sensitive Metadata
```powershell
python launch_converter.py --inspect-metadata photo.jpg
python launch_converter.py --inspect-metadata confidential_report.pdf
python launch_converter.py -i contract.docx --inspect-metadata
```

#### Directly Strip / Clean Metadata Without Changing Format
```powershell
# Strips all EXIF, GPS, and camera tags from JPEG, saving to photo_clean.jpg
python launch_converter.py --clean-metadata photo.jpg

# Strips author, title, producer, and XMP XML streams from PDF
python launch_converter.py --clean-metadata document.pdf

# Custom output destination
python launch_converter.py -i proposal.docx -o proposal_sanitized.docx --clean-metadata
```

---

### 8. Batch Directory Processing

```powershell
# Convert all convertible documents/images in a folder to PDF
python launch_converter.py -i ./input_folder -f PDF -o ./pdf_results

# Recursively scan subdirectories
python launch_converter.py -i ./photos -f WEBP -q 85 -o ./optimized_webp -r
```

---

## 🖥️ Desktop GUI Features

1. **Modern PySide6 (Qt6) Interface**:
   - Clean dark-mode stylesheet with responsive drag-and-drop queues.
   - Per-file progress bars, real-time conversion status indicators, and size reduction statistics.
2. **Dedicated PDF Tools Dialogs**:
   - **Merge Dialog**: Drag-to-reorder files, toggle bookmark/TOC generation, and merge.
   - **Split Dialog**: Extract page ranges (`1-5, 8`) or burst into individual pages with real-time range validation.
   - **Organize Dialog**: Interactive visual page grid to reorder, rotate (90° clockwise/counter-clockwise), or delete pages.
   - **Compress Dialog**: Select compression presets (Screen 72 DPI, eBook 150 DPI, Print 300 DPI) and preview size reduction with safe fallback protection.
3. **Dedicated Image Tools Workspace**:
   - **Compress Images**: Batch image compression with output format, quality, resize bounds, destination folder, and metadata stripping controls.
  - Queue context menu integration lets image rows jump straight into compression.
4. **Dedicated Background Removal Page**:
   - Local batch processing with model selection, transparent PNG/lossless WebP, optional masks, before/after preview, and edge/crop settings.
   - CPU inference runs in a worker, reusing the loaded model; cancellation takes effect between files.
5. **Interactive File Preview & Privacy Badges**:
   - First-page rendering for PDFs and image previews with color mode and dimensions.
   - Document summaries (paragraph, table, slide, and word counts).
   - Live privacy badge inspects file metadata and alerts user (`⚠️ Has metadata` / `🛡️ Clean`).
6. **Queue Management & Thread Worker**:
   - Background `QThread` execution ensures the UI never hangs or freezes during heavy conversions.
  - Cancellation stops queued work after the current conversion completes.

---

## 📦 Standalone Executable Packaging

Package the entire application into a standalone Windows `.exe` with embedded icon:

```powershell
# Build single-file executable with clean build artifacts
python build_executable.py --onefile --clean

# Build executable and automatically generate Desktop shortcut
python build_executable.py --onefile --clean --shortcut
```

The resulting binary is generated in `dist/UniversalFileConverter.exe`.

To include background removal, install `image_converter/requirements-background.txt`
in the build environment first. The spec collects `bgremove`, its registry, ONNX
Runtime/OpenCV native libraries and package metadata, and embeds the verified `fast`
weights found in `BGREMOVE_MODEL_DIR`, `backgroundG/models`, or the platform cache.
It never downloads weights during a build. Missing dependencies produce a build
message that the feature will be unavailable; a missing model produces instructions
to install it explicitly or select an external model folder at runtime. A model
checksum mismatch stops the build.

The bundle includes [background-removal notices](image_converter/notices/background-removal/NOTICE.txt),
the upstream Apache 2.0 license, and model provenance. Larger models remain external.
The module's virtual environment, demo artifacts, and optional alpha-matting stack
are excluded. A successful build alone does not validate its native runtime; smoke
test a cutout on the target machine before distributing the executable.

---

## 🐍 Python API Usage

The core conversion and PDF utility engines can be imported directly into Python applications:

```python
from pathlib import Path
from image_converter.core.engine import UniversalConverterEngine, ConversionConfig
from image_converter.core.pdf_tools import merge_pdfs, split_pdf, organize_pages, compress_pdf
from image_converter.core.metadata_engine import strip_file_metadata, get_detailed_metadata

engine = UniversalConverterEngine()

# 1. Convert CSV to Excel
config_xlsx = ConversionConfig(target_format="XLSX")
result = engine.convert_single("data.csv", "data.xlsx", config_xlsx)
print(f"Success: {result.success}, File size: {result.output_size_bytes} bytes")

# 2. Convert PDF to PNG images (with password support)
config_png = ConversionConfig(target_format="PNG", dpi=200, password="optional_password")
result = engine.convert_single("paper.pdf", "page.png", config_png)

# 3. Merge PDFs with hierarchical bookmarks
merged_output = merge_pdfs(["intro.pdf", "chart.png", "appendix.pdf"], "final_report.pdf", bookmarks=True)

# 4. Compress PDF with guaranteed size invariant
compress_info = compress_pdf("heavy_scan.pdf", "compressed_scan.pdf", power=2)
print(f"Ratio: {compress_info['ratio']:.1%}, Saved: {compress_info['saved_bytes']} bytes")

# 5. Multithreaded Batch conversion with progress callback
tasks = [
    (Path("table.csv"), Path("table.xlsx"), config_xlsx),
    (Path("doc.docx"), Path("doc.pdf"), ConversionConfig(target_format="PDF", strip_metadata=True)),
]

def on_progress(current, total, res):
    print(f"[{current}/{total}] Converted {res.input_path} -> {res.output_path}")

results = engine.convert_batch(tasks, progress_callback=on_progress, max_workers=4)
```

---

## 🧪 Testing & Quality Assurance

The repository includes an automated pytest suite covering conversion, security, metadata, CLI, concurrency, and GUI behavior:

```powershell
# Run the full test suite
.\venv\Scripts\python -m pytest -q

# Run specific functional test suites
pytest image_converter/tests/test_pdf_tools.py -v         # PDF merge, split, organize, compress
pytest image_converter/tests/test_documents.py -v         # PDF & DOCX conversion pipelines
pytest image_converter/tests/test_com_automation.py -v    # COM thread safety, constants & security
pytest image_converter/tests/test_office_integration.py -v  # Multi-threaded Office concurrency & failure tests
pytest image_converter/tests/test_qa_audit.py -v          # Full QA audit across all formats
pytest image_converter/tests/test_tool_dialogs.py -v      # GUI tool dialogs (offscreen)
pytest image_converter/tests/test_security.py -v          # Zip-bomb, path traversal, magic bytes
pytest image_converter/tests/test_background_cli.py -v    # Background-removal CLI routing and output safety
```

### Verification Highlights
- **Stressed Multi-Threaded Office Concurrency**: 5-run concurrency check (120 conversions across 4 threads, 30 corrupt/locked failure attempts) tested with 500ms process polling and 10s delayed probes, proving 0 lingering COM processes.
- **AST Silent-Handler Scan**: AST parser verifies that 100% of non-raising/non-logging exception handlers in non-test code are top-level `ImportError` guards for optional dependencies.
- **Mutation Tested**: Injected failures verified against PyMuPDF, Pillow, win32com, and python-docx.

---

## 🏗️ Architecture & Security Hardening

For a fuller service-level architecture overview, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

```
file converter/
│
├── launch_converter.py          # Unified entry point (CLI router & GUI launcher)
├── launch_converter.bat         # Windows double-click launcher & CLI forwarder
├── create_shortcut.py           # Windows Desktop & Start Menu shortcut creator
├── build_executable.py          # PyInstaller automated packaging script
├── universal_file_converter.spec# PyInstaller configuration specification
├── app_icon.ico                 # Multi-resolution application icon (16x16 to 256x256)
├── app_icon.png                 # High-resolution application brand mark
├── main.py                      # Compatibility entry point
│
├── image_converter/
│   ├── requirements.txt         # Project dependencies
│   ├── cli.py                   # Command-line interface with -v, --ocr, --strip-metadata
│   │
│   ├── core/                    # Modular core services with compatibility wrappers
│   │   ├── conversion/          # UniversalConverterEngine, image conversion, batch orchestration
│   │   ├── documents/           # PDF and Word conversion pipelines
│   │   ├── data/                # CSV, Excel, JSON, HTML, and table conversions
│   │   ├── presentations/       # PowerPoint conversion pipelines
│   │   ├── rich_documents/      # ODT and RTF conversion pipelines
│   │   ├── pdf/                 # Merge, split, organize, rotate, extract, compress
│   │   ├── metadata/            # Metadata inspection and stripping
│   │   ├── ocr/                 # Tesseract OCR page rendering and extraction
│   │   ├── safety/              # Zip-bomb defense, magic-byte sniffing, traversal guard
│   │   ├── platform/            # Windows COM helpers and thread-local initialization
│   │   ├── observability/       # Logging setup and logger access
│   │   ├── engine.py            # Backward-compatible wrapper for core/conversion
│   │   ├── pdf_tools.py         # Backward-compatible wrapper for core/pdf
│   │   └── ...                  # Additional old-path wrappers for existing imports
│   │
│   ├── ui/                      # PySide6 Desktop GUI
│   │   ├── assets/              # UI brand assets (app_icon.ico, app_icon.png)
│   │   ├── main_window.py       # Main application window & toolbar integration
│   │   ├── tool_dialogs.py      # Dedicated dialogs (Merge, Split, Organize, Compress)
│   │   ├── pdf_tools_page.py    # PDF tools workspace
│   │   ├── image_tools_page.py  # Image compression workspace
│   │   ├── queue_model.py       # Conversion queue state model
│   │   ├── components.py        # DropZone, Preview, Settings, QueueTable
│   │   ├── nav_rail.py          # Left navigation bar
│   │   ├── stats_widget.py      # Conversion statistics cards
│   │   ├── theme.py             # Modern Dark Mode CSS stylesheet
│   │   └── worker.py            # Background QThread for non-blocking conversion
│   │
│   └── tests/                   # Automated pytest suite
│       ├── conftest.py          # Pytest fixtures and Office test markers
│       ├── test_engine.py       # Core image engine & false-success gate tests
│       ├── test_pdf_tools.py    # PDF merge, split, organize, compress invariant tests
│       ├── test_documents.py    # PDF and DOCX pipelines & table extraction validation
│       ├── test_office_integration.py # Multi-threaded Office concurrency & failure tests
│       ├── test_com_automation.py# CoInitialize per-thread & COM constants unit tests
│       ├── test_tool_dialogs.py # GUI tool dialogs (offscreen)
│       ├── test_qa_audit.py     # End-to-end QA audit test suite
│       ├── test_metadata.py     # Metadata stripping & inspection tests across all formats
│       ├── test_security.py     # Security, path traversal & magic byte sniffing tests
│       ├── test_edge_cases.py   # Malformed, encrypted, and non-UTF8 tests
│       ├── test_concurrency.py  # Concurrency, workers & cancel tests
│       ├── test_new_formats.py  # PPTX, ODT, and RTF tests
│       ├── test_ocr.py          # OCR engine & fallback tests
│       ├── test_data.py         # CSV & Excel tests
│       └── test_cli.py          # CLI integration tests
```

---

## ❓ FAQ & Troubleshooting Guide

### 1. How do I enable OCR?
Install the Tesseract OCR engine on your operating system:
- **Windows**: `winget install UB-Mannheim.TesseractOCR` (default path: `C:\Program Files\Tesseract-OCR`).
- **macOS**: `brew install tesseract`.
- **Linux**: `sudo apt-get install tesseract-ocr`.
Then pass `--ocr` in the CLI or check "Enable OCR Text Fallback" in the GUI.

### 2. When is Microsoft Office used vs. Pure-Python Headless mode?
- **On Windows with Microsoft Office installed**: DOCX $\rightarrow$ PDF, PPTX $\rightarrow$ PDF, XLSX $\rightarrow$ PDF, and RTF/ODT $\rightarrow$ PDF leverage native Microsoft Office COM automation. This guarantees 100% visual fidelity, preserving exact fonts, page layouts, table formatting, and complex vector shapes. All COM calls run within isolated thread contexts with macro suppression and automatic process termination.
- **On non-Windows platforms or machines without Office**: Office-dependent PDF exports are unavailable and return a conversion failure. Other implemented routes use the available pure-Python libraries (`reportlab`, `python-docx`, `python-pptx`, `pdf2docx`, `openpyxl`).

### 3. How does the PDF compressor guarantee files never grow larger?
`compress_pdf` applies progressive optimization passes (deflate streams, image downsampling, font/metadata cleanup). Before finalizing, it measures the output size against the original input. If the optimized file is equal to or larger than the source, it automatically replaces the output with a bit-identical copy of the source, guaranteeing that `output_size <= input_size` under all circumstances.

### 4. What security defenses are built in?
- **Universal False-Success Gate**: Output files must exist and have `size > 0`. Corrupted or 0-byte files are immediately unlinked and returned as failures.
- **Zip Bombs**: Checks container ratio (max 100:1), total uncompressed bytes (max 500MB), and total entry count (max 50,000) on all OpenPackaging formats (`.docx`, `.xlsx`, `.pptx`, `.odt`).
- **Path Traversal & Injections**: Validates that destination paths cannot escape intended directories or contain null bytes (`\x00`).
- **Magic Byte Sniffing**: Inspects true binary signatures (`%PDF-`, `\x89PNG`, `PK\x03\x04`, `{\rtf`) to prevent extension-spoofing attacks.

---

## 📄 License

MIT License. Free for personal and commercial use.
