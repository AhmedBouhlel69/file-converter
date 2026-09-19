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
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Union

import fitz  # PyMuPDF
from PIL import Image


def parse_page_range_str(range_str: str, max_pages: int) -> List[int]:
    """
    Parse a 1-indexed page range string (e.g. '1, 3, 5-8', '2-end')
    into a sorted list of 0-indexed page indices.
    """
    if not range_str or not range_str.strip():
        return list(range(max_pages))

    result: Set[int] = set()
    parts = [p.strip() for p in range_str.split(",") if p.strip()]

    for part in parts:
        if "-" in part:
            sub = part.split("-", 1)
            start_str = sub[0].strip()
            end_str = sub[1].strip()

            start = 1 if not start_str else int(start_str)
            if end_str.lower() in ("end", "last", "max", ""):
                end = max_pages
            else:
                end = int(end_str)

            if start > end:
                start, end = end, start

            for p in range(max(1, start), min(max_pages, end) + 1):
                result.add(p - 1)
        else:
            try:
                val = int(part)
                if 1 <= val <= max_pages:
                    result.add(val - 1)
            except ValueError:
                continue

    return sorted(list(result))


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

    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    merged_doc = fitz.open()
    toc: List[List[Any]] = []
    current_page = 0

    image_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif", ".gif"}

    for path in file_paths:
        p = Path(path).resolve()
        if not p.is_file():
            continue

        ext = p.suffix.lower()

        if ext == ".pdf":
            src = fitz.open(str(p))
            src_count = len(src)
            if src_count > 0:
                merged_doc.insert_pdf(src)
                if bookmarks:
                    toc.append([1, p.stem, current_page + 1])
                current_page += src_count
            src.close()

        elif ext in image_exts:
            try:
                with Image.open(str(p)) as im:
                    img_w, img_h = im.size
                # Use standard A4 or image dimensions
                margin = 20
                pw = float(img_w + 2 * margin)
                ph = float(img_h + 2 * margin)

                page = merged_doc.new_page(width=pw, height=ph)
                rect = fitz.Rect(margin, margin, margin + img_w, margin + img_h)
                page.insert_image(rect, filename=str(p))

                if bookmarks:
                    toc.append([1, p.stem, current_page + 1])
                current_page += 1
            except Exception:
                continue

    if len(merged_doc) == 0:
        merged_doc.close()
        raise ValueError("Could not merge: all input files were invalid or empty.")

    if bookmarks and toc:
        try:
            merged_doc.set_toc(toc)
        except Exception:
            pass

    merged_doc.save(str(out_p), garbage=4, deflate=True)
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
    out_d = Path(output_dir).resolve()
    out_d.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(src_p))
    total_pages = len(doc)
    if total_pages == 0:
        doc.close()
        raise ValueError("Cannot split empty PDF document.")

    generated_files: List[str] = []

    if mode == "all_single" or (mode == "every_n" and n == 1):
        for i in range(total_pages):
            out_file = out_d / f"{src_p.stem}_page_{i + 1}.pdf"
            new_doc = fitz.open()
            new_doc.insert_pdf(doc, from_page=i, to_page=i)
            new_doc.save(str(out_file), garbage=4, deflate=True)
            new_doc.close()
            generated_files.append(str(out_file))

    elif mode == "every_n":
        step = max(1, n)
        part = 1
        for start in range(0, total_pages, step):
            end = min(total_pages - 1, start + step - 1)
            out_file = out_d / f"{src_p.stem}_part_{part}.pdf"
            new_doc = fitz.open()
            new_doc.insert_pdf(doc, from_page=start, to_page=end)
            new_doc.save(str(out_file), garbage=4, deflate=True)
            new_doc.close()
            generated_files.append(str(out_file))
            part += 1

    else:  # 'ranges'
        if not ranges:
            ranges = f"1-{total_pages}"
        range_chunks = [r.strip() for r in ranges.split(",") if r.strip()]
        for idx, r_str in enumerate(range_chunks, start=1):
            indices = parse_page_range_str(r_str, total_pages)
            if not indices:
                continue
            out_file = out_d / f"{src_p.stem}_part_{idx}.pdf"
            new_doc = fitz.open()
            for page_idx in indices:
                new_doc.insert_pdf(doc, from_page=page_idx, to_page=page_idx)
            new_doc.save(str(out_file), garbage=4, deflate=True)
            new_doc.close()
            generated_files.append(str(out_file))

    doc.close()
    return generated_files


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
    """
    src_p = Path(pdf_path).resolve()
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(src_p))
    total_pages = len(doc)
    if total_pages == 0:
        doc.close()
        raise ValueError("Document has no pages.")

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
      - 'low' / 'lossless': lossless compression, stream deflation, garbage collection, vector cleaning.
      - 'medium' / 'balanced': resample images > 1200px, JPEG quality 65.
      - 'high' / 'max': resample images > 800px, JPEG quality 40, transparency stripping.
    Returns:
      dict with original_size, compressed_size, saved_bytes, savings_percent.
    """
    src_p = Path(pdf_path).resolve()
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    orig_size = src_p.stat().st_size
    doc = fitz.open(str(src_p))

    lvl = level.lower()
    
    # Pre-process: Clean contents of all pages
    # This combines text and graphics operations, which can drastically reduce file size
    for page in doc:
        try:
            page.clean_contents()
        except Exception:
            pass

    if lvl in ("medium", "high", "balanced", "max"):
        max_dim = 800 if lvl in ("high", "max") else 1200
        quality = 40 if lvl in ("high", "max") else 65
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
                    
                    # Process if large, or not a JPEG, or we want to reduce JPEG quality
                    if w > max_dim or h > max_dim or pil_img.format != "JPEG" or quality < 75:
                        if w > max_dim or h > max_dim:
                            pil_img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
                            
                        # Handle transparency
                        if pil_img.mode in ('RGBA', 'LA') or (pil_img.mode == 'P' and 'transparency' in pil_img.info):
                            bg = Image.new('RGB', pil_img.size, (255, 255, 255))
                            if pil_img.mode == 'P':
                                pil_img = pil_img.convert('RGBA')
                            mask = pil_img.split()[3] if len(pil_img.split()) == 4 else None
                            if mask:
                                bg.paste(pil_img, mask=mask)
                            else:
                                bg.paste(pil_img)
                            pil_img = bg
                        elif pil_img.mode not in ('L', 'RGB'):
                            pil_img = pil_img.convert('RGB')
                        
                        buf = io.BytesIO()
                        pil_img.save(buf, format="JPEG", quality=quality, optimize=True)
                        new_bytes = buf.getvalue()
                        
                        # ONLY update if the new image is actually smaller!
                        if len(new_bytes) < orig_len:
                            doc.update_stream(xref, new_bytes)
                except Exception:
                    continue
                    
    # Attempt font subsetting (available in newer PyMuPDF versions)
    if hasattr(doc, "subset_fonts"):
        try:
            doc.subset_fonts()
        except Exception:
            pass

    doc.save(
        str(out_p),
        garbage=4,
        deflate=True,
        clean=True,
        deflate_images=True,
        deflate_fonts=True,
    )
    doc.close()

    comp_size = out_p.stat().st_size
    saved = orig_size - comp_size
    pct = (saved / orig_size) * 100.0 if orig_size > 0 else 0.0

    return {
        "original_size": orig_size,
        "compressed_size": comp_size,
        "saved_bytes": saved,
        "savings_percent": max(0.0, pct),
    }


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
