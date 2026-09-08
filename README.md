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
  - [Launch Desktop GUI](#launch-desktop-gui)
- [Command Line Interface (CLI) Guide](#-command-line-interface-cli-guide)
  - [Listing Formats](#1-listing-supported-formats)
  - [Document Conversions (PDF & Word)](#2-document-conversions-pdf--word)
  - [Spreadsheet & Data Conversions (CSV & Excel)](#3-spreadsheet--data-conversions-csv--excel)
  - [Image Conversions](#4-image-conversions)
  - [Batch Directory Processing](#5-batch-directory-processing)
- [Desktop GUI Features](#-desktop-gui-features)
- [Python API Usage](#-python-api-usage)
- [Testing](#-testing)
- [Architecture & Design](#-architecture--design)
- [FAQ & Troubleshooting](#-faq--troubleshooting)

---

## 🚀 Key Features

- **Multi-Category File Conversion**:
  - **Documents**: Convert **PDF** to high-res images, Word (`.docx`), plain text, and extract data tables into Excel/CSV. Convert **Word (`.docx`)** to printable PDF, formatted text, HTML, and images.
  - **Spreadsheets & Data**: Convert **CSV** to styled Excel workbooks (`.xlsx`), printable PDF tables, JSON, and responsive HTML. Convert **Excel (`.xlsx`)** to CSV, PDF reports, JSON, and HTML.
  - **Images**: Seamlessly batch convert and resize between **HEIC, JPG, PNG, WEBP, BMP, TIFF, GIF, ICO, and PDF**.
- **100% Offline & Private**: All conversions run locally on your computer. Your documents, photos, and spreadsheets are never uploaded to any external server.
- **Headless & Standalone Word Conversion**: Converts `.docx` to PDF using a pure-Python ReportLab pipeline with zero dependency on Microsoft Word or Office installation.
- **Ultra-Fast PDF Engine**: Powered by `PyMuPDF` (`fitz`), enabling page-by-page rendering, sub-second text extraction, and automatic table detection.
- **Dual Interface**:
  - **Modern Dark-Mode Desktop GUI** with Drag & Drop, rich file preview (live PDF rendering, document word counts, spreadsheet dimension stats), customizable options, and batch queue.
  - **Full-featured CLI** for scripting, terminal power users, and automated workflows.
- **Apple HEIC/HEIF Support**: Native decode and encode for modern iPhone photos via `pillow-heif`.
- **Advanced Processing Options**:
  - Quality compression (1–100%) for lossy formats (JPG, WEBP, HEIC)
  - DPI resolution control for document rendering (50–600 DPI)
  - Smart transparency compositing onto customizable backgrounds
  - Auto-orientation transpose via camera EXIF tags
  - Aspect-ratio locked image resizing (percentage, custom dimensions, or bounding box)

---

## 🔄 Supported Formats & Conversion Matrix

| Input Format | Category | Target Output Formats |
| :--- | :--- | :--- |
| **PDF** (`.pdf`) | Document | `PNG`, `JPG`, `WEBP`, `DOCX`, `TXT`, `CSV`, `XLSX` |
| **Word** (`.docx`, `.doc`) | Document | `PDF`, `TXT`, `HTML`, `PNG`, `JPG`, `WEBP` |
| **CSV** (`.csv`) | Spreadsheet | `XLSX`, `PDF`, `JSON`, `HTML`, `TXT` |
| **Excel** (`.xlsx`, `.xls`) | Spreadsheet | `CSV`, `PDF`, `JSON`, `HTML` |
| **JPEG** (`.jpg`, `.jpeg`) | Image | `PNG`, `WEBP`, `HEIC`, `BMP`, `TIFF`, `GIF`, `ICO`, `PDF` |
| **PNG** (`.png`) | Image | `JPG`, `WEBP`, `HEIC`, `BMP`, `TIFF`, `GIF`, `ICO`, `PDF` |
| **HEIC / HEIF** (`.heic`, `.heif`) | Image | `JPG`, `PNG`, `WEBP`, `BMP`, `TIFF`, `GIF`, `ICO`, `PDF` |
| **WEBP** (`.webp`) | Image | `JPG`, `PNG`, `HEIC`, `BMP`, `TIFF`, `GIF`, `ICO`, `PDF` |
| **BMP** (`.bmp`, `.dib`) | Image | `JPG`, `PNG`, `WEBP`, `HEIC`, `TIFF`, `GIF`, `ICO`, `PDF` |
| **TIFF** (`.tiff`, `.tif`) | Image | `JPG`, `PNG`, `WEBP`, `HEIC`, `BMP`, `GIF`, `ICO`, `PDF` |
| **GIF** (`.gif`) | Image | `JPG`, `PNG`, `WEBP`, `HEIC`, `BMP`, `TIFF`, `ICO`, `PDF` |
| **ICO** (`.ico`) | Image | `JPG`, `PNG`, `WEBP`, `HEIC`, `BMP`, `TIFF`, `GIF`, `PDF` |
| **PPM / TGA / EPS** | Image | `JPG`, `PNG`, `WEBP`, `HEIC`, `BMP`, `TIFF`, `GIF`, `ICO`, `PDF` |

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

### Launch Desktop GUI

- **On Windows**: Double-click `launch_converter.bat`, or run:
  ```powershell
  .\venv\Scripts\python.exe launch_converter.py
  ```
- **On macOS / Linux**:
  ```bash
  ./venv/bin/python launch_converter.py
  ```

---

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

Convert an entire directory of files in one command:
```powershell
# Batch convert all images/documents in a folder to PDF
python launch_converter.py -i ./input_folder -f PDF -o ./pdf_results

# Recursively scan subdirectories
python launch_converter.py -i ./photos -f WEBP -q 85 -o ./optimized_webp -r
```

---

## 🖥️ Desktop GUI Features

1. **Drag & Drop Landing Zone**:
   - Drag single files, multiple files, or full folders directly into the window.
   - Accepts images, PDFs, Word documents, CSV, and Excel spreadsheets.
2. **Interactive File Preview**:
   - **Images**: Live image preview thumbnail with dimensions, color mode, and alpha channel status.
   - **PDFs**: Live rendered first-page preview with total page count and point dimensions.
   - **Word (`.docx`)**: Summary card showing paragraph count, table count, and estimated word count.
   - **Spreadsheets (`.csv`, `.xlsx`)**: Summary card showing row count, column count, column names, and sheet names.
3. **Smart Conversion Settings**:
   - Format selector intelligently adjusts available options based on target format.
   - Sliders for quality (lossy formats) and DPI (PDF/DOCX rendering).
   - Sheet selector for Excel spreadsheets.
   - Resizing modes: Original, Percentage Scale, Custom Width & Height, or Max Bounding Box.
4. **Non-blocking Asynchronous Batch Processing**:
   - Multi-threaded worker keeps the interface 100% responsive during intensive batch operations.
   - Per-file progress bar, real-time conversion status, and size reduction statistics.
5. **Direct Destination Handling**:
   - Option to output to the same directory or select a custom destination folder.
   - Convenient "Open Output Folder" button appears upon completion.

---

## 🐍 Python API Usage

You can embed the conversion engine directly into your own Python applications:

```python
from pathlib import Path
from image_converter.core.engine import UniversalConverterEngine, ConversionConfig

engine = UniversalConverterEngine()

# 1. Convert CSV to Excel
config_xlsx = ConversionConfig(target_format="XLSX")
result = engine.convert_single("data.csv", "data.xlsx", config_xlsx)
print(f"Success: {result.success}, File size: {result.output_size_bytes} bytes")

# 2. Convert PDF to PNG images
config_png = ConversionConfig(target_format="PNG", dpi=200)
result = engine.convert_single("paper.pdf", "page.png", config_png)
print(f"Rendered: {result.output_path}")

# 3. Convert Word DOCX to PDF
config_pdf = ConversionConfig(target_format="PDF")
result = engine.convert_single("document.docx", "document.pdf", config_pdf)
print(f"PDF generated in {result.duration_seconds:.3f}s")

# 4. Batch conversion with progress callback
tasks = [
    (Path("file1.csv"), Path("file1.xlsx"), config_xlsx),
    (Path("doc.docx"), Path("doc.pdf"), config_pdf),
]

def on_progress(current, total, res):
    print(f"[{current}/{total}] Converted {res.input_path} -> {res.output_path}")

results = engine.convert_batch(tasks, progress_callback=on_progress)
```

---

## 🧪 Testing

The repository contains an automated test suite verifying all conversion pathways:

```powershell
# Run the full test suite
python -m pytest image_converter/tests -v

# Run document tests only
python -m pytest image_converter/tests/test_documents.py -v

# Run spreadsheet/data tests only
python -m pytest image_converter/tests/test_data.py -v

# Run CLI tests only
python -m pytest image_converter/tests/test_cli.py -v
```

---

## 🏗️ Architecture & Design

```
file converter/
│
├── launch_converter.py          # Unified entry point (CLI router & GUI launcher)
├── launch_converter.bat         # Windows double-click desktop launcher
├── main.py                      # Compatibility entry point
│
├── image_converter/
│   ├── requirements.txt         # Project dependencies
│   ├── cli.py                   # Command-line interface parser & batch runner
│   │
│   ├── core/                    # Conversion Engines
│   │   ├── engine.py            # UniversalConverterEngine master dispatcher
│   │   ├── document_engine.py   # PDF & Word DOCX conversion pipelines
│   │   └── data_engine.py       # CSV & Excel XLSX conversion pipelines
│   │
│   ├── ui/                      # PySide6 Desktop GUI
│   │   ├── main_window.py       # Main application window
│   │   ├── components.py        # DropZone, FilePreview, Settings, QueueTable
│   │   ├── theme.py             # Modern Dark Mode CSS stylesheet
│   │   └── worker.py            # Background QThread for non-blocking conversion
│   │
│   └── tests/                   # Automated Pytest Suite
│       ├── test_engine.py       # Image conversion tests
│       ├── test_documents.py    # PDF and Word conversion tests
│       ├── test_data.py         # CSV and Excel conversion tests
│       └── test_cli.py          # CLI integration tests
```

---

## ❓ FAQ & Troubleshooting

### Does converting Word (.docx) to PDF require Microsoft Office?
**No.** The conversion uses a pure-Python layout generator built on `reportlab` and `python-docx`. It runs 100% headless and does not require Microsoft Word or Office to be installed.

### Can I extract tables from a multi-page PDF into Excel?
**Yes.** PyMuPDF's table detection locates tabular structures across all pages in the PDF and compiles them into an Excel workbook (`.xlsx`) or CSV file.

### How are multi-page PDFs handled when converting to images?
If you convert a multi-page PDF to PNG/JPG with an output file specified (e.g., `-o page.png`), the first page is written to `page.png`, and subsequent pages are saved as `page_page_2.png`, `page_page_3.png`, etc. If you specify an output folder, all pages are exported cleanly.

### What if the destination file name matches the source file?
To prevent accidental data loss, the CLI rejects tasks where input and output paths are identical unless an explicit output format or directory is specified. In the Desktop GUI, `_converted` is automatically appended to avoid overwriting your original file.

---

## 📄 License

MIT License. Free for personal and commercial use.
