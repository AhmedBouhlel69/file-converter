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

# Batch convert an entire folder to PDF
.\venv\Scripts\python.exe launch_converter.py -i ./docs_and_images -f PDF -o ./all_pdfs
```

---

## Running Tests

Automated 79-test pytest suite validates security, metadata stripping, and conversions across all formats:
```powershell
.\venv\Scripts\python.exe -m pytest image_converter/tests/ -v
```
