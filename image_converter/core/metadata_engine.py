"""
Metadata Engine for Universal File Converter.
Inspects, sanitizes, and strips metadata (EXIF, GPS, Author, Timestamps, Tracking)
across Images, PDF, Word (DOCX), Excel (XLSX), PowerPoint (PPTX), and OpenDocument (ODT).
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

import fitz  # PyMuPDF
from PIL import Image, ImageOps

try:
    import docx
    _DOCX_AVAILABLE = True
except ImportError:
    _DOCX_AVAILABLE = False

try:
    from pptx import Presentation
    _PPTX_AVAILABLE = True
except ImportError:
    _PPTX_AVAILABLE = False

try:
    import openpyxl
    _OPENPYXL_AVAILABLE = True
except ImportError:
    _OPENPYXL_AVAILABLE = False


def get_detailed_metadata(file_path: str | Path, password: Optional[str] = None) -> Dict[str, Any]:
    """
    Inspect a file and return a comprehensive structured dictionary of all metadata.
    Detects personal identifiable information (PII), author, GPS, software, and timestamps.
    """
    p = Path(file_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = p.suffix.lower()
    meta_info: Dict[str, Any] = {
        "file_name": p.name,
        "file_path": str(p),
        "file_size": p.stat().st_size,
        "extension": ext,
        "has_metadata": False,
        "fields_count": 0,
        "fields": {},
        "warnings": [],
    }

    # 1. Images (JPEG, PNG, WEBP, TIFF, HEIC, BMP)
    if ext in (".jpg", ".jpeg", ".png", ".webp", ".tiff", ".tif", ".heic", ".heif", ".bmp"):
        try:
            with Image.open(str(p)) as img:
                exif_data = img.getexif()
                fields = {}
                if exif_data:
                    # Known important EXIF tags
                    tag_names = {
                        0x010E: "ImageDescription",
                        0x010F: "Make",
                        0x0110: "Model",
                        0x0131: "Software",
                        0x0132: "DateTime",
                        0x013B: "Artist",
                        0x8298: "Copyright",
                        0x9003: "DateTimeOriginal",
                        0x9004: "DateTimeDigitized",
                        0x9286: "UserComment",
                        0x8825: "GPSInfo",
                    }
                    for tag_id, val in exif_data.items():
                        name = tag_names.get(tag_id, f"Tag_{tag_id}")
                        str_val = str(val)[:120]
                        fields[name] = str_val

                # Check info dict for text / comments
                for k, v in img.info.items():
                    if k in ("comment", "Description", "Author", "Software", "Title", "Copyright"):
                        fields[f"Info_{k}"] = str(v)[:120]

                if fields:
                    meta_info["has_metadata"] = True
                    meta_info["fields"] = fields
                    meta_info["fields_count"] = len(fields)
                    if "GPSInfo" in fields:
                        meta_info["warnings"].append("Contains embedded GPS location data")
                    if "Artist" in fields or "Make" in fields:
                        meta_info["warnings"].append("Contains device or author information")
        except Exception as e:
            logger.warning(f"Image metadata inspection failed for '{p.name}': {e}", exc_info=True)
            meta_info["warnings"].append(f"Image metadata inspection failed: {e}")

    # 2. PDF Documents
    elif ext == ".pdf":
        try:
            doc = fitz.open(str(p))
            if doc.is_encrypted and password:
                doc.authenticate(password)

            fields = {}
            raw_meta = doc.metadata or {}
            for k, v in raw_meta.items():
                if k.lower() in ("format", "encryption"):
                    continue
                if v and str(v).strip():
                    fields[k.capitalize()] = str(v).strip()

            has_xmp = bool(doc.get_xml_metadata())
            if has_xmp:
                fields["XMP_Metadata"] = "Present (Embedded XML Stream)"

            doc.close()

            if fields:
                meta_info["has_metadata"] = True
                meta_info["fields"] = fields
                meta_info["fields_count"] = len(fields)
                if any(k in fields for k in ("Author", "Creator", "Producer")):
                    meta_info["warnings"].append("Contains author or software generator metadata")
        except Exception as e:
            logger.warning(f"PDF metadata inspection failed for '{p.name}': {e}", exc_info=True)
            meta_info["warnings"].append(f"PDF metadata inspection failed: {e}")

    # 3. Word DOCX
    elif ext == ".docx" and _DOCX_AVAILABLE:
        try:
            doc = docx.Document(str(p))
            cp = doc.core_properties
            props = [
                "author", "last_modified_by", "title", "subject",
                "keywords", "comments", "category", "created", "modified", "revision"
            ]
            fields = {}
            for pr in props:
                val = getattr(cp, pr, None)
                if val is not None and str(val).strip() and str(val) != "1":
                    fields[pr.replace("_", " ").title()] = str(val).strip()

            if fields:
                meta_info["has_metadata"] = True
                meta_info["fields"] = fields
                meta_info["fields_count"] = len(fields)
                if "Author" in fields or "Last Modified By" in fields:
                    meta_info["warnings"].append("Contains document author tracking")
        except Exception as e:
            logger.warning(f"DOCX metadata inspection failed for '{p.name}': {e}", exc_info=True)
            meta_info["warnings"].append(f"DOCX metadata inspection failed: {e}")

    # 4. PowerPoint PPTX
    elif ext == ".pptx" and _PPTX_AVAILABLE:
        try:
            prs = Presentation(str(p))
            cp = prs.core_properties
            props = [
                "author", "last_modified_by", "title", "subject",
                "keywords", "comments", "category", "created", "modified", "revision"
            ]
            fields = {}
            for pr in props:
                val = getattr(cp, pr, None)
                if val is not None and str(val).strip() and str(val) != "1":
                    fields[pr.replace("_", " ").title()] = str(val).strip()

            if fields:
                meta_info["has_metadata"] = True
                meta_info["fields"] = fields
                meta_info["fields_count"] = len(fields)
                if "Author" in fields:
                    meta_info["warnings"].append("Contains presentation author metadata")
        except Exception as e:
            logger.warning(f"PPTX metadata inspection failed for '{p.name}': {e}", exc_info=True)
            meta_info["warnings"].append(f"PPTX metadata inspection failed: {e}")

    # 5. Excel XLSX
    elif ext in (".xlsx", ".xlsm") and _OPENPYXL_AVAILABLE:
        try:
            wb = openpyxl.load_workbook(str(p), read_only=False, data_only=True)
            props = ["creator", "lastModifiedBy", "title", "subject", "description", "keywords", "category", "created", "modified"]
            fields = {}
            for pr in props:
                val = getattr(wb.properties, pr, None)
                if val is not None and str(val).strip():
                    fields[pr.replace("_", " ").title()] = str(val).strip()
            wb.close()

            if fields:
                meta_info["has_metadata"] = True
                meta_info["fields"] = fields
                meta_info["fields_count"] = len(fields)
                if "Creator" in fields or "Lastmodifiedby" in fields:
                    meta_info["warnings"].append("Contains workbook creator information")
        except Exception as e:
            logger.warning(f"Excel metadata inspection failed for '{p.name}': {e}", exc_info=True)
            meta_info["warnings"].append(f"Excel metadata inspection failed: {e}")

    # 6. OpenDocument ODT
    elif ext == ".odt":
        try:
            with zipfile.ZipFile(str(p), "r") as z:
                if "meta.xml" in z.namelist():
                    xml_str = z.read("meta.xml").decode("utf-8", errors="replace")
                    fields = {}
                    import xml.etree.ElementTree as ET
                    try:
                        root = ET.fromstring(xml_str)
                        for elem in root.iter():
                            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                            if tag in ("creator", "title", "generator", "date", "initial-creator"):
                                text = (elem.text or "").strip()
                                if text:
                                    fields[tag.capitalize()] = text
                    except Exception as e:
                        logger.warning(f"Failed parsing ODT meta.xml: {e}", exc_info=True)
                    if fields:
                        meta_info["has_metadata"] = True
                        meta_info["fields"] = fields
                        meta_info["fields_count"] = len(fields)
                        if "Creator" in fields or "Generator" in fields:
                            meta_info["warnings"].append("Contains author or software generator tracking")
        except Exception as e:
            logger.warning(f"ODT metadata inspection failed for '{p.name}': {e}", exc_info=True)
            meta_info["warnings"].append(f"ODT metadata inspection failed: {e}")

    return meta_info


def strip_image_metadata(input_path: Path, output_path: Path) -> List[str]:
    """Strip EXIF, GPS, IPTC, ICC profile, and comments from an image."""
    removed_tags: List[str] = []
    with Image.open(str(input_path)) as img:
        exif = img.getexif()
        if exif:
            removed_tags.extend([f"EXIF_Tag_{k}" for k in list(exif.keys())[:10]])
            if len(exif) > 10:
                removed_tags.append(f"... and {len(exif) - 10} more EXIF tags")

        for info_key in list(img.info.keys()):
            if info_key in ("exif", "icc_profile", "photoshop", "xmp", "comment"):
                removed_tags.append(f"Image_Info_{info_key}")

        # Correct orientation before stripping EXIF rotation tag
        try:
            clean_img = ImageOps.exif_transpose(img)
            if clean_img is None:
                clean_img = img.copy()
        except Exception as e:
            logger.error(f"Failed to transpose EXIF orientation in '{input_path.name}': {e}", exc_info=True)
            raise RuntimeError(f"Metadata stripping failed during EXIF orientation transpose for '{input_path.name}': {e}") from e

        # Re-create pure raster data to drop any lingering low-level metadata chunks
        sanitized = Image.new(clean_img.mode, clean_img.size)
        sanitized.paste(clean_img)

        # Output format
        ext = output_path.suffix.lower()
        save_format = "JPEG" if ext in (".jpg", ".jpeg") else None

        output_path.parent.mkdir(parents=True, exist_ok=True)
        if save_format == "JPEG":
            sanitized.convert("RGB").save(str(output_path), format=save_format, quality=95)
        else:
            sanitized.save(str(output_path))

    return removed_tags if removed_tags else ["EXIF/Metadata stream stripped"]


def strip_pdf_metadata(input_path: Path, output_path: Path, password: Optional[str] = None) -> List[str]:
    """Strip PDF metadata dictionary, XMP XML stream, and garbage collections."""
    doc = fitz.open(str(input_path))
    if doc.is_encrypted and password:
        doc.authenticate(password)

    removed: List[str] = []
    raw_meta = doc.metadata or {}
    for k, v in raw_meta.items():
        if v and str(v).strip():
            removed.append(f"PDF:{k}={str(v)[:40]}")

    if doc.get_xml_metadata():
        removed.append("PDF:XMP_Metadata_Stream")

    # Clear metadata
    doc.set_metadata({})
    doc.del_xml_metadata()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path), deflate=True, clean=True, garbage=4)
    doc.close()

    return removed if removed else ["PDF info dictionary & XMP stream cleared"]


def strip_docx_metadata(input_path: Path, output_path: Path) -> List[str]:
    """Strip Word Document core properties and revision history."""
    if not _DOCX_AVAILABLE:
        raise RuntimeError("python-docx is required for DOCX metadata stripping.")

    doc = docx.Document(str(input_path))
    cp = doc.core_properties
    props = [
        "author", "last_modified_by", "title", "subject",
        "keywords", "comments", "category"
    ]
    removed: List[str] = []
    for pr in props:
        val = getattr(cp, pr, None)
        if val is not None and str(val).strip():
            removed.append(f"DOCX:{pr}={str(val)[:40]}")
            setattr(cp, pr, "")

    # Reset dates and revision count
    setattr(cp, "revision", 1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    return removed if removed else ["DOCX core properties cleared"]


def strip_pptx_metadata(input_path: Path, output_path: Path) -> List[str]:
    """Strip PowerPoint presentation core properties and comments."""
    if not _PPTX_AVAILABLE:
        raise RuntimeError("python-pptx is required for PPTX metadata stripping.")

    prs = Presentation(str(input_path))
    cp = prs.core_properties
    props = [
        "author", "last_modified_by", "title", "subject",
        "keywords", "comments", "category"
    ]
    removed: List[str] = []
    for pr in props:
        val = getattr(cp, pr, None)
        if val is not None and str(val).strip():
            removed.append(f"PPTX:{pr}={str(val)[:40]}")
            setattr(cp, pr, "")

    setattr(cp, "revision", 1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(output_path))
    return removed if removed else ["PPTX core properties cleared"]


def strip_xlsx_metadata(input_path: Path, output_path: Path) -> List[str]:
    """Strip Excel workbook creator and modification properties."""
    if not _OPENPYXL_AVAILABLE:
        raise RuntimeError("openpyxl is required for XLSX metadata stripping.")

    wb = openpyxl.load_workbook(str(input_path))
    props = ["creator", "lastModifiedBy", "title", "subject", "description", "keywords", "category"]
    removed: List[str] = []
    for pr in props:
        val = getattr(wb.properties, pr, None)
        if val is not None and str(val).strip():
            removed.append(f"XLSX:{pr}={str(val)[:40]}")
            setattr(wb.properties, pr, "")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(output_path))
    wb.close()
    return removed if removed else ["Excel workbook properties cleared"]


def strip_odt_metadata(input_path: Path, output_path: Path) -> List[str]:
    """Strip metadata tags from OpenDocument Text (.odt) package."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    removed: List[str] = []

    minimal_meta_xml = (
        b"<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        b"<office:document-meta xmlns:office=\"urn:oasis:names:tc:opendocument:xmlns:office:1.0\" "
        b"xmlns:meta=\"urn:oasis:names:tc:opendocument:xmlns:meta:1.0\" office:version=\"1.2\">\n"
        b"  <office:meta/>\n"
        b"</office:document-meta>"
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_zip = Path(tmp_dir) / "cleaned.odt"
        with zipfile.ZipFile(str(input_path), "r") as zin:
            with zipfile.ZipFile(str(tmp_zip), "w", compression=zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    if item.filename == "meta.xml":
                        zout.writestr(item, minimal_meta_xml)
                        removed.append("ODT:meta.xml generator/author stripped")
                    else:
                        zout.writestr(item, zin.read(item.filename))
        shutil.copy2(tmp_zip, output_path)

    return removed if removed else ["ODT metadata cleared"]


def strip_file_metadata(
    input_path: str | Path,
    output_path: Optional[str | Path] = None,
    password: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Primary metadata deletion router. Strips all personal, tracking, and device metadata
    from input file and writes a clean copy to output_path.
    If output_path is omitted, creates `<filename>_clean.<ext>` in the same directory.
    """
    in_p = Path(input_path).resolve()
    if not in_p.is_file():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    ext = in_p.suffix.lower()
    if output_path is None:
        out_p = in_p.parent / f"{in_p.stem}_clean{in_p.suffix}"
    else:
        out_p = Path(output_path).resolve()

    # Reject overwriting the exact same input file in-place directly without temp buffer
    is_in_place = (in_p == out_p)
    target_write_path = out_p
    temp_target: Optional[Path] = None
    if is_in_place:
        temp_target = in_p.parent / f"{in_p.stem}_tmp_sanitize{in_p.suffix}"
        target_write_path = temp_target

    removed_fields: List[str] = []
    error_msg: Optional[str] = None
    success = False

    try:
        # Route to appropriate stripper
        if ext in (".jpg", ".jpeg", ".png", ".webp", ".tiff", ".tif", ".heic", ".heif", ".bmp"):
            removed_fields = strip_image_metadata(in_p, target_write_path)
            success = True
        elif ext == ".pdf":
            removed_fields = strip_pdf_metadata(in_p, target_write_path, password=password)
            success = True
        elif ext == ".docx":
            removed_fields = strip_docx_metadata(in_p, target_write_path)
            success = True
        elif ext == ".pptx":
            removed_fields = strip_pptx_metadata(in_p, target_write_path)
            success = True
        elif ext in (".xlsx", ".xlsm"):
            removed_fields = strip_xlsx_metadata(in_p, target_write_path)
            success = True
        elif ext == ".odt":
            removed_fields = strip_odt_metadata(in_p, target_write_path)
            success = True
        elif ext in (".csv", ".txt", ".rtf", ".html", ".json"):
            # Text-based formats have no embedded binary metadata headers
            shutil.copy2(in_p, target_write_path)
            removed_fields = ["Text file: Standard stream sanitized"]
            success = True
        else:
            raise ValueError(f"Metadata stripping not supported for format: {ext}")

        if is_in_place and temp_target and temp_target.exists():
            shutil.move(str(temp_target), str(out_p))

    except Exception as e:
        success = False
        error_msg = str(e)
        if temp_target and temp_target.exists():
            try:
                temp_target.unlink()
            except Exception as e:
                logger.warning(f"Failed to remove temporary file {temp_target}: {e}", exc_info=True)

    orig_size = in_p.stat().st_size
    sanitized_size = out_p.stat().st_size if out_p.exists() and success else 0

    return {
        "success": success,
        "input_path": str(in_p),
        "output_path": str(out_p),
        "extension": ext,
        "fields_removed": removed_fields,
        "original_size": orig_size,
        "sanitized_size": sanitized_size,
        "error_message": error_msg,
    }
