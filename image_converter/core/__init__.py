"""
Core conversion engine and format utilities.
Supports Images, PDF, Word, CSV, and Excel.
"""

from .data_engine import DataConverter, get_csv_metadata, get_excel_metadata
from .document_engine import (
    DocumentConverter,
    check_docx_encryption,
    get_docx_metadata,
    get_pdf_metadata,
    open_pdf_with_password,
)
from .presentation_engine import PresentationConverter, get_pptx_metadata
from .rich_doc_engine import RichDocumentConverter, get_odt_metadata, get_rtf_metadata
from .security import (
    SecurityError,
    sniff_file_type,
    validate_input_file,
    validate_output_path,
    validate_zip_container,
)
from .ocr_engine import (
    get_ocr_status_message,
    is_ocr_available,
    ocr_image_to_text,
    ocr_pdf_page,
    ocr_pdf_to_text,
    pdf_needs_ocr,
)
from .logging_config import get_logger, setup_logger
from .metadata_engine import (
    get_detailed_metadata,
    strip_docx_metadata,
    strip_file_metadata,
    strip_image_metadata,
    strip_odt_metadata,
    strip_pdf_metadata,
    strip_pptx_metadata,
    strip_xlsx_metadata,
)
from .engine import (
    FORMAT_EXTENSIONS,
    SUPPORTED_INPUT_FORMATS,
    SUPPORTED_OUTPUT_FORMATS,
    ConversionConfig,
    ConversionResult,
    ImageConverterEngine,
    UniversalConverterEngine,
    get_file_metadata,
    get_image_metadata,
    get_supported_input_extensions,
    get_supported_output_formats,
)

__all__ = [
    "ImageConverterEngine",
    "UniversalConverterEngine",
    "DocumentConverter",
    "DataConverter",
    "PresentationConverter",
    "RichDocumentConverter",
    "ConversionConfig",
    "ConversionResult",
    "SUPPORTED_INPUT_FORMATS",
    "SUPPORTED_OUTPUT_FORMATS",
    "FORMAT_EXTENSIONS",
    "get_supported_input_extensions",
    "get_supported_output_formats",
    "get_image_metadata",
    "get_file_metadata",
    "get_pdf_metadata",
    "get_docx_metadata",
    "get_csv_metadata",
    "get_excel_metadata",
    "get_pptx_metadata",
    "get_odt_metadata",
    "get_rtf_metadata",
    "open_pdf_with_password",
    "check_docx_encryption",
    "SecurityError",
    "sniff_file_type",
    "validate_input_file",
    "validate_output_path",
    "validate_zip_container",
    "is_ocr_available",
    "get_ocr_status_message",
    "ocr_image_to_text",
    "ocr_pdf_page",
    "ocr_pdf_to_text",
    "pdf_needs_ocr",
    "setup_logger",
    "get_logger",
    "get_detailed_metadata",
    "strip_file_metadata",
    "strip_image_metadata",
    "strip_pdf_metadata",
    "strip_docx_metadata",
    "strip_xlsx_metadata",
    "strip_pptx_metadata",
    "strip_odt_metadata",
]
