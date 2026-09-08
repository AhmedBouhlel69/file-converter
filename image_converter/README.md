# Universal File Converter

A fast, cross-platform, local desktop and CLI file conversion application built with Python, PySide6 (Qt6), PyMuPDF, python-docx, ReportLab, pandas, openpyxl, and Pillow.

Convert between **PDF, Word (DOCX), Excel (XLSX), CSV**, and **Images (HEIC, JPG, PNG, WEBP, BMP, TIFF, GIF, ICO)** locally on your machine with zero cloud upload required.

---

## Key Features

- **Wide Format Support**:
  - **Documents**: PDF, Word (`.docx`, `.doc`), Text (`.txt`), HTML
  - **Spreadsheets & Data**: CSV, Excel (`.xlsx`, `.xls`), JSON, HTML
  - **Images**: HEIC, HEIF, JPG, JPEG, PNG, WEBP, BMP, TIFF, GIF, ICO, PPM, TGA, EPS
- **Offline & Private**: 100% local processing; no files ever leave your system.
- **Standalone Word-to-PDF**: Converts Word documents to PDF without requiring Microsoft Word or Office installation.
- **Fast PDF Processing**: Uses PyMuPDF for page-by-page image rendering, text extraction, and automatic table detection.
- **Full Apple HEIC Support**: iPhone HEIC/HEIF photo decoding and encoding via `pillow-heif`.
- **Drag & Drop Desktop GUI**: Modern Dark Mode interface with real-time file previews, metadata stats, and batch progress tracking.
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

Automated pytest suite validates conversions across formats:
```powershell
.\venv\Scripts\python.exe -m pytest image_converter/tests/ -v
```
