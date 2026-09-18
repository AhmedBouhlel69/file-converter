# Universal File Converter

A fast, cross-platform, local desktop and CLI file conversion application built with Python, PySide6 (Qt6), PyMuPDF, python-docx, ReportLab, pandas, openpyxl, and Pillow.

Convert between **PDF, Word (DOCX), Excel (XLSX), CSV**, and **Images (HEIC, JPG, PNG, WEBP, BMP, TIFF, GIF, ICO)** locally on your machine with zero cloud upload required.

---

## 📑 Table of Contents

- [Key Features](#-key-features)
- [Supported Formats & Conversion Matrix](#-supported-formats--conversion-matrix)
- [Installation & Quick Start](#-installation--quick-start)
  - [Prerequisites](#prerequisites)
  - [Setup Virtual Environment](#setup-virtual-environment)
  - [Application Icon & Desktop Shortcut](#application-icon--desktop-shortcut)
  - [Launcher Command Guide](#launcher-command-guide)
- [Standalone Executable Packaging](#-standalone-executable-packaging)
- [Command Line Interface (CLI) Guide](#-command-line-interface-cli-guide)
  - [Listing Formats](#1-listing-supported-formats)
  - [Document Conversions (PDF & Word)](#2-document-conversions-pdf--word)
  - [Spreadsheet & Data Conversions (CSV & Excel)](#3-spreadsheet--data-conversions-csv--excel)
  - [Image Conversions](#4-image-conversions)
  - [Advanced Options: OCR, Security, Passwords, and Concurrency](#5-advanced-options-ocr-security-passwords-and-concurrency)
  - [Privacy & Metadata Deletion](#6-privacy--metadata-deletion)
  - [Batch Directory Processing](#7-batch-directory-processing)
- [Desktop GUI Features](#-desktop-gui-features)
- [Python API Usage](#-python-api-usage)
- [Testing](#-testing)
- [Architecture & Design](#-architecture--design)
- [FAQ & Troubleshooting](#-faq--troubleshooting)

---

## 🚀 Key Features

- **Multi-Category File Conversion**:
  - **Documents**: Convert **PDF** to high-res images, Word (`.docx`), plain text, and extract data tables into Excel/CSV. Convert **Word (`.docx`)** to printable PDF, formatted text, HTML, ODT, RTF, PPTX, and images.
  - **Presentations & Rich Docs**: Convert **PowerPoint (`.pptx`)** to PDF slides, responsive HTML presentations, text, and PNG images. Convert **OpenDocument (`.odt`)** and **Rich Text (`.rtf`)** to PDF, Word (`.docx`), and text.
  - **Spreadsheets & Data**: Convert **CSV** (UTF-8, UTF-16, CP1252, Latin-1) to styled Excel workbooks (`.xlsx`), printable PDF tables, JSON, and responsive HTML. Convert **Excel (`.xlsx`)** to CSV, PDF reports, JSON, and HTML.
  - **Images**: Seamlessly batch convert and resize between **HEIC, JPG, PNG, WEBP, BMP, TIFF, GIF, ICO, and PDF**.
- **Privacy & Complete Metadata Deletion**:
  - **Images (JPG, PNG, WEBP, HEIC, TIFF, BMP)**: Strip all EXIF tags, GPS location data, camera make/model/serial numbers, IPTC profiles, and user comments.
  - **PDF Documents**: Strip title, author, subject, creator, producer, creation/modification timestamps, and embedded Adobe XMP XML packets.
  - **Office Documents (Word, Excel, PowerPoint, ODT)**: Clear author, last modified by, company, keywords, comments, and revision histories from `.docx`, `.xlsx`, `.pptx`, and `.odt`.
  - **Live Metadata Inspection**: `--inspect-metadata` CLI report and live GUI privacy badge (`⚠️ Has metadata` / `🛡️ Clean`).
  - **Direct Sanitization**: Clean metadata directly without format change via `--clean-metadata` or GUI privacy mode.
- **OCR Engine (Optical Character Recognition)**:
  - Extract text and convert scanned PDFs and images directly to searchable Text and Word (`.docx`) documents via Tesseract OCR (`--ocr` flag or GUI toggle).
- **Hardened Security & Integrity**:
  - **Zip-bomb protection**: Enforces decompression ratios, entry limits, and uncompressed size ceilings on `.docx`, `.xlsx`, `.pptx`, and `.odt` files.
  - **Path traversal guards**: Defends against directory escape sequences and null-byte injection attacks.
  - **Magic byte signature sniffing**: Validates true binary signatures rather than relying purely on file extensions.
  - **0-byte & corruption defenses**: Gracefully catches and reports corrupted or empty input files.
- **Multithreaded High-Performance Batching**:
  - Concurrent batch processing using Python thread pools with thread-safe progress callbacks and instant mid-batch cancellation.
- **Structured Logging & Diagnostics**:
  - Built-in logging with verbose debug flags (`-v`, `--verbose`) and dedicated log file outputs (`--log-file`).
- **100% Offline & Private**: All conversions run locally on your computer.
- **Headless & Standalone**: Pure-Python pipelines with zero Microsoft Office dependencies.

---

## 🔄 Supported Formats & Conversion Matrix

| Input Format | Category | Target Output Formats |
| :--- | :--- | :--- |
| **PDF** (`.pdf`) | Document | `PNG`, `JPG`, `WEBP`, `DOCX`, `TXT`, `CSV`, `XLSX`, `PPTX` |
| **Word** (`.docx`, `.doc`) | Document | `PDF`, `TXT`, `HTML`, `PNG`, `JPG`, `WEBP`, `ODT`, `RTF`, `PPTX` |
| **PowerPoint** (`.pptx`) | Presentation | `PDF`, `TXT`, `HTML`, `PNG`, `JPG`, `WEBP`, `DOCX` |
| **OpenDocument** (`.odt`) | Document | `PDF`, `DOCX`, `TXT`, `RTF` |
| **Rich Text** (`.rtf`) | Document | `PDF`, `DOCX`, `TXT`, `ODT` |
| **Plain Text** (`.txt`) | Text | `PDF`, `DOCX`, `PPTX`, `RTF`, `HTML` |
| **CSV** (`.csv`) | Spreadsheet | `XLSX`, `PDF`, `JSON`, `HTML`, `TXT` |
| **Excel** (`.xlsx`, `.xls`) | Spreadsheet | `CSV`, `PDF`, `JSON`, `HTML` |
| **Images** (HEIC, JPG, PNG, etc.) | Image | `JPG`, `PNG`, `WEBP`, `HEIC`, `BMP`, `TIFF`, `GIF`, `ICO`, `PDF`, `TXT` (OCR), `DOCX` (OCR) |

---

## 📦 Installation & Quick Start

### Prerequisites
- **Python 3.10+** (Python 3.11, 3.12, 3.13, or 3.14 supported)
- Windows, macOS, or Linux

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

Universal File Converter includes a custom high-resolution application icon (`app_icon.ico` & `app_icon.png`) with full support for Windows taskbar grouping (AppUserModelID), title bar, and desktop shortcuts.

To create a **Windows Desktop and Start Menu shortcut** with the custom application icon:

```powershell
# Create Desktop shortcut with the application icon
.\launch_converter.bat --create-shortcut

# Or create via Python (supports --desktop and --start-menu)
python launch_converter.py --create-shortcut
```

### Launcher Command Guide

The project provides two primary launchers: `launch_converter.bat` and `launch_converter.py`.

#### 1. Windows Batch Launcher (`launch_converter.bat`)
- **Desktop GUI Mode**: Double-click `launch_converter.bat` or run `.\launch_converter.bat` with no arguments. It launches the PySide6 GUI in the background via `pythonw.exe` without leaving an open terminal window.
- **CLI Mode**: Pass any command line arguments to `launch_converter.bat`. It automatically detects arguments and runs synchronously in console mode with full output streaming:
  ```powershell
  # Show formats
  .\launch_converter.bat --list-formats

  # Convert files
  .\launch_converter.bat -i document.pdf -o document.docx
  ```
- **Shortcut Creation**:
  ```powershell
  .\launch_converter.bat --create-shortcut
  ```

#### 2. Python Unified Launcher (`launch_converter.py`)
- **Desktop GUI**: Run with no arguments (or `--gui`):
  ```powershell
  python launch_converter.py
  ```
- **Command-Line Interface**: Run with any conversion options:
  ```powershell
  python launch_converter.py -i sample.csv -o sample.xlsx
  ```
- **Create Shortcut**:
  ```powershell
  python launch_converter.py --create-shortcut
  ```

---

## 📦 Standalone Executable Packaging

You can package the entire application into a single standalone `.exe` file with the custom application icon embedded:

```powershell
# Build single-file executable with embedded icon and clean previous builds
python build_executable.py --onefile --clean

# Build executable and automatically create a Desktop shortcut pointing to it
python build_executable.py --onefile --clean --shortcut
```

The resulting executable is generated in the `dist/` directory:
- `dist/UniversalFileConverter.exe` (~100 MB standalone binary with zero external Python runtime required).


## 💻 Command Line Interface (CLI) Guide

The CLI is automatically invoked whenever arguments are provided to `launch_converter.py`.

### 1. Listing Supported Formats
```powershell
python launch_converter.py --list-formats
```

### 2. Document Conversions (PDF & Word)

#### Convert PDF to High-Resolution PNG Images
```powershell
# Render at default 150 DPI
python launch_converter.py -i document.pdf -f PNG -o ./output_images

# Render at high 300 DPI
python launch_converter.py -i document.pdf -f PNG -o ./output_images --dpi 300
```

#### Convert PDF to Word (.docx)
```powershell
python launch_converter.py -i report.pdf -o report.docx
```

#### Extract Plain Text from PDF
```powershell
python launch_converter.py -i book.pdf -o book.txt
```

#### Extract Tables from PDF to CSV or Excel
```powershell
python launch_converter.py -i financial_statement.pdf -o tables.csv
python launch_converter.py -i financial_statement.pdf -o tables.xlsx
```

#### Convert Word (.docx) to PDF
```powershell
python launch_converter.py -i proposal.docx -o proposal.pdf
```

#### Convert Word (.docx) to Plain Text or HTML
```powershell
python launch_converter.py -i article.docx -o article.txt
python launch_converter.py -i article.docx -o article.html
```

#### Convert Word (.docx) to Page Images
```powershell
python launch_converter.py -i manual.docx -f PNG -o ./page_images
```

---

### 3. Spreadsheet & Data Conversions (CSV & Excel)

#### Convert CSV to Styled Excel Workbook (.xlsx)
```powershell
python launch_converter.py -i data.csv -o data.xlsx
```

#### Convert CSV to Printable PDF Table Report
```powershell
python launch_converter.py -i customers.csv -o customers.pdf
```

#### Convert CSV to JSON or Responsive HTML
```powershell
python launch_converter.py -i data.csv -o data.json
python launch_converter.py -i data.csv -o data.html
```

#### Convert Excel (.xlsx) to CSV
```powershell
# Converts the active / first sheet
python launch_converter.py -i workbook.xlsx -o output.csv

# Specify a particular sheet by name
python launch_converter.py -i workbook.xlsx -o q3_sales.csv --sheet "Q3"
```

#### Convert Excel (.xlsx) to PDF Table Report
```powershell
python launch_converter.py -i balance_sheet.xlsx -o balance_sheet.pdf
```

---

### 4. Image Conversions

#### Convert Apple iPhone HEIC Photos to JPG or PNG
```powershell
python launch_converter.py -i IMG_1234.heic -o photo.jpg -q 92
python launch_converter.py -i IMG_1234.heic -o photo.png
```

#### Convert Image with Transparency to JPG with Custom Background
```powershell
# Composites alpha onto solid white background
python launch_converter.py -i logo.png -o logo.jpg --bg-color "#ffffff"

# Custom dark grey background
python launch_converter.py -i icon.png -o icon.jpg --bg-color "#1f2937"
```

#### Convert and Resize Image
```powershell
# Scale down by 50%
python launch_converter.py -i banner.jpg -o banner_small.jpg --resize-percent 50

# Fit inside 1920x1080 while keeping aspect ratio
python launch_converter.py -i raw.png -o wallpaper.webp --width 1920 --height 1080
```

#### Create Windows Icon (.ico) Bundle
```powershell
# Generates multi-size icon bundle (16, 32, 48, 64, 128, 256 px)
python launch_converter.py -i logo.png -o favicon.ico
```

---

### 5. Batch Directory Processing

### 5. Advanced Options: OCR, Security, Passwords, and Concurrency

#### OCR Text Extraction on Scanned PDFs and Images
```powershell
# Extract text from a scanned PDF page using OCR fallback
python launch_converter.py -i scanned_doc.pdf -o searchable.txt --ocr

# Convert image to editable Word (.docx) document via OCR
python launch_converter.py -i receipt_scan.jpg -o document.docx --ocr
```

#### Converting Encrypted / Password-Protected PDFs
```powershell
# Convert password-protected PDF to Word
python launch_converter.py -i secure_statement.pdf -o statement.docx --password "mySecret123"
```

#### Multithreaded Batch Processing & Concurrency
```powershell
# Process batch using 8 concurrent worker threads
python launch_converter.py -i ./large_batch -f WEBP -o ./converted --workers 8
```

#### Detailed Diagnostic Logging
```powershell
# Run with verbose debug output and write log file
python launch_converter.py -i ./documents -f PDF -o ./pdf_out -v --log-file ./converter.log
```

---

### 6. Privacy & Metadata Deletion

Universal File Converter allows you to inspect, sanitize, and completely purge personal tracking metadata, GPS locations, camera hardware identifiers, and office document author histories.

#### Inspect File for Sensitive Metadata & Tracking Tags
Inspect any image, PDF, or office document to reveal embedded metadata, tag counts, and security warnings:
```powershell
# Inspect metadata and display formatted privacy report
python launch_converter.py --inspect-metadata photo.jpg
python launch_converter.py --inspect-metadata confidential_report.pdf
python launch_converter.py -i contract.docx --inspect-metadata
```

#### Directly Strip / Clean Metadata Without Changing Format
Sanitize a file in-place or generate a cleaned copy (`<filename>_clean.<ext>`):
```powershell
# Strips all EXIF, GPS, and camera tags from JPEG, saving to photo_clean.jpg
python launch_converter.py --clean-metadata photo.jpg

# Strips author, title, producer, and XMP XML streams from PDF
python launch_converter.py --clean-metadata document.pdf

# Specify custom output path for the sanitized document
python launch_converter.py -i proposal.docx -o proposal_sanitized.docx --clean-metadata
```

#### Strip Metadata During Format Conversion
Purge metadata while converting to any target format:
```powershell
# Convert iPhone HEIC photo to JPEG with all EXIF and GPS tags stripped
python launch_converter.py -i IMG_001.heic -o IMG_001.jpg --strip-metadata

# Convert Word document to PDF without leaking author or revision tracking
python launch_converter.py -i memo.docx -o memo.pdf --strip-metadata
```

---

### 7. Batch Directory Processing

Convert an entire directory of files in one command:
```powershell
# Batch convert all images/documents in a folder to PDF
python launch_converter.py -i ./input_folder -f PDF -o ./pdf_results

# Batch clean metadata from all files in a folder
python launch_converter.py -i ./sensitive_docs -f STRIP_METADATA -o ./clean_docs
```

# Recursively scan subdirectories
python launch_converter.py -i ./photos -f WEBP -q 85 -o ./optimized_webp -r
```

---

## 🖥️ Desktop GUI Features

1. **Drag & Drop Landing Zone**:
   - Drag single files, multiple files, or full folders directly into the window.
   - Accepts images, PDFs, Word documents, PowerPoint presentations, ODT, RTF, CSV, and Excel spreadsheets.
2. **Interactive File Preview**:
   - **Images**: Live image preview thumbnail with dimensions, color mode, and alpha channel status.
   - **PDFs**: Live rendered first-page preview with total page count and point dimensions.
   - **Word (`.docx`)**: Summary card showing paragraph count, table count, and estimated word count.
   - **PowerPoint (`.pptx`)**: Slide count and presentation title preview.
   - **OpenDocument (`.odt`) & RTF**: Paragraph count, word count, and text summaries.
   - **Spreadsheets (`.csv`, `.xlsx`)**: Row count, column count, headers preview, and sheet names.
3. **Smart Conversion Settings**:
   - Format selector dynamically adjusts available settings.
   - Document Security: Enter password for encrypted files.
   - OCR Toggle: Enable automatic OCR text recognition for scanned pages and images.
   - Quality and DPI sliders, sheet selector, and rich resizing modes.
4. **Privacy & Metadata Deletion Controls**:
   - **Live Privacy Badge**: Preview card inspects file and displays `⚠️ Has metadata` with details or `🛡️ Clean (No tracking tags)`.
   - **Privacy Mode Toggle**: '🗑️ Strip all metadata (Privacy mode)' checkbox strips all personal identifiers, EXIF, and office properties automatically during conversion.
5. **Non-blocking Asynchronous Batch Processing**:
   - Multi-threaded worker keeps the interface 100% responsive during intensive batch operations.
   - Instant **Cancel** button aborts remaining batch items cleanly mid-job.
   - Per-file progress bar, real-time conversion status, and size reduction statistics.
6. **Direct Destination Handling**:
   - Option to output to the same directory or select a custom destination folder.
   - Convenient "Open Output Folder" button appears upon completion.

---

## 📦 Standalone Executable Packaging (PyInstaller)

Universal File Converter includes a production-ready PyInstaller build script and `.spec` file to generate an offline, standalone `.exe` desktop application without requiring Python on target machines:

```powershell
# Build standalone executable into dist/ directory
python build_executable.py

# Clean build artifacts before compiling
python build_executable.py --clean

# Build into a directory bundle instead of single-file
python build_executable.py --onedir
```

The resulting executable will be placed in `dist/UniversalFileConverter.exe`.

---

## 🐍 Python API Usage

You can embed the conversion and metadata sanitization engine directly into your own Python applications:

```python
from pathlib import Path
from image_converter.core.engine import UniversalConverterEngine, ConversionConfig
from image_converter.core.metadata_engine import strip_file_metadata, get_detailed_metadata

engine = UniversalConverterEngine()

# 1. Convert CSV to Excel
config_xlsx = ConversionConfig(target_format="XLSX")
result = engine.convert_single("data.csv", "data.xlsx", config_xlsx)
print(f"Success: {result.success}, File size: {result.output_size_bytes} bytes")

# 2. Convert PDF to PNG images (with password support)
config_png = ConversionConfig(target_format="PNG", dpi=200, password="optional_password")
result = engine.convert_single("paper.pdf", "page.png", config_png)
print(f"Rendered: {result.output_path}")

# 3. Convert Scanned PDF to Text with OCR fallback
config_ocr = ConversionConfig(target_format="TXT", enable_ocr=True)
result = engine.convert_single("scanned.pdf", "scanned.txt", config_ocr)

# 4. Inspect & Strip Metadata Directly
meta_info = get_detailed_metadata("contract.pdf")
print(f"Has metadata: {meta_info['has_metadata']}, Fields: {meta_info['fields']}")
strip_file_metadata("contract.pdf", "contract_clean.pdf")

# 5. Multithreaded Batch conversion with progress callback & cancellation
tasks = [
    (Path("file1.csv"), Path("file1.xlsx"), config_xlsx),
    (Path("doc.docx"), Path("doc.pdf"), ConversionConfig(target_format="PDF", strip_metadata=True)),
]

def on_progress(current, total, res):
    print(f"[{current}/{total}] Converted {res.input_path} -> {res.output_path}")

results = engine.convert_batch(tasks, progress_callback=on_progress, max_workers=4)
```

---

## 🧪 Testing

The repository features an exhaustive 79-test automated verification suite covering security, concurrency, edge cases, new formats, metadata sanitization, and all conversion routes:

```powershell
# Run the full 79-test suite
python -m pytest image_converter/tests -v

# Run individual test modules
python -m pytest image_converter/tests/test_metadata.py -v    # EXIF, PDF, DOCX, XLSX, PPTX, ODT metadata stripping
python -m pytest image_converter/tests/test_security.py -v    # Path traversal, zip bombs, magic bytes
python -m pytest image_converter/tests/test_edge_cases.py -v  # Corrupted files, passwords, non-UTF8 CSV
python -m pytest image_converter/tests/test_concurrency.py -v # Multithreading & cancellation
python -m pytest image_converter/tests/test_new_formats.py -v # PPTX, ODT, RTF pipelines
python -m pytest image_converter/tests/test_ocr.py -v         # OCR fallback detection
python -m pytest image_converter/tests/test_documents.py -v   # PDF and DOCX pipelines
python -m pytest image_converter/tests/test_data.py -v        # CSV and Excel pipelines
python -m pytest image_converter/tests/test_cli.py -v         # CLI argument parsing & flows
python -m pytest image_converter/tests/test_logging.py -v     # Logging & diagnostics
```

---

## 🏗️ Architecture & Security Design

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
│   ├── cli.py                   # Command-line interface with -v, --ocr, --strip-metadata, --clean-metadata
│   │
│   ├── core/                    # Core Engine & Pipelines
│   │   ├── engine.py            # Master UniversalConverterEngine dispatcher
│   │   ├── metadata_engine.py   # Privacy & metadata engine (EXIF, PDF, DOCX, XLSX, PPTX, ODT)
│   │   ├── document_engine.py   # PDF & Word DOCX conversion pipelines
│   │   ├── presentation_engine.py# PowerPoint (.pptx) conversion engine
│   │   ├── rich_doc_engine.py   # OpenDocument (.odt) & RTF conversion engine
│   │   ├── data_engine.py       # CSV & Excel XLSX conversion pipelines
│   │   ├── security.py          # Zip bomb defense, magic byte sniffing, traversal guard
│   │   ├── ocr_engine.py        # Tesseract OCR page rendering & extraction
│   │   └── logging_config.py    # Structured logging and diagnostics
│   │
│   ├── ui/                      # PySide6 Desktop GUI
│   │   ├── assets/              # UI brand assets (app_icon.ico, app_icon.png)
│   │   ├── main_window.py       # Main application window (AppUserModelID & Icon set)
│   │   ├── components.py        # DropZone, Preview, Settings, QueueTable
│   │   ├── theme.py             # Modern Dark Mode CSS stylesheet
│   │   └── worker.py            # Background QThread for non-blocking conversion
│   │
│   └── tests/                   # 79-Test Automated Verification Suite
│       ├── test_metadata.py     # Metadata stripping & inspection tests across all formats
│       ├── test_security.py     # Security & validation tests
│       ├── test_edge_cases.py   # Malformed, encrypted, and non-UTF8 tests
│       ├── test_concurrency.py  # Concurrency, workers & cancel tests
│       ├── test_new_formats.py  # PPTX, ODT, and RTF tests
│       ├── test_ocr.py          # OCR engine & fallback tests
│       ├── test_engine.py       # Core image engine tests
│       ├── test_documents.py    # PDF & Word tests
│       ├── test_data.py         # CSV & Excel tests
│       ├── test_cli.py          # CLI integration tests
│       └── test_logging.py      # Logging tests
```

---

## ❓ FAQ & Troubleshooting Guide

### 1. How do I enable OCR on Windows, macOS, or Linux?
Universal File Converter uses `pytesseract` to communicate with the system Tesseract OCR binary:
- **Windows**: Install via `winget install UB-Mannheim.TesseractOCR` or download the installer from GitHub. Make sure `tesseract.exe` is added to your PATH (default: `C:\Program Files\Tesseract-OCR`).
- **macOS**: Install via Homebrew: `brew install tesseract`.
- **Linux (Ubuntu/Debian)**: Install via apt: `sudo apt-get install tesseract-ocr`.
Once installed, pass `--ocr` in the CLI or check "Enable OCR Text Fallback" in the GUI.

### 2. How are encrypted / password-protected files handled?
- **PDF**: Pass `--password <secret>` in the CLI or enter the password in the GUI. If no password is provided, a clear error is returned without crashing.
- **Word / Office**: Modern encrypted Office documents (`.docx`, `.xlsx`, `.pptx`) are packaged as encrypted OLE compound storage. The engine detects this signature immediately and informs the user rather than failing with a generic corrupt zip error.

### 3. How does the converter handle non-UTF-8 CSV files?
The engine uses a tiered encoding detection pipeline:
1. Automatic BOM signature detection for `UTF-16` (LE/BE) and `UTF-8-SIG`.
2. Standard Western European encodings (`UTF-8`, `CP1252`, `Latin-1`, `ISO-8859-1`).
3. Statistical heuristic fallback via `charset-normalizer`.
4. Final replacement mode (`encoding_errors="replace"`) to guarantee clean, uncorrupted ingestion.

### 4. What security defenses are built in?
- **Zip Bombs**: Checks container ratio (max 100:1), total uncompressed bytes (max 500MB), and total entry count (max 50,000) on all OpenPackaging formats (`.docx`, `.xlsx`, `.pptx`, `.odt`).
- **Path Traversal**: Resolves paths and validates that output paths cannot escape intended directories or contain null bytes (`\x00`).
- **Magic Byte Sniffing**: Inspects the true file header bytes (e.g. `%PDF-`, `\x89PNG`, `PK\x03\x04`, `{\rtf`) to prevent extension-spoofing attacks.
- **0-Byte & Oversized Files**: 0-byte files are rejected early with helpful errors; input files exceeding 500MB are safely blocked before decompression.

### 5. Does converting Word or PowerPoint require Microsoft Office?
**No.** All conversions use pure-Python headless libraries (`reportlab`, `python-docx`, `python-pptx`, `striprtf`, `odfpy`). You do not need Microsoft Office, LibreOffice, or Word installed.

---

## 📄 License

MIT License. Free for personal and commercial use.

