"""
Tests for local PDF tools (Merge, Split, Organize, Compress, Rotate).
Verifies 100% local operation without external dependencies or fluff.
"""

from pathlib import Path
import fitz  # PyMuPDF
import pytest
from PIL import Image

from image_converter.core.pdf_tools import (
    compress_pdf,
    extract_pages,
    merge_pdfs,
    organize_pages,
    parse_page_range_str,
    remove_pages,
    rotate_pdf,
    split_pdf,
)


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    """Create a multi-page PDF for testing."""
    pdf_path = tmp_path / "sample.pdf"
    doc = fitz.open()
    for i in range(5):
        page = doc.new_page(width=300, height=400)
        page.insert_text((50, 50), f"Page {i + 1} Content", fontsize=16)
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest.fixture
def sample_image(tmp_path: Path) -> Path:
    """Create a sample PNG image."""
    img_path = tmp_path / "test_img.png"
    im = Image.new("RGB", (200, 200), color=(79, 70, 229))
    im.save(str(img_path))
    return img_path


def test_parse_page_range_str():
    assert parse_page_range_str("1, 3, 5", 5) == [0, 2, 4]
    assert parse_page_range_str("1-3", 5) == [0, 1, 2]
    assert parse_page_range_str("2-end", 5) == [1, 2, 3, 4]
    assert parse_page_range_str("", 5) == [0, 1, 2, 3, 4]


def test_merge_pdfs(sample_pdf: Path, sample_image: Path, tmp_path: Path):
    out_pdf = tmp_path / "merged.pdf"
    res = merge_pdfs([sample_pdf, sample_image], out_pdf)
    assert Path(res).exists()
    doc = fitz.open(res)
    assert len(doc) == 6  # 5 from sample_pdf + 1 from sample_image
    doc.close()


def test_split_pdf_all_single(sample_pdf: Path, tmp_path: Path):
    out_dir = tmp_path / "split_out"
    files = split_pdf(sample_pdf, out_dir, mode="all_single")
    assert len(files) == 5
    for f in files:
        assert Path(f).exists()
        doc = fitz.open(f)
        assert len(doc) == 1
        doc.close()


def test_split_pdf_every_n(sample_pdf: Path, tmp_path: Path):
    out_dir = tmp_path / "split_every_2"
    files = split_pdf(sample_pdf, out_dir, mode="every_n", n=2)
    assert len(files) == 3  # pages 1-2, 3-4, 5
    for f in files:
        assert Path(f).exists()


def test_split_pdf_ranges(sample_pdf: Path, tmp_path: Path):
    out_dir = tmp_path / "split_ranges"
    files = split_pdf(sample_pdf, out_dir, mode="ranges", ranges="1-2, 4-5")
    assert len(files) == 2
    doc1 = fitz.open(files[0])
    assert len(doc1) == 2
    doc1.close()


def test_organize_pages(sample_pdf: Path, tmp_path: Path):
    out_pdf = tmp_path / "reordered.pdf"
    # Reverse order and rotate page 0
    organize_pages(sample_pdf, out_pdf, page_order=[4, 3, 2, 1, 0], rotations={0: 90})
    assert out_pdf.exists()
    doc = fitz.open(str(out_pdf))
    assert len(doc) == 5
    assert doc[0].rotation == 90
    assert "Page 5" in doc[0].get_text()
    assert "Page 1" in doc[4].get_text()
    doc.close()


def test_rotate_pdf(sample_pdf: Path, tmp_path: Path):
    out_pdf = tmp_path / "rotated.pdf"
    rotate_pdf(sample_pdf, out_pdf, angle=90, page_target="all")
    assert out_pdf.exists()
    doc = fitz.open(str(out_pdf))
    for page in doc:
        assert page.rotation == 90
    doc.close()


def test_compress_pdf(sample_pdf: Path, tmp_path: Path):
    out_pdf = tmp_path / "compressed.pdf"
    stats = compress_pdf(sample_pdf, out_pdf, level="medium")
    assert out_pdf.exists()
    assert "original_size" in stats
    assert "compressed_size" in stats
    assert "savings_percent" in stats
    assert stats["compressed_size"] > 0


def test_remove_pages(sample_pdf: Path, tmp_path: Path):
    out_pdf = tmp_path / "removed.pdf"
    remove_pages(sample_pdf, out_pdf, pages_to_remove="2, 4")
    assert out_pdf.exists()
    doc = fitz.open(str(out_pdf))
    assert len(doc) == 3
    doc.close()


def test_extract_pages(sample_pdf: Path, tmp_path: Path):
    out_pdf = tmp_path / "extracted.pdf"
    extract_pages(sample_pdf, out_pdf, pages_to_extract="1, 3, 5")
    assert out_pdf.exists()
    doc = fitz.open(str(out_pdf))
    assert len(doc) == 3
    doc.close()
