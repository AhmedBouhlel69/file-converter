"""
Local PDF & Document Tools for Universal File Converter.
100% offline, local operations using PyMuPDF (fitz) and Pillow:
- Merge (PDFs and images into a single PDF)
- Split (pages, ranges, every N pages)
- Organize Pages (reorder, rotate, delete, duplicate)
- Compress (reduce file size via image resampling and stream deflation)
- Rotate (rotate pages)
"""

from __future__ import annotations

import io
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Union

import fitz  # PyMuPDF
from PIL import Image

logger = logging.getLogger(__name__)


def parse_page_range_str(range_str: str, max_pages: int) -> List[int]:
    """
    Parse a 1-indexed page range string (e.g. '1, 3, 5-8', '2-end')
    into a sorted list of 0-indexed page indices.

    Validation rules:
    - Empty string or whitespace-only -> ValueError("Empty page range")
    - Trailing/leading commas or ',,' -> ValueError
    - Non-numeric tokens (e.g. '1-abc', 'p1-p3') -> ValueError
    - Non-ASCII digits (e.g. Arabic/Devanagari numerals) -> ValueError
    - 0 or negative numbers (e.g. '0-5', '-3') -> ValueError (1-indexed)
    - Ranges where start > end (e.g. '5-3') -> ValueError
    - Ranges where end > max_pages -> ValueError (do not clamp)
    - Overlapping ranges (e.g. '1-3, 2-5') -> ValueError
    - Whitespace around hyphens/commas is permitted (e.g. '1 - 3 , 5') -> valid
    """
    if range_str is None:
        raise ValueError("Empty page range")

    raw = range_str.strip()
    if not raw:
        raise ValueError("Empty page range")

    if raw.startswith(",") or raw.endswith(","):
        raise ValueError(f"Invalid page range syntax: leading or trailing comma in '{range_str}'")

    raw_tokens = raw.split(",")
    for tok in raw_tokens:
        if not tok.strip():
            raise ValueError(f"Invalid page range syntax: empty segment or consecutive commas in '{range_str}'")

    def _parse_int_token(token_str: str) -> int:
        s = token_str.strip()
        if not s:
            raise ValueError("Empty page number token")
        if not s.isascii() or not s.isdigit():
            raise ValueError(f"Invalid page number '{s}': must be ASCII digits")
        val = int(s)
        if val <= 0:
            raise ValueError(f"Page number {val} is invalid: must be >= 1 (1-indexed)")
        return val

    result_pages: List[int] = []
    seen_pages: Set[int] = set()

    for token in raw_tokens:
        tok = token.strip()
        if "-" in tok:
            hyphen_parts = tok.split("-")
            if len(hyphen_parts) != 2:
                raise ValueError(f"Invalid range token '{tok}': must contain exactly one hyphen")
            start_str = hyphen_parts[0].strip()
            end_str = hyphen_parts[1].strip()

            if not start_str:
                raise ValueError(f"Invalid range token '{tok}': missing start page")
            if not end_str:
                raise ValueError(f"Invalid range token '{tok}': missing end page")

            start = _parse_int_token(start_str)
            if end_str.lower() in ("end", "last", "max"):
                end = max_pages
            else:
                end = _parse_int_token(end_str)

            if start > end:
                raise ValueError(f"Invalid range '{tok}': start page {start} > end page {end}")

            if start > max_pages:
                raise ValueError(f"Start page {start} exceeds total pages ({max_pages})")
            if end > max_pages:
                raise ValueError(f"End page {end} exceeds total pages ({max_pages})")

            for p in range(start, end + 1):
                idx = p - 1
                if idx in seen_pages:
                    raise ValueError(f"Overlapping page ranges: page {p} appears multiple times")
                seen_pages.add(idx)
                result_pages.append(idx)
        else:
            val = _parse_int_token(tok)
            if val > max_pages:
                raise ValueError(f"Page {val} exceeds total pages ({max_pages})")
            idx = val - 1
            if idx in seen_pages:
                raise ValueError(f"Overlapping page ranges: page {val} appears multiple times")
            seen_pages.add(idx)
            result_pages.append(idx)

    return sorted(result_pages)


def merge_pdfs(
    file_paths: Sequence[Union[str, Path]],
    output_path: Union[str, Path],
    bookmarks: bool = True,
) -> str:
    """
    Combine multiple files (PDFs and Images) into a single PDF document.
    100% local with PyMuPDF.
    """
    if not file_paths:
        raise ValueError("No files provided for merging.")

    allowed_exts = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif", ".gif"}
    image_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif", ".gif"}

    # Item 4: Upfront format validation before creating any files or directories
    resolved_paths: List[Path] = []
    for path in file_paths:
        p = Path(path).resolve()
        if not p.is_file():
            raise FileNotFoundError(f"Input file not found for merge: {p}")
        if p.stat().st_size == 0:
            raise ValueError(f"Input file '{p.name}' is empty (0 bytes).")
        ext = p.suffix.lower()
        if ext not in allowed_exts:
            raise ValueError(f"Unsupported file format for merge: {p.name}")
        resolved_paths.append(p)

    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)
    temp_out = out_p.with_name(f".tmp_merge_{os.getpid()}_{time.time_ns()}_{out_p.name}")

    merged_doc = fitz.open()
    toc: List[List[Any]] = []
    current_page = 0
    expected_total_pages = 0

    try:
        for p in resolved_paths:
            ext = p.suffix.lower()

            if ext == ".pdf":
                # Validate PDF header signature
                try:
                    with open(p, "rb") as f:
                        header = f.read(1024)
                    if b"%PDF-" not in header:
                        raise ValueError(f"Input file '{p.name}' is not a valid PDF (missing %PDF- header).")
                except OSError as e:
                    raise ValueError(f"Failed to read PDF file '{p.name}': {e}") from e

                # Item 5 / 5b: Handle corrupt, repaired, or encrypted PDFs explicitly
                try:
                    src = fitz.open(str(p))
                except Exception as e:
                    raise ValueError(f"Corrupted or unreadable PDF '{p.name}': {e}") from e

                try:
                    if getattr(src, "is_repaired", False):
                        raise ValueError(f"Input PDF '{p}' is damaged/truncated (repaired by parser, cannot safely merge)")

                    if src.is_encrypted:
                        # Attempt empty string authentication
                        if not src.authenticate(""):
                            raise ValueError(f"'{p.name}' is password-protected and could not be merged")

                    src_count = len(src)
                    if src_count == 0:
                        raise ValueError(f"Input PDF '{p.name}' contains no pages.")
                    merged_doc.insert_pdf(src)
                    expected_total_pages += src_count
                    if bookmarks:
                        toc.append([1, p.stem, current_page + 1])
                    current_page += src_count
                finally:
                    src.close()

            elif ext in image_exts:
                try:
                    with Image.open(str(p)) as im:
                        img_w, img_h = im.size
                    margin = 20
                    pw = float(img_w + 2 * margin)
                    ph = float(img_h + 2 * margin)

                    page = merged_doc.new_page(width=pw, height=ph)
                    rect = fitz.Rect(margin, margin, margin + img_w, margin + img_h)
                    page.insert_image(rect, filename=str(p))

                    expected_total_pages += 1
                    if bookmarks:
                        toc.append([1, p.stem, current_page + 1])
                    current_page += 1
                except Exception as e:
                    logger.warning(f"Failed to embed image '{p.name}' in merged PDF: {e}", exc_info=True)
                    continue

        if len(merged_doc) == 0:
            raise ValueError("Could not merge: all input files were invalid or empty.")

        if bookmarks and toc:
            try:
                merged_doc.set_toc(toc)
            except Exception as e:
                logger.warning(f"Failed to set TOC in merged PDF '{out_p.name}': {e}", exc_info=True)

        # 5b.3: Verify output page count equals sum of input page counts
        if len(merged_doc) != expected_total_pages:
            raise ValueError(
                f"Page count mismatch during merge: expected {expected_total_pages}, got {len(merged_doc)}"
            )

        # 5b.4: Save to atomic temp file and replace to ensure pre-existing output is never corrupted
        merged_doc.save(str(temp_out), garbage=4, deflate=True)
        merged_doc.close()
        os.replace(str(temp_out), str(out_p))

    except Exception:
        if temp_out.exists():
            try:
                temp_out.unlink()
            except Exception as unlink_err:
                logger.warning(f"Failed to clean up temp file '{temp_out}': {unlink_err}", exc_info=True)
        raise
    finally:
        if not merged_doc.is_closed:
            merged_doc.close()

    return str(out_p)


def split_pdf(
    pdf_path: Union[str, Path],
    output_dir: Union[str, Path],
    mode: str = "ranges",
    ranges: Optional[str] = None,
    n: int = 1,
) -> List[str]:
    """
    Split a PDF into multiple documents.
    mode:
      - 'all_single': splits every page into an individual file
      - 'every_n': splits every N pages
      - 'ranges': splits by comma-separated ranges e.g. '1-2, 3-5'
    """
    src_p = Path(pdf_path).resolve()
    if not src_p.is_file():
        raise FileNotFoundError(f"Input file not found for split: {src_p}")
    if src_p.stat().st_size == 0:
        raise ValueError(f"Input PDF '{src_p.name}' is empty (0 bytes).")

    # Header validation
    try:
        with open(src_p, "rb") as f:
            header = f.read(1024)
        if b"%PDF-" not in header:
            raise ValueError(f"Input file '{src_p.name}' is not a valid PDF (missing %PDF- header).")
    except OSError as e:
        raise ValueError(f"Failed to read PDF file '{src_p.name}': {e}") from e

    doc = fitz.open(str(src_p))
    try:
        if getattr(doc, "is_repaired", False):
            raise ValueError(f"Input PDF '{src_p}' is damaged/truncated (repaired by parser, cannot safely split)")

        if doc.is_encrypted:
            if not doc.authenticate(""):
                raise ValueError(f"'{src_p.name}' is password-protected and could not be split")

        total_pages = len(doc)
        if total_pages == 0:
            raise ValueError("Cannot split empty PDF document.")

        # Upfront validation of split ranges and plan creation
        split_plan: List[Tuple[str, List[int]]] = []

        if mode == "all_single" or (mode == "every_n" and n == 1):
            for i in range(total_pages):
                out_name = f"{src_p.stem}_page_{i + 1}.pdf"
                split_plan.append((out_name, [i]))

        elif mode == "every_n":
            if n < 1:
                raise ValueError(f"Split parameter n must be >= 1, got {n}")
            part = 1
            for start in range(0, total_pages, n):
                end = min(total_pages, start + n)
                out_name = f"{src_p.stem}_part_{part}.pdf"
                split_plan.append((out_name, list(range(start, end))))
                part += 1

        else:  # 'ranges'
            if not ranges or not ranges.strip():
                raise ValueError("Empty page range")
            # Enforce validation of full range string upfront (rejects empty, bad syntax, overlap, out of bounds)
            _ = parse_page_range_str(ranges, total_pages)
            chunks = [r.strip() for r in ranges.split(",") if r.strip()]
            for idx, r_str in enumerate(chunks, start=1):
                indices = parse_page_range_str(r_str, total_pages)
                out_name = f"{src_p.stem}_part_{idx}.pdf"
                split_plan.append((out_name, indices))

        # Upfront validation passed! Now create files.
        out_d = Path(output_dir).resolve()
        out_d.mkdir(parents=True, exist_ok=True)
        created_files: List[Path] = []

        try:
            for out_name, indices in split_plan:
                out_file = out_d / out_name
                new_doc = fitz.open()
                for page_idx in indices:
                    new_doc.insert_pdf(doc, from_page=page_idx, to_page=page_idx)
                new_doc.save(str(out_file), garbage=4, deflate=True)
                new_doc.close()
                created_files.append(out_file)
        except Exception:
            # Midway failure cleanup
            for cf in created_files:
                if cf.exists():
                    try:
                        cf.unlink()
                    except Exception as unlink_err:
                        logger.warning(f"Could not remove temporary file {cf}: {unlink_err}")
            raise

        return [str(f) for f in created_files]

    finally:
        doc.close()


def organize_pages(
    pdf_path: Union[str, Path],
    output_path: Union[str, Path],
    page_order: Sequence[int],
    rotations: Optional[Dict[int, int]] = None,
) -> str:
    """
    Reorder, duplicate, rotate, and delete pages in a PDF.
    page_order: list of 0-indexed page numbers in desired sequence.
    rotations: dict mapping target sequence index to rotation angle (90, 180, 270).

    Sort order policy:
    Hierarchy fidelity beats page monotonicity — an editorial section stays under its chapter
    even if reordering placed the chapter after the section in the final document.
    """
    src_p = Path(pdf_path).resolve()
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(src_p))
    total_pages = len(doc)
    if total_pages == 0:
        doc.close()
        raise ValueError("Document has no pages.")

    if not page_order:
        doc.close()
        raise ValueError("page_order cannot be empty.")

    for pos, p_idx in enumerate(page_order):
        if not isinstance(p_idx, int) or p_idx < 0 or p_idx >= total_pages:
            doc.close()
            raise ValueError(
                f"Invalid page index {p_idx} at position {pos}: "
                f"document has {total_pages} page(s), valid 0-indexed range is 0 to {total_pages - 1}."
            )

    # Extract bookmarks/TOC before reorganizing pages
    src_toc = doc.get_toc(simple=False)

    # Build old-page-index -> new-page-index mapping
    # Policy: If a page is duplicated (appears more than once in page_order),
    # TOC entries pointing to it are mapped to its first occurrence in the reorganized document.
    # This avoids duplicate bookmarks and maintains intuitive forward navigation.
    # Pages absent from page_order are deleted.
    old_to_new: Dict[int, int] = {}
    for new_idx, old_idx in enumerate(page_order):
        if 0 <= old_idx < total_pages and old_idx not in old_to_new:
            old_to_new[old_idx] = new_idx

    remapped_toc: List[List[Any]] = []
    if src_toc:
        class _TocNode:
            def __init__(self, level: int, title: str, page: int, dest: Optional[Dict[str, Any]] = None):
                self.level = level
                self.title = title
                self.page = page
                self.dest = dest
                self.children: List[_TocNode] = []

        # 1. Parse flat PyMuPDF TOC list into a true tree structure to make parent-child relationships explicit
        root = _TocNode(0, "root", 0)
        stack = [root]
        for item in src_toc:
            lvl, title, p_1indexed = item[0], item[1], item[2]
            dest = dict(item[3]) if len(item) > 3 and isinstance(item[3], dict) else None
            node = _TocNode(lvl, title, p_1indexed, dest)
            while stack[-1].level >= lvl:
                stack.pop()
            stack[-1].children.append(node)
            stack.append(node)

        # 2. Prune deleted pages and remap surviving nodes
        # Policy: If a parent node's page was deleted but its children's pages survive,
        # orphaned children are promoted to the parent's level (attached to the grandparent).
        # This ensures surviving document sections remain navigable rather than being lost.
        def _prune_and_remap(parent: _TocNode) -> None:
            surviving: List[_TocNode] = []
            for child in parent.children:
                if child.page <= 0:
                    logger.warning(
                        f"TOC entry '{child.title}' dropped during reorganization: "
                        f"unresolved or non-page destination (page={child.page})"
                    )
                    _prune_and_remap(child)
                    surviving.extend(child.children)
                    continue

                old_p0 = child.page - 1
                if old_p0 in old_to_new:
                    new_p0 = old_to_new[old_p0]
                    child.page = new_p0 + 1
                    if child.dest and "page" in child.dest:
                        child.dest["page"] = new_p0
                    _prune_and_remap(child)
                    surviving.append(child)
                else:
                    logger.warning(
                        f"TOC entry '{child.title}' dropped during reorganization: "
                        f"target page {child.page} was deleted"
                    )
                    _prune_and_remap(child)
                    # Promote surviving children of deleted parent
                    surviving.extend(child.children)
            # Sibling ordering: sort siblings at this level by their new page numbers
            surviving.sort(key=lambda c: c.page)
            parent.children = surviving

        _prune_and_remap(root)

        # 3. Flatten the tree back to PyMuPDF format in parent-then-children order
        def _flatten_tree(parent: _TocNode, current_level: int) -> None:
            for child in parent.children:
                entry: List[Any] = [current_level, child.title, child.page]
                if child.dest:
                    entry.append(child.dest)
                remapped_toc.append(entry)
                _flatten_tree(child, current_level + 1)

        _flatten_tree(root, 1)

    new_doc = fitz.open()
    for target_idx, page_idx in enumerate(page_order):
        if 0 <= page_idx < total_pages:
            new_doc.insert_pdf(doc, from_page=page_idx, to_page=page_idx)
            if rotations and target_idx in rotations:
                angle = rotations[target_idx]
                curr_page = new_doc[target_idx]
                curr_page.set_rotation((curr_page.rotation + angle) % 360)

    if len(new_doc) == 0:
        new_doc.close()
        doc.close()
        raise ValueError("No valid pages in reordered sequence.")

    if remapped_toc:
        try:
            new_doc.set_toc(remapped_toc)
        except Exception as e:
            logger.warning(f"Failed to set remapped TOC in reorganized PDF '{out_p.name}': {e}", exc_info=True)

    new_doc.save(str(out_p), garbage=4, deflate=True)
    new_doc.close()
    doc.close()
    return str(out_p)


def rotate_pdf(
    pdf_path: Union[str, Path],
    output_path: Union[str, Path],
    angle: int = 90,
    page_target: str = "all",
    custom_pages: Optional[Union[List[int], str]] = None,
) -> str:
    """Rotate pages in a PDF document by 90, 180, or 270 degrees."""
    src_p = Path(pdf_path).resolve()
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(src_p))
    total_pages = len(doc)
    if total_pages == 0:
        doc.close()
        raise ValueError("Document has no pages.")

    if page_target == "all":
        target_indices = set(range(total_pages))
    elif page_target == "odd":
        target_indices = {i for i in range(total_pages) if (i + 1) % 2 != 0}
    elif page_target == "even":
        target_indices = {i for i in range(total_pages) if (i + 1) % 2 == 0}
    else:  # custom
        if isinstance(custom_pages, str):
            target_indices = set(parse_page_range_str(custom_pages, total_pages))
        elif custom_pages:
            target_indices = {p - 1 for p in custom_pages if 1 <= p <= total_pages}
        else:
            target_indices = set(range(total_pages))

    for idx in target_indices:
        page = doc[idx]
        page.set_rotation((page.rotation + angle) % 360)

    doc.save(str(out_p), garbage=4, deflate=True)
    doc.close()
    return str(out_p)


def compress_pdf(
    pdf_path: Union[str, Path],
    output_path: Union[str, Path],
    level: str = "medium",
) -> Dict[str, Any]:
    """
    Compress PDF file size with stream deflation, vector cleaning, and aggressive image optimization.
    level:
      - 'low' / 'lossless' / 'fast': lossless compression, stream deflation, garbage collection, vector cleaning.
      - 'medium' / 'balanced' / 'default': resample images > 1200px, JPEG quality 65.
      - 'high' / 'max' / 'maximum': resample images > 800px, JPEG quality 40, transparency stripping.

    Item 7 Guarantee:
    If compressed_size >= input_size, the larger compressed file is discarded,
    and the original file is copied via shutil.copy2 with path_taken='fallback-copy'.
    """
    src_p = Path(pdf_path).resolve()
    if not src_p.is_file():
        raise FileNotFoundError(f"Input file not found for compression: {src_p}")
    orig_size = src_p.stat().st_size
    if orig_size == 0:
        raise ValueError(f"Input PDF '{src_p.name}' is empty (0 bytes).")

    try:
        with open(src_p, "rb") as f:
            header = f.read(1024)
        if b"%PDF-" not in header:
            raise ValueError(f"Input file '{src_p.name}' is not a valid PDF (missing %PDF- header).")
    except OSError as e:
        raise ValueError(f"Failed to read PDF file '{src_p.name}': {e}") from e

    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)
    temp_out = out_p.with_name(f".tmp_comp_{os.getpid()}_{time.time_ns()}_{out_p.name}")

    doc = fitz.open(str(src_p))
    try:
        if getattr(doc, "is_repaired", False):
            raise ValueError(f"Input PDF '{src_p}' is damaged/truncated (repaired by parser, cannot safely compress)")

        if doc.is_encrypted:
            if not doc.authenticate(""):
                raise ValueError(f"'{src_p.name}' is password-protected and could not be compressed")

        orig_page_count = len(doc)
        if orig_page_count == 0:
            raise ValueError("Cannot compress empty PDF document.")

        lvl = level.lower().strip()
        is_high = lvl in ("high", "max", "maximum")
        is_medium = lvl in ("medium", "balanced", "default")

        # Pre-process: Clean contents of all pages
        for page in doc:
            try:
                page.clean_contents()
            except Exception as e:
                logger.warning(f"Failed to clean contents on page {page.number + 1}: {e}", exc_info=True)

        if is_medium or is_high:
            max_dim = 800 if is_high else 1200
            quality = 40 if is_high else 65
            processed_xrefs = set()

            for page in doc:
                for img_info in page.get_images():
                    xref = img_info[0]
                    if xref in processed_xrefs:
                        continue
                    processed_xrefs.add(xref)

                    base_image = doc.extract_image(xref)
                    if not base_image or "image" not in base_image:
                        continue
                    try:
                        img_bytes = base_image["image"]
                        orig_len = len(img_bytes)

                        pil_img = Image.open(io.BytesIO(img_bytes))
                        w, h = pil_img.size

                        if w > max_dim or h > max_dim or pil_img.format != "JPEG" or quality < 75:
                            if w > max_dim or h > max_dim:
                                pil_img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

                            if pil_img.mode in ("RGBA", "LA") or (pil_img.mode == "P" and "transparency" in pil_img.info):
                                bg = Image.new("RGB", pil_img.size, (255, 255, 255))
                                if pil_img.mode == "P":
                                    pil_img = pil_img.convert("RGBA")
                                mask = pil_img.split()[3] if len(pil_img.split()) == 4 else None
                                if mask:
                                    bg.paste(pil_img, mask=mask)
                                else:
                                    bg.paste(pil_img)
                                pil_img = bg
                            elif pil_img.mode not in ("L", "RGB"):
                                pil_img = pil_img.convert("RGB")

                            buf = io.BytesIO()
                            pil_img.save(buf, format="JPEG", quality=quality, optimize=True)
                            new_bytes = buf.getvalue()

                            if len(new_bytes) < orig_len:
                                page.replace_image(xref, stream=new_bytes)
                    except Exception as e:
                        logger.warning(f"Failed compressing image xref {xref}: {e}", exc_info=True)
                        continue

        if hasattr(doc, "subset_fonts"):
            try:
                doc.subset_fonts()
            except Exception as e:
                logger.warning(f"Failed subsetting fonts in PDF '{out_p.name}': {e}", exc_info=True)

        doc.save(
            str(temp_out),
            garbage=4,
            deflate=True,
            clean=True,
            deflate_images=True,
            deflate_fonts=True,
        )
        doc.close()

        comp_size = temp_out.stat().st_size

        # Item 7.1: If compressed_size >= orig_size, never return the larger file
        if comp_size >= orig_size:
            if temp_out.exists():
                temp_out.unlink()
            shutil.copy2(src_p, out_p)
            result = {
                "original_size": orig_size,
                "compressed_size": orig_size,
                "saved_bytes": 0,
                "savings_percent": 0.0,
                "path_taken": "fallback-copy",
                "message": "no size reduction achieved, original kept",
            }
        else:
            os.replace(str(temp_out), str(out_p))
            saved = orig_size - comp_size
            pct = (saved / orig_size) * 100.0 if orig_size > 0 else 0.0
            result = {
                "original_size": orig_size,
                "compressed_size": comp_size,
                "saved_bytes": saved,
                "savings_percent": round(pct, 2),
                "path_taken": "compressed",
                "message": f"compressed ({pct:.1f}% reduction)",
            }

        # Item 7.4: Assert page count of output equals page count of input
        check_doc = fitz.open(str(out_p))
        out_pages = len(check_doc)
        check_doc.close()
        if out_pages != orig_page_count:
            raise ValueError(
                f"Compression altered page count: expected {orig_page_count}, got {out_pages}"
            )

        return result

    except Exception:
        if temp_out.exists():
            try:
                temp_out.unlink()
            except Exception as unlink_err:
                logger.warning(f"Could not remove temporary file {temp_out}: {unlink_err}")
        raise
    finally:
        if not doc.is_closed:
            doc.close()
        if temp_out.exists():
            try:
                temp_out.unlink()
            except Exception as unlink_err:
                logger.warning(f"Could not remove temporary file {temp_out}: {unlink_err}")


def remove_pages(
    pdf_path: Union[str, Path],
    output_path: Union[str, Path],
    pages_to_remove: Union[List[int], str],
) -> str:
    """Remove specified pages (1-indexed input) permanently from a PDF."""
    src_p = Path(pdf_path).resolve()
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(src_p))
    total_pages = len(doc)
    if total_pages == 0:
        doc.close()
        raise ValueError("Document has no pages.")

    if isinstance(pages_to_remove, str):
        remove_indices = set(parse_page_range_str(pages_to_remove, total_pages))
    else:
        remove_indices = {p - 1 for p in pages_to_remove if 1 <= p <= total_pages}

    if len(remove_indices) >= total_pages:
        doc.close()
        raise ValueError("Cannot remove all pages from document.")

    for idx in sorted(remove_indices, reverse=True):
        doc.delete_page(idx)

    doc.save(str(out_p), garbage=4, deflate=True)
    doc.close()
    return str(out_p)


def extract_pages(
    pdf_path: Union[str, Path],
    output_path: Union[str, Path],
    pages_to_extract: Union[List[int], str],
) -> str:
    """Extract specified pages (1-indexed input) into a new PDF."""
    src_p = Path(pdf_path).resolve()
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(src_p))
    total_pages = len(doc)
    if total_pages == 0:
        doc.close()
        raise ValueError("Document has no pages.")

    if isinstance(pages_to_extract, str):
        indices = parse_page_range_str(pages_to_extract, total_pages)
    else:
        indices = [p - 1 for p in pages_to_extract if 1 <= p <= total_pages]

    if not indices:
        doc.close()
        raise ValueError("No valid pages selected for extraction.")

    new_doc = fitz.open()
    for idx in indices:
        new_doc.insert_pdf(doc, from_page=idx, to_page=idx)

    new_doc.save(str(out_p), garbage=4, deflate=True)
    new_doc.close()
    doc.close()
    return str(out_p)
