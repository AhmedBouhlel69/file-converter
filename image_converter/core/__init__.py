"""
Core conversion engine and format utilities.
Supports Images, PDF, Word, CSV, and Excel.

Uses lazy imports via __getattr__ to avoid loading heavy libraries
(pandas, openpyxl, pdf2docx, pptx, odf) at startup.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Lazy-import registry: maps symbol name -> (module_path, name_in_module)
# ---------------------------------------------------------------------------
_LAZY_IMPORTS: dict[str, tuple[str, str]] = {}


def _register(module: str, *names: str) -> None:
    for n in names:
        _LAZY_IMPORTS[n] = (module, n)


# --- data_engine ---
_register(
    ".data_engine",
    "DataConverter",
    "get_csv_metadata",
    "get_excel_metadata",
)

# --- document_engine ---
_register(
    ".document_engine",
    "DocumentConverter",
    "check_docx_encryption",
    "get_docx_metadata",
    "get_pdf_metadata",
    "open_pdf_with_password",
)

# --- pdf_tools (100% local, fast) ---
_register(
    ".pdf_tools",
    "merge_pdfs",
    "split_pdf",
    "remove_pages",
    "extract_pages",
    "organize_pages",
    "rotate_pdf",
    "compress_pdf",
)

# --- pdf_toolkit_engine (facade / compatibility) ---
_register(
    ".pdf_toolkit_engine",
    "PDFToolkitEngine",
    "images_to_pdf",
    "repair_pdf",
    "ocr_pdf",
    "word_to_pdf",
    "powerpoint_to_pdf",
    "excel_to_pdf",
    "html_to_pdf",
    "pdf_to_images",
    "pdf_to_word",
    "pdf_to_powerpoint",
    "pdf_to_excel",
    "pdf_to_pdfa",
    "edit_pdf_content",
    "add_page_numbers",
    "add_watermark",
    "crop_pdf",
    "get_form_fields",
    "fill_form_fields",
    "add_form_field",
    "export_form_data",
    "protect_pdf",
    "unlock_pdf",
    "sign_pdf",
    "redact_pdf",
    "summarize_pdf",
    "translate_pdf",
    "pdf_to_markdown",
    "compare_pdfs",
)

# --- presentation_engine ---
_register(
    ".presentation_engine",
    "PresentationConverter",
    "get_pptx_metadata",
)

# --- rich_doc_engine ---
_register(
    ".rich_doc_engine",
    "RichDocumentConverter",
    "get_odt_metadata",
    "get_rtf_metadata",
)

# --- security ---
_register(
    ".security",
    "SecurityError",
    "sniff_file_type",
    "validate_input_file",
    "validate_output_path",
    "validate_zip_container",
)

# --- ocr_engine ---
_register(
    ".ocr_engine",
    "is_ocr_available",
    "get_ocr_status_message",
    "ocr_image_to_text",
    "ocr_pdf_page",
    "ocr_pdf_to_text",
    "pdf_needs_ocr",
)

# --- logging_config ---
_register(
    ".logging_config",
    "setup_logger",
    "get_logger",
)

# --- metadata_engine ---
_register(
    ".metadata_engine",
    "get_detailed_metadata",
    "strip_file_metadata",
    "strip_image_metadata",
    "strip_pdf_metadata",
    "strip_docx_metadata",
    "strip_xlsx_metadata",
    "strip_pptx_metadata",
    "strip_odt_metadata",
)

# --- engine ---
_register(
    ".engine",
    "FORMAT_EXTENSIONS",
    "SUPPORTED_INPUT_FORMATS",
    "SUPPORTED_OUTPUT_FORMATS",
    "ConversionConfig",
    "ConversionResult",
    "ImageConverterEngine",
    "UniversalConverterEngine",
    "get_file_metadata",
    "get_image_metadata",
    "get_supported_input_extensions",
    "get_supported_output_formats",
)


# ---------------------------------------------------------------------------
# __getattr__: Python calls this when a name is not found in the module dict
# ---------------------------------------------------------------------------
def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module_path, attr_name = _LAZY_IMPORTS[name]
        import importlib
        mod = importlib.import_module(module_path, package=__name__)
        value = getattr(mod, attr_name)
        # Cache in module namespace so __getattr__ is not called again
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ---------------------------------------------------------------------------
# __all__ for star imports and documentation
# ---------------------------------------------------------------------------
__all__ = list(_LAZY_IMPORTS.keys())
