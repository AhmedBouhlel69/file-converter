"""
Core conversion engine and format utilities.
Supports Images, PDF, Word, CSV, and Excel.
"""

from .data_engine import DataConverter, get_csv_metadata, get_excel_metadata
from .document_engine import DocumentConverter, get_docx_metadata, get_pdf_metadata
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
]
