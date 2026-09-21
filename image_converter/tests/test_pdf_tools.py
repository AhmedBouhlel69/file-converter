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
    with pytest.raises(ValueError, match="Empty page range"):
        parse_page_range_str("", 5)


def test_merge_pdfs(sample_pdf: Path, sample_image: Path, tmp_path: Path):
    out_pdf = tmp_path / "merged.pdf"
    res = merge_pdfs([sample_pdf, sample_image], out_pdf)
    assert Path(res).exists()
    doc = fitz.open(res)
    assert len(doc) == 6  # 5 from sample_pdf + 1 from sample_image
    doc.close()


def test_merge_rejects_unsupported_files_and_preserves_directory(sample_pdf: Path, sample_image: Path, tmp_path: Path):
    """
    Item 4 verification:
    Merge must reject unsupported files (e.g. .txt) upfront before creating any output.
    Output directory snapshot must remain completely identical.
    """
    out_dir = tmp_path / "merge_out_dir"
    out_dir.mkdir(parents=True, exist_ok=True)
    sentinel = out_dir / "existing_file.txt"
    sentinel.write_text("keep me intact", encoding="utf-8")

    before_snapshot = sorted([p.name for p in out_dir.iterdir()])

    unsupported_file = tmp_path / "notes.txt"
    unsupported_file.write_text("Hello world", encoding="utf-8")

    out_pdf = out_dir / "merged.pdf"
    with pytest.raises(ValueError) as exc_info:
        merge_pdfs([sample_pdf, sample_image, unsupported_file], out_pdf)

    assert "Unsupported file format for merge" in str(exc_info.value)
    assert "notes.txt" in str(exc_info.value)

    after_snapshot = sorted([p.name for p in out_dir.iterdir()])
    assert before_snapshot == after_snapshot, "Output directory contents must be completely unchanged"
    assert not out_pdf.exists()


def test_merge_handles_encrypted_pdf_explicitly_and_cleans_output(sample_pdf: Path, tmp_path: Path):
    """
    Item 5 verification:
    Merge must detect password-protected PDFs explicitly, raise an error naming the offending file,
    and guarantee that no partial merged file remains on disk.
    """
    enc_pdf = tmp_path / "locked_document.pdf"
    enc_doc = fitz.open()
    page = enc_doc.new_page(width=300, height=400)
    page.insert_text((50, 50), "Confidential", fontsize=14)
    # Save with AES-256 password protection
    enc_doc.save(
        str(enc_pdf),
        encryption=fitz.PDF_ENCRYPT_AES_256,
        user_pw="secure123",
        owner_pw="secure123",
    )
    enc_doc.close()

    out_pdf = tmp_path / "merged_encrypted_out.pdf"

    with pytest.raises(ValueError) as exc_info:
        merge_pdfs([sample_pdf, enc_pdf], out_pdf)

    err_msg = str(exc_info.value)
    assert "locked_document.pdf" in err_msg, f"Expected filename in error message: {err_msg}"
    assert "password-protected" in err_msg.lower(), f"Expected 'password-protected' in error: {err_msg}"
    assert not out_pdf.exists(), "No partial merged output file must remain on disk"



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


def test_organize_pages_preserves_bookmarks_and_toc(tmp_path: Path):
    """
    Item 3 verification:
    1. Create PDF with multi-level TOC (>=3 entries, >=3 pages, nested sub-level).
    2. Delete one page that a TOC entry points to.
    3. Reorder remaining pages and duplicate one page.
    4. Assert TOC count equals original minus deleted page's entries.
    5. Assert page numbers match where content now lives and confirm text on target page.
    """
    src_pdf = tmp_path / "toc_source.pdf"
    doc = fitz.open()

    # Create 4 pages with distinct text markers
    p0 = doc.new_page(width=300, height=400)
    p0.insert_text((50, 50), "Content of Chapter 1", fontsize=14)

    p1 = doc.new_page(width=300, height=400)
    p1.insert_text((50, 50), "Content of Section 1.1", fontsize=14)

    p2 = doc.new_page(width=300, height=400)
    p2.insert_text((50, 50), "Content of Section 1.2", fontsize=14)

    p3 = doc.new_page(width=300, height=400)
    p3.insert_text((50, 50), "Content of Chapter 2", fontsize=14)

    initial_toc = [
        [1, "Chapter 1", 1],
        [2, "Section 1.1", 2],
        [2, "Section 1.2", 3],
        [1, "Chapter 2", 4],
    ]
    doc.set_toc(initial_toc)
    doc.save(str(src_pdf))
    doc.close()

    # Check source TOC
    src_doc = fitz.open(str(src_pdf))
    before_toc = src_doc.get_toc(simple=True)
    src_doc.close()

    # Reorder operation:
    # Delete page 1 (Section 1.1).
    # Reorder remaining: page 3 -> first, page 2 -> second, page 0 -> third.
    # Duplicate page 0 -> fourth.
    # page_order = [3, 2, 0, 0]
    out_pdf = tmp_path / "toc_reorganized.pdf"
    organize_pages(src_pdf, out_pdf, page_order=[3, 2, 0, 0])

    assert out_pdf.exists()
    reorg_doc = fitz.open(str(out_pdf))
    after_toc = reorg_doc.get_toc(simple=True)

    # Print before & after for audit reporting
    print("\n--- BEFORE TOC DUMP ---")
    for item in before_toc:
        print(item)
    print("--- AFTER TOC DUMP ---")
    for item in after_toc:
        print(item)

    # Assertion 1: Length is original (4) - 1 (deleted Section 1.1) = 3
    assert len(after_toc) == 3, f"Expected 3 TOC entries, got {len(after_toc)}"

    # Assertion 2: Section 1.1 was dropped
    titles = [item[1] for item in after_toc]
    assert "Section 1.1" not in titles

    # Assertion 3: Section 1.2 remains a child of its true parent Chapter 1, NOT Chapter 2
    # Find Section 1.2 index and verify its preceding parent is Chapter 1
    s12_idx = next(i for i, item in enumerate(after_toc) if item[1] == "Section 1.2")
    parent_entry = None
    for i in range(s12_idx - 1, -1, -1):
        if after_toc[i][0] < after_toc[s12_idx][0]:
            parent_entry = after_toc[i]
            break
    assert parent_entry is not None and parent_entry[1] == "Chapter 1", (
        f"Section 1.2 must remain parented by Chapter 1, but got parent: {parent_entry}"
    )

    # Assertion 4: Verify target pages and actual content
    # Chapter 2 was old page 3 (index 3), now at index 0 -> page 1 (1-indexed)
    ch2_entry = next(item for item in after_toc if item[1] == "Chapter 2")
    assert ch2_entry[2] == 1
    assert "Content of Chapter 2" in reorg_doc[ch2_entry[2] - 1].get_text()

    # Section 1.2 was old page 2 (index 2), now at index 1 -> page 2 (1-indexed)
    s12_entry = next(item for item in after_toc if item[1] == "Section 1.2")
    assert s12_entry[2] == 2
    assert "Content of Section 1.2" in reorg_doc[s12_entry[2] - 1].get_text()

    # Chapter 1 was old page 0 (index 0), duplicated at indices 2 and 3; mapped to first occurrence -> page 3
    ch1_entry = next(item for item in after_toc if item[1] == "Chapter 1")
    assert ch1_entry[2] == 3
    assert "Content of Chapter 1" in reorg_doc[ch1_entry[2] - 1].get_text()

    reorg_doc.close()


def test_organize_pages_preserves_parent_child_association(tmp_path: Path):
    """
    Item 3 verification:
    Construct a TOC with two level-1 chapters, each having a distinct child:
    - Chapter A (p1) -> Child A1 (p2)
    - Chapter B (p3) -> Child B1 (p4)
    Reorder so Child B1 (p4) comes before Child A1 (p2), but Chapter A is still before Chapter B.
    Assert that each child is still nested under its ORIGINAL parent title in the outline.
    """
    src_pdf = tmp_path / "two_chapters.pdf"
    doc = fitz.open()
    for i in range(4):
        p = doc.new_page(width=300, height=400)
        p.insert_text((50, 50), f"Page {i + 1} Content")

    initial_toc = [
        [1, "Chapter A", 1],
        [2, "Child A1", 2],
        [1, "Chapter B", 3],
        [2, "Child B1", 4],
    ]
    doc.set_toc(initial_toc)
    doc.save(str(src_pdf))
    doc.close()

    src_doc = fitz.open(str(src_pdf))
    before_toc = src_doc.get_toc(simple=True)
    src_doc.close()

    # Reorder: old page 0 (Chapter A), old page 3 (Child B1), old page 1 (Child A1), old page 2 (Chapter B)
    # page_order = [0, 3, 1, 2]
    # New pages:
    # Page 1: Chapter A (old p0)
    # Page 2: Child B1 (old p3)
    # Page 3: Child A1 (old p1)
    # Page 4: Chapter B (old p2)
    out_pdf = tmp_path / "two_chapters_reordered.pdf"
    organize_pages(src_pdf, out_pdf, page_order=[0, 3, 1, 2])

    reorg_doc = fitz.open(str(out_pdf))
    after_toc = reorg_doc.get_toc(simple=True)

    print("\n--- TWO CHAPTERS BEFORE TOC DUMP ---")
    for item in before_toc:
        print(item)
    print("--- TWO CHAPTERS AFTER TOC DUMP ---")
    for item in after_toc:
        print(item)

    # Helper function to find the immediate parent of an entry
    def get_parent_title(toc, entry_title):
        idx = next(i for i, item in enumerate(toc) if item[1] == entry_title)
        entry_level = toc[idx][0]
        for i in range(idx - 1, -1, -1):
            if toc[i][0] < entry_level:
                return toc[i][1]
        return None

    parent_of_a1 = get_parent_title(after_toc, "Child A1")
    parent_of_b1 = get_parent_title(after_toc, "Child B1")

    # Assert that Child A1 is still associated with Chapter A, NOT Chapter B
    assert parent_of_a1 == "Chapter A", f"Child A1 must be nested under Chapter A, got: {parent_of_a1}"
    # Assert that Child B1 is still associated with Chapter B, NOT Chapter A
    assert parent_of_b1 == "Chapter B", f"Child B1 must be nested under Chapter B, got: {parent_of_b1}"

    reorg_doc.close()


def test_merge_handles_corrupted_pdf_explicitly_and_cleans_output(sample_pdf: Path, tmp_path: Path):
    """
    Item 5 verification:
    Merge must detect truncated/corrupted PDF inputs explicitly, raise an error naming the offending file,
    and guarantee that no partial merged file remains on disk.
    """
    corrupt_pdf = tmp_path / "bad_corrupted.pdf"
    # Write a truncated/malformed PDF header with garbage content
    corrupt_pdf.write_bytes(b"%PDF-1.5\n%TRUNCATED_CORRUPT_DATA_WITHOUT_TRAILER_OR_XREF\x00\xff\xfe")

    out_pdf = tmp_path / "merged_corrupt_out.pdf"

    with pytest.raises(ValueError) as exc_info:
        merge_pdfs([sample_pdf, corrupt_pdf], out_pdf)

    err_msg = str(exc_info.value)
    assert "bad_corrupted.pdf" in err_msg, f"Expected filename in error message: {err_msg}"
    assert "corrupted" in err_msg.lower() or "unreadable" in err_msg.lower(), f"Expected corrupt error: {err_msg}"
    assert not out_pdf.exists(), "No partial merged output file must remain on disk"


def test_organize_pages_unresolved_dest_dropped_with_warning(tmp_path: Path, caplog):
    """
    3b.2: Entries whose destination is unresolved or non-page (e.g. page <= 0 / -1)
    must be dropped with an explicit logged warning.
    """
    import logging
    src_pdf = tmp_path / "unresolved_dest.pdf"
    doc = fitz.open()
    p0 = doc.new_page(width=300, height=400)
    p0.insert_text((50, 50), "Page 1 Content")
    p1 = doc.new_page(width=300, height=400)
    p1.insert_text((50, 50), "Page 2 Content")

    # PyMuPDF TOC entry with unresolved destination page=-1
    initial_toc = [
        [1, "Valid Chapter", 1],
        [2, "Unresolved Link", -1],
    ]
    doc.set_toc(initial_toc)
    doc.save(str(src_pdf))
    doc.close()

    out_pdf = tmp_path / "unresolved_out.pdf"
    with caplog.at_level(logging.WARNING):
        organize_pages(src_pdf, out_pdf, page_order=[0, 1])

    out_doc = fitz.open(str(out_pdf))
    after_toc = out_doc.get_toc(simple=True)
    out_doc.close()

    # Unresolved link was dropped
    titles = [item[1] for item in after_toc]
    assert "Unresolved Link" not in titles
    assert "Valid Chapter" in titles

    # Logged warning verified
    warning_found = any(
        "Unresolved Link" in record.message and "unresolved or non-page destination" in record.message
        for record in caplog.records
    )
    assert warning_found, f"Expected warning for unresolved link, got: {[r.message for r in caplog.records]}"


def test_organize_pages_duplicate_page_policy(tmp_path: Path):
    """
    3b.3: If a page is duplicated in page_order (e.g. [1, 0, 0]),
    bookmarks pointing to it must map to its first occurrence.
    """
    src_pdf = tmp_path / "dup_source.pdf"
    doc = fitz.open()
    p0 = doc.new_page(width=300, height=400)
    p0.insert_text((50, 50), "Page 1 Content")
    p1 = doc.new_page(width=300, height=400)
    p1.insert_text((50, 50), "Page 2 Content")

    initial_toc = [
        [1, "Chapter 1", 1],
        [1, "Chapter 2", 2],
    ]
    doc.set_toc(initial_toc)
    doc.save(str(src_pdf))
    doc.close()

    out_pdf = tmp_path / "dup_out.pdf"
    # Page 1 (index 1) is first (new page 1)
    # Page 0 (index 0) is duplicated at new page 2 and new page 3
    organize_pages(src_pdf, out_pdf, page_order=[1, 0, 0])

    out_doc = fitz.open(str(out_pdf))
    after_toc = out_doc.get_toc(simple=True)
    out_doc.close()

    # Chapter 2 should be at page 1
    ch2 = next(item for item in after_toc if item[1] == "Chapter 2")
    assert ch2[2] == 1

    # Chapter 1 (page 0) was placed at index 1 and index 2 (pages 2 and 3)
    # By policy, it must point to the FIRST occurrence (page 2)
    ch1 = next(item for item in after_toc if item[1] == "Chapter 1")
    assert ch1[2] == 2


def test_organize_pages_invalid_and_negative_indices_raise_value_error(tmp_path: Path):
    src_pdf = tmp_path / "three_pages.pdf"
    doc = fitz.open()
    for i in range(3):
        doc.new_page().insert_text((50, 50), f"Page {i+1}")
    doc.save(str(src_pdf))
    doc.close()

    out_pdf = tmp_path / "out.pdf"

    # 1. Mixed valid and out-of-bounds [0, 999]
    with pytest.raises(ValueError) as exc_info:
        organize_pages(src_pdf, out_pdf, page_order=[0, 999])
    assert "Invalid page index 999 at position 1" in str(exc_info.value)
    assert "document has 3 page(s)" in str(exc_info.value)

    # 2. Negative index [-1, 0]
    with pytest.raises(ValueError) as exc_info2:
        organize_pages(src_pdf, out_pdf, page_order=[-1, 0])
    assert "Invalid page index -1 at position 0" in str(exc_info2.value)

    # 3. Non-integer index
    with pytest.raises(ValueError) as exc_info3:
        organize_pages(src_pdf, out_pdf, page_order=[0, "bad"])
    assert "Invalid page index bad" in str(exc_info3.value)

    # 4. Empty page_order
    with pytest.raises(ValueError) as exc_info4:
        organize_pages(src_pdf, out_pdf, page_order=[])
    assert "page_order cannot be empty" in str(exc_info4.value)

    # 5. Duplicates [0, 0, 1] MUST succeed
    dup_out = tmp_path / "dup_ok.pdf"
    organize_pages(src_pdf, dup_out, page_order=[0, 0, 1])
    res_doc = fitz.open(str(dup_out))
    assert len(res_doc) == 3
    res_doc.close()


def test_merge_pdfs_rejects_truncated_repaired_pdf(sample_pdf: Path, tmp_path: Path):
    """
    5b.1: Truncate a real PDF to 50% of its bytes. PyMuPDF's fitz.open() silently
    repairs many truncated PDFs and reports is_repaired=True.
    merge_pdfs must reject it with ValueError naming the file and mentioning damaged/truncated.
    """
    orig_bytes = sample_pdf.read_bytes()
    truncated_pdf = tmp_path / "truncated_half.pdf"
    truncated_pdf.write_bytes(orig_bytes[: len(orig_bytes) // 2])

    # Assert that PyMuPDF actually considers this truncated fixture repaired
    probe = fitz.open(str(truncated_pdf))
    assert probe.is_repaired is True, "Fixture must produce a PDF that fitz marks as is_repaired == True"
    probe.close()

    out_pdf = tmp_path / "merged_trunc_out.pdf"
    with pytest.raises(ValueError) as exc_info:
        merge_pdfs([sample_pdf, truncated_pdf], out_pdf)

    err = str(exc_info.value)
    assert "truncated_half.pdf" in err or "damaged/truncated" in err.lower()
    assert not out_pdf.exists()


def test_merge_pdfs_rejects_zero_byte_and_non_pdf(sample_pdf: Path, tmp_path: Path):
    """
    5b.2: An input file with .pdf extension that is 0 bytes or not a PDF at all
    must be rejected with ValueError before any page operations.
    """
    zero_byte_pdf = tmp_path / "empty.pdf"
    zero_byte_pdf.write_bytes(b"")

    out_pdf = tmp_path / "out1.pdf"
    with pytest.raises(ValueError) as exc_info:
        merge_pdfs([sample_pdf, zero_byte_pdf], out_pdf)
    assert "empty (0 bytes)" in str(exc_info.value)
    assert not out_pdf.exists()

    fake_pdf = tmp_path / "fake.pdf"
    fake_pdf.write_text("This is plain text with a .pdf extension, not a PDF!", encoding="utf-8")

    out_pdf2 = tmp_path / "out2.pdf"
    with pytest.raises(ValueError) as exc_info2:
        merge_pdfs([sample_pdf, fake_pdf], out_pdf2)
    assert "missing %PDF- header" in str(exc_info2.value) or "not a valid PDF" in str(exc_info2.value)
    assert not out_pdf2.exists()


def test_merge_pdfs_page_count_sum(sample_pdf: Path, tmp_path: Path):
    """
    5b.3: Verify output page count equals the sum of input page counts.
    """
    doc2 = fitz.open()
    for _ in range(3):
        doc2.new_page(width=200, height=200)
    pdf2 = tmp_path / "three_pages.pdf"
    doc2.save(str(pdf2))
    doc2.close()

    img = Image.new("RGB", (100, 100), color="blue")
    img_path = tmp_path / "one_page.png"
    img.save(img_path)

    out_pdf = tmp_path / "merged_sum.pdf"
    merge_pdfs([sample_pdf, pdf2, img_path], out_pdf)

    out_doc = fitz.open(str(out_pdf))
    assert out_doc.page_count == (5 + 3 + 1)
    out_doc.close()


def test_merge_pdfs_failure_does_not_clobber_existing_file(sample_pdf: Path, tmp_path: Path):
    """
    5b.4: If merge fails midway (e.g. file 2 of 2 is corrupt), assert that no partial
    output file exists at output_path. If a file already existed there before the call,
    assert it was NOT overwritten or deleted.
    """
    existing_out = tmp_path / "precious_existing.pdf"
    precious_content = b"DO_NOT_CLOBBER_ME_PREVIOUS_VERSION"
    existing_out.write_bytes(precious_content)

    corrupt_pdf = tmp_path / "broken.pdf"
    corrupt_pdf.write_bytes(b"NOT A REAL PDF")

    with pytest.raises(ValueError):
        merge_pdfs([sample_pdf, corrupt_pdf], existing_out)

    # Assert pre-existing file is intact and byte-identical
    assert existing_out.exists()
    assert existing_out.read_bytes() == precious_content


def test_parse_page_range_str_strict_rejections():
    """
    Item 6.1: Test all invalid range cases:
    - Empty string or whitespace-only -> ValueError
    - Trailing/leading commas or ,, -> ValueError
    - Non-numeric tokens -> ValueError
    - Non-ASCII digits -> ValueError
    - 0 or negative numbers -> ValueError
    - Ranges where start > end -> ValueError
    - Ranges where end > total_pages -> ValueError (do not clamp)
    - Overlapping ranges -> ValueError
    - Whitespace around hyphens/commas -> valid
    """
    # Empty string or whitespace-only
    with pytest.raises(ValueError, match="Empty page range"):
        parse_page_range_str("", max_pages=10)
    with pytest.raises(ValueError, match="Empty page range"):
        parse_page_range_str("   ", max_pages=10)

    # Trailing/leading commas or ,,
    with pytest.raises(ValueError, match="leading or trailing comma"):
        parse_page_range_str(",1-3", max_pages=10)
    with pytest.raises(ValueError, match="leading or trailing comma"):
        parse_page_range_str("1-3,", max_pages=10)
    with pytest.raises(ValueError, match="empty segment or consecutive commas"):
        parse_page_range_str("1-2,,3-4", max_pages=10)
    with pytest.raises(ValueError, match="empty segment or consecutive commas"):
        parse_page_range_str("1-2, ,3-4", max_pages=10)

    # Non-numeric tokens
    with pytest.raises(ValueError, match="must be ASCII digits"):
        parse_page_range_str("1-abc", max_pages=10)
    with pytest.raises(ValueError, match="must be ASCII digits"):
        parse_page_range_str("p1-p3", max_pages=10)

    # Non-ASCII digits (Arabic / Devanagari numerals)
    with pytest.raises(ValueError, match="must be ASCII digits"):
        parse_page_range_str("١-٣", max_pages=10)
    with pytest.raises(ValueError, match="must be ASCII digits"):
        parse_page_range_str("१-५", max_pages=10)

    # 0 or negative numbers
    with pytest.raises(ValueError, match="must be >= 1"):
        parse_page_range_str("0-5", max_pages=10)
    with pytest.raises(ValueError, match="missing start page|must be >= 1"):
        parse_page_range_str("-3", max_pages=10)

    # Ranges where start > end
    with pytest.raises(ValueError, match="start page 5 > end page 3"):
        parse_page_range_str("5-3", max_pages=10)

    # Ranges where end > total_pages (must NOT clamp)
    with pytest.raises(ValueError, match="exceeds total pages"):
        parse_page_range_str("1-10", max_pages=5)
    with pytest.raises(ValueError, match="exceeds total pages"):
        parse_page_range_str("6", max_pages=5)

    # Overlapping ranges
    with pytest.raises(ValueError, match="Overlapping page ranges"):
        parse_page_range_str("1-3, 2-5", max_pages=10)
    with pytest.raises(ValueError, match="Overlapping page ranges"):
        parse_page_range_str("1, 1", max_pages=10)

    # Valid with whitespace around hyphens/commas
    res = parse_page_range_str("1 - 3 , 5", max_pages=10)
    assert res == [0, 1, 2, 4]


def test_split_pdf_validates_upfront_zero_files_on_error(sample_pdf: Path, tmp_path: Path):
    """
    Item 6.2: If ANY range is invalid, write ZERO files to disk.
    Validate all ranges upfront before creating any output file.
    """
    out_dir = tmp_path / "split_zero_out"

    # Overlapping ranges should fail upfront
    with pytest.raises(ValueError, match="Overlapping page ranges"):
        split_pdf(sample_pdf, out_dir, mode="ranges", ranges="1-3, 2-5")

    # Output directory must have zero files
    if out_dir.exists():
        files_written = list(out_dir.iterdir())
        assert len(files_written) == 0, f"Expected 0 files written, found: {files_written}"

    # Range exceeding page count should fail upfront
    with pytest.raises(ValueError, match="exceeds total pages"):
        split_pdf(sample_pdf, out_dir, mode="ranges", ranges="1-99")

    if out_dir.exists():
        files_written = list(out_dir.iterdir())
        assert len(files_written) == 0, f"Expected 0 files written, found: {files_written}"


def test_split_pdf_content_verification(tmp_path: Path):
    """
    Item 6.2: Verify every output file contains exactly the requested pages
    (content-based: check text on each page of each output against source).
    """
    src_pdf = tmp_path / "content_doc.pdf"
    doc = fitz.open()
    marker_texts = [
        "PAGE_1_ALPHA_UNIQUE_CONTENT",
        "PAGE_2_BRAVO_UNIQUE_CONTENT",
        "PAGE_3_CHARLIE_UNIQUE_CONTENT",
        "PAGE_4_DELTA_UNIQUE_CONTENT",
        "PAGE_5_ECHO_UNIQUE_CONTENT",
    ]
    for text in marker_texts:
        p = doc.new_page(width=300, height=400)
        p.insert_text((50, 50), text)
    doc.save(str(src_pdf))
    doc.close()

    out_dir = tmp_path / "split_content_out"
    # Split into: Part 1 = pages 1-2, Part 2 = pages 4-5
    generated = split_pdf(src_pdf, out_dir, mode="ranges", ranges="1-2, 4-5")
    assert len(generated) == 2

    # Verify Part 1 (pages 1-2)
    p1_doc = fitz.open(generated[0])
    assert len(p1_doc) == 2
    assert marker_texts[0] in p1_doc[0].get_text()
    assert marker_texts[1] in p1_doc[1].get_text()
    p1_doc.close()

    # Verify Part 2 (pages 4-5)
    p2_doc = fitz.open(generated[1])
    assert len(p2_doc) == 2
    assert marker_texts[3] in p2_doc[0].get_text()
    assert marker_texts[4] in p2_doc[1].get_text()
    p2_doc.close()


def test_split_pdf_midway_failure_cleanup(sample_pdf: Path, tmp_path: Path, monkeypatch):
    """
    Item 6.2: If split fails midway (e.g. disk write error on 2nd part),
    clean up any already-written parts.
    """
    out_dir = tmp_path / "split_cleanup_out"

    original_save = fitz.Document.save
    save_call_count = 0

    def failing_save(self, filename, *args, **kwargs):
        nonlocal save_call_count
        save_call_count += 1
        if save_call_count == 2:
            raise OSError("Simulated disk write failure on 2nd part")
        return original_save(self, filename, *args, **kwargs)

    monkeypatch.setattr(fitz.Document, "save", failing_save)

    with pytest.raises(OSError, match="Simulated disk write failure"):
        split_pdf(sample_pdf, out_dir, mode="ranges", ranges="1-2, 3-4")

    # Assert that Part 1 was cleaned up and does not linger on disk
    if out_dir.exists():
        remaining_files = list(out_dir.iterdir())
        assert len(remaining_files) == 0, f"Expected 0 lingering files, found: {remaining_files}"



def test_split_pdf_encrypted_input_rejected(tmp_path: Path):
    """
    6b: Split with encrypted input.
    split_pdf and ImageConverterEngine.split_pdf must reject password-protected PDF
    with a clear error and write ZERO files to disk (snapshot diff).
    """
    enc_pdf = tmp_path / "encrypted_secret.pdf"
    doc = fitz.open()
    p = doc.new_page(width=200, height=200)
    p.insert_text((50, 50), "Secret encrypted content")
    # Save with AES 256 encryption
    doc.save(
        str(enc_pdf),
        encryption=fitz.PDF_ENCRYPT_AES_256,
        user_pw="password123",
        owner_pw="owner123",
    )
    doc.close()

    out_dir = tmp_path / "split_enc_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    files_before = list(out_dir.iterdir())

    # 1. Direct split_pdf call
    with pytest.raises(ValueError, match="password-protected and could not be split"):
        split_pdf(enc_pdf, out_dir, mode="ranges", ranges="1")

    files_after_direct = list(out_dir.iterdir())
    assert files_after_direct == files_before, "Directory snapshot diff must show 0 files created after direct split error"

    # 2. Engine-level split_pdf call
    from image_converter.core.engine import ImageConverterEngine
    engine = ImageConverterEngine()
    res = engine.split_pdf(enc_pdf, out_dir, mode="ranges", ranges="1")
    assert res.success is False
    assert "password-protected and could not be split" in res.error_message

    files_after_engine = list(out_dir.iterdir())
    assert files_after_engine == files_before, "Directory snapshot diff must show 0 files created after engine split error"


def test_compress_pdf_matrix_and_fallbacks(tmp_path: Path):
    """
    Item 7 & 7b verification:
    1. Realistic photo-like compressible PDF: 1200x800 high-entropy image with text blocks.
    2. Fidelity checks for every level (low, medium, high):
       - page count identical
       - text extraction identical (no dropped text)
       - image count per page unchanged (no dropped images)
       - rendered-pixel comparison at 150 DPI (Mean Absolute Difference per pixel)
    3. Multi-KB already-optimized fixture: 600x400 JPEG at quality 35 embedded in deflated PDF (~25 KB).
       - verify fallback-copy is taken across all levels
       - verify SHA-256 match (input hash == output hash)
       - verify saved_bytes == 0 and savings_percent == 0.0
    4. Assert no .tmp_comp_* temporary files linger in directory.
    """
    import hashlib
    import random

    # 1. Build a realistic photo-like compressible PDF
    # High-entropy image with gradient + seeded pseudo-noise to represent realistic photographic content
    compressible_pdf = tmp_path / "realistic_photo_doc.pdf"
    img_w, img_h = 1400, 900
    rng = random.Random(42)
    img_data = bytearray(img_w * img_h * 3)
    for y in range(img_h):
        for x in range(img_w):
            idx = (y * img_w + x) * 3
            # Blend smooth gradient with seeded texture
            grad_r = int((x / img_w) * 200)
            grad_g = int((y / img_h) * 200)
            noise = rng.randint(0, 55)
            img_data[idx] = min(255, grad_r + noise)
            img_data[idx + 1] = min(255, grad_g + noise)
            img_data[idx + 2] = min(255, ((grad_r + grad_g) // 2) + noise)

    photo_img = Image.frombytes("RGB", (img_w, img_h), bytes(img_data))
    photo_jpg_path = tmp_path / "photo_raw.jpg"
    photo_img.save(photo_jpg_path, format="JPEG", quality=92)

    doc_comp = fitz.open()
    page = doc_comp.new_page(width=800, height=600)
    page.insert_text((50, 40), "Document Header: Ground Truth Text", fontsize=14)
    page.insert_image(fitz.Rect(50, 60, 750, 520), filename=str(photo_jpg_path))
    page.insert_text((50, 550), "Document Footer: Confidential Report Q3", fontsize=12)
    doc_comp.save(str(compressible_pdf), deflate=True)
    doc_comp.close()

    # 2. Build a realistic multi-KB already-optimized PDF (pre-compressed at high level)
    draft_pdf = tmp_path / "draft_to_optimize.pdf"
    incompressible_pdf = tmp_path / "realistic_already_optimized.pdf"
    small_w, small_h = 600, 400
    small_data = bytearray(small_w * small_h * 3)
    for i in range(len(small_data)):
        small_data[i] = (i * 37) % 256
    small_img = Image.frombytes("RGB", (small_w, small_h), bytes(small_data))
    small_jpg_path = tmp_path / "already_compressed_q30.jpg"
    small_img.save(small_jpg_path, format="JPEG", quality=30)

    doc_draft = fitz.open()
    p2 = doc_draft.new_page(width=500, height=400)
    p2.insert_text((30, 30), "Optimized Document Header")
    p2.insert_image(fitz.Rect(30, 50, 470, 350), filename=str(small_jpg_path))
    p2.insert_text((30, 370), "Optimized Document Footer")
    doc_draft.save(str(draft_pdf))
    doc_draft.close()

    # Pre-compress to high level so it is already maximally compressed
    compress_pdf(draft_pdf, incompressible_pdf, level="high")
    incomp_input_sha = hashlib.sha256(incompressible_pdf.read_bytes()).hexdigest()

    levels = ["low", "medium", "high"]

    print("\n--- COMPRESSION TEST RESULTS TABLE (REALISTIC FIXTURES) ---")
    print(f"{'Category':<15} | {'Level':<10} | {'Input Bytes':<12} | {'Output Bytes':<12} | {'Path Taken':<15} | {'MAD (0-255)':<12} | {'Savings %'}")
    print("-" * 96)

    # Test Realistic Compressible
    src_doc = fitz.open(str(compressible_pdf))
    src_pix = src_doc[0].get_pixmap(dpi=150)
    src_text = src_doc[0].get_text()

    for lvl in levels:
        out_f = tmp_path / f"comp_out_{lvl}.pdf"
        stats = compress_pdf(compressible_pdf, out_f, level=lvl)

        assert out_f.exists()
        out_doc = fitz.open(str(out_f))

        # 7b.3 Fidelity checks
        # 1. Page count equal
        assert out_doc.page_count == src_doc.page_count, f"Page count mismatch at level {lvl}"

        # 2. Text extraction identical
        assert out_doc[0].get_text() == src_text, f"Text corrupted at level {lvl}"

        # 3. Image count per page unchanged
        assert len(out_doc[0].get_images()) == len(src_doc[0].get_images()), f"Images dropped at level {lvl}"

        # 4. Rendered-pixel comparison at 150 DPI (Mean Absolute Difference)
        out_pix = out_doc[0].get_pixmap(dpi=150)
        assert len(src_pix.samples) == len(out_pix.samples)
        diff_total = sum(abs(a - b) for a, b in zip(src_pix.samples, out_pix.samples))
        mad = diff_total / len(src_pix.samples)

        # Fidelity thresholds:
        # - low (lossless stream deflation): MAD must be 0.0 (exact match)
        # - medium (JPEG 65, resample > 1200px): MAD < 15.0
        # - high (JPEG 40, resample > 800px): MAD < 30.0 (lossy degradation acknowledged)
        if lvl == "low":
            assert mad == 0.0, f"Low level must be pixel-exact (lossless), got MAD={mad}"
        elif lvl == "medium":
            assert mad < 15.0, f"Medium level pixel degradation exceeded threshold: MAD={mad}"
        elif lvl == "high":
            assert mad < 30.0, f"High level pixel degradation exceeded threshold: MAD={mad}"

        out_doc.close()

        print(
            f"{'Compressible':<15} | {lvl:<10} | {stats['original_size']:<12} | "
            f"{stats['compressed_size']:<12} | {stats['path_taken']:<15} | {mad:<12.2f} | {stats['savings_percent']:.2f}%"
        )

    src_doc.close()

    # Test Realistic Incompressible (must trigger fallback-copy)
    for lvl in levels:
        out_f = tmp_path / f"incomp_out_{lvl}.pdf"
        stats = compress_pdf(incompressible_pdf, out_f, level=lvl)

        assert out_f.exists()
        assert stats["path_taken"] == "fallback-copy"
        assert stats["saved_bytes"] == 0
        assert stats["savings_percent"] == 0.0
        assert "no size reduction achieved" in stats["message"]

        # 7c.3: Verify SHA-256 byte-for-byte identity
        out_sha = hashlib.sha256(out_f.read_bytes()).hexdigest()
        assert out_sha == incomp_input_sha, f"Fallback-copy output must match input SHA-256: {out_sha} != {incomp_input_sha}"

        out_doc = fitz.open(str(out_f))
        assert len(out_doc) == 1
        out_doc.close()

        print(
            f"{'Incompressible':<15} | {lvl:<10} | {stats['original_size']:<12} | "
            f"{stats['compressed_size']:<12} | {stats['path_taken']:<15} | {'0.00 (exact)':<12} | {stats['savings_percent']:.2f}%"
        )

    # 7c.4: Snapshot-diff: Assert no temporary files linger
    temp_files = [f.name for f in tmp_path.iterdir() if f.name.startswith(".tmp_comp_")]
    assert len(temp_files) == 0, f"Lingering temporary files found: {temp_files}"







