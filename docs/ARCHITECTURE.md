# Project Architecture

Universal File Converter is a local desktop and CLI application. The code is organized as a modular monolith: each domain has its own package boundary, while everything still runs in one local process for speed, offline privacy, and simple packaging.

## Runtime Entry Points

| Area | Path | Responsibility |
| :--- | :--- | :--- |
| Desktop app | `image_converter/ui/` | PySide6 windows, dialogs, queue model, theme, and background worker glue |
| CLI | `image_converter/cli.py` | Argument parsing, batch file collection, and command-line execution |
| Core services | `image_converter/core/` | Conversion, PDF tools, metadata cleaning, OCR, validation, logging, and platform integration |

## Core Service Packages

| Service Package | Main Module | Responsibility |
| :--- | :--- | :--- |
| `core/conversion/` | `engine.py` | Main conversion orchestrator, image conversion, batch conversion, result verification |
| `core/documents/` | `engine.py` | PDF and Word document conversions |
| `core/data/` | `engine.py` | CSV, Excel, JSON, HTML, and table-oriented conversions |
| `core/presentations/` | `engine.py` | PowerPoint conversion paths |
| `core/rich_documents/` | `engine.py` | ODT and RTF conversion paths |
| `core/pdf/` | `tools.py` | PDF merge, split, organize, rotate, extract, and compress tools |
| `core/metadata/` | `engine.py` | Metadata inspection and stripping for images, PDFs, Office, and ODT |
| `core/ocr/` | `engine.py` | OCR availability checks and Tesseract-backed extraction |
| `core/safety/` | `security.py` | Input validation, output path validation, magic-byte sniffing, zip-bomb defenses |
| `core/platform/` | `com_utils.py` | Windows COM helpers and thread-local COM initialization |
| `core/observability/` | `logging_config.py` | Logging setup and logger access |

## Compatibility Layer

The previous flat import paths still exist as thin wrappers:

- `image_converter.core.engine`
- `image_converter.core.document_engine`
- `image_converter.core.data_engine`
- `image_converter.core.presentation_engine`
- `image_converter.core.rich_doc_engine`
- `image_converter.core.pdf_tools`
- `image_converter.core.metadata_engine`
- `image_converter.core.ocr_engine`
- `image_converter.core.security`
- `image_converter.core.com_utils`
- `image_converter.core.logging_config`

New code should prefer the service packages. Existing tests, scripts, and external callers can keep using the old paths until they are migrated.

## Why Not Separate Processes Yet?

The app handles private local files and ships as a desktop executable, so splitting into networked microservices would add packaging, IPC, permissions, and failure-mode complexity without a clear payoff. This layout gives the useful part of a microservice structure, clear bounded modules, while keeping local execution simple.

If the app later needs true service isolation, the clean package boundaries here are the seams to extract first:

1. `core/conversion/` as a conversion worker service.
2. `core/pdf/` as a PDF utility service.
3. `core/metadata/` and `core/safety/` as validation and sanitization services.
4. `ui/` and `cli.py` as clients of those services.
