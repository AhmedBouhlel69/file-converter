"""Presentation-only evidence for the metadata fields the existing inspector reads."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import RLock
import warnings
import xml.etree.ElementTree as ET
import zipfile

from image_converter.core.metadata import engine as metadata_engine

_INSPECTION_WARNING_LOCK = RLock()


@dataclass(frozen=True)
class MetadataEvidence:
    status: str
    fields: tuple[str, ...] = ()
    detail: str = ""
    partial: bool = False

    @property
    def summary(self) -> str:
        if self.status == "found":
            count = len(self.fields)
            return f"{count} supported metadata field{'s' if count != 1 else ''} found"
        if self.status == "not_found":
            return "No supported metadata found"
        if self.status == "failed":
            return "Metadata could not be inspected"
        return "Metadata inspection unavailable"

    @property
    def output_text(self) -> str:
        text = f"Output check: {self.summary}."
        if self.partial:
            text += " Only the first output file was checked."
        return text


def inspect_metadata(path: str | Path, password: str | None = None, *, partial: bool = False) -> MetadataEvidence:
    """Do not interpret an unsupported or failed inspection as a clean result."""
    file_path = Path(path)
    extension = file_path.suffix.lower()
    supported = {
        ".jpg", ".jpeg", ".png", ".webp", ".tiff", ".tif", ".heic", ".heif", ".bmp", ".pdf", ".odt",
    }
    optional = {
        ".docx": metadata_engine._DOCX_AVAILABLE,
        ".pptx": metadata_engine._PPTX_AVAILABLE,
        ".xlsx": metadata_engine._OPENPYXL_AVAILABLE,
        ".xlsm": metadata_engine._OPENPYXL_AVAILABLE,
    }
    if extension not in supported and not optional.get(extension, False):
        return MetadataEvidence("unavailable", detail="This format or its metadata reader is unavailable.", partial=partial)
    try:
        if extension == ".odt":
            # The existing reader logs XML parse errors without returning a warning.
            with zipfile.ZipFile(file_path) as archive:
                if "meta.xml" in archive.namelist():
                    # Match the existing reader's decoding, including its limits.
                    ET.fromstring(archive.read("meta.xml").decode("utf-8", errors="replace"))
        if extension == ".pdf":
            with metadata_engine.fitz.open(str(file_path)) as document:
                if document.needs_pass and not (password and document.authenticate(password)):
                    return MetadataEvidence("unavailable", detail="A valid PDF password is required for inspection.", partial=partial)
        # Warning contexts are global on some Python builds. Inspector and worker
        # checks must not restore or consume each other's warning filters.
        with _INSPECTION_WARNING_LOCK:
            with warnings.catch_warnings(record=True) as reader_warnings:
                warnings.simplefilter("always")
                metadata = metadata_engine.get_detailed_metadata(file_path, password=password)
        parse_warnings = [
            str(warning.message) for warning in reader_warnings
            if any(term in str(warning.message).lower() for term in ("corrupt", "truncat", "invalid", "malformed", "parse", "exif"))
        ]
        if parse_warnings:
            return MetadataEvidence("failed", detail="\n".join(parse_warnings), partial=partial)
        inspection_warnings = tuple(str(warning) for warning in metadata.get("warnings", ()))
        if any("inspection failed" in warning.lower() for warning in inspection_warnings):
            return MetadataEvidence("failed", detail="\n".join(inspection_warnings), partial=partial)
        fields = tuple(str(field) for field in metadata.get("fields", {}))
        if metadata.get("has_metadata") and not fields:
            return MetadataEvidence("failed", detail="The metadata reader did not return field evidence.", partial=partial)
        return MetadataEvidence("found" if fields else "not_found", fields, "\n".join(inspection_warnings), partial)
    except Exception as error:
        return MetadataEvidence("failed", detail=str(error), partial=partial)


def metadata_check_summary(evidence: list[MetadataEvidence]) -> str:
    if not evidence:
        return ""
    found = sum(item.status == "found" for item in evidence)
    absent = sum(item.status == "not_found" for item in evidence)
    unknown = len(evidence) - found - absent
    return (
        f"Output metadata checks: {absent} with no supported fields found; "
        f"{found} with supported fields; {unknown} unavailable or failed. "
        "Select a row for details."
    )
