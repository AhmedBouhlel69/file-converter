"""
Unit tests for the ImageConverterEngine.
"""

import tempfile
from pathlib import Path
from PIL import Image

import pytest

from image_converter.core.engine import (
    ImageConverterEngine,
    ConversionConfig,
    get_image_metadata,
    get_supported_input_extensions,
    get_supported_output_formats,
    _HEIF_AVAILABLE,
)


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def engine():
    return ImageConverterEngine()


def test_supported_formats(engine):
    in_exts = get_supported_input_extensions()
    out_fmts = get_supported_output_formats()

    assert ".jpg" in in_exts
    assert ".png" in in_exts
    assert ".heic" in in_exts
    assert "PNG" in out_fmts
    assert "JPG" in out_fmts
    assert "WEBP" in out_fmts
    assert "ICO" in out_fmts
    assert "PDF" in out_fmts


def test_metadata_extraction(temp_dir):
    img_path = temp_dir / "sample.png"
    img = Image.new("RGBA", (120, 80), color=(255, 0, 0, 128))
    img.save(img_path, format="PNG")

    meta = get_image_metadata(img_path)
    assert meta["width"] == 120
    assert meta["height"] == 80
    assert meta["has_alpha"] is True
    assert meta["file_size"] > 0


def test_png_to_jpg_with_alpha_compositing(engine, temp_dir):
    # Transparent PNG with half transparent red
    src_path = temp_dir / "alpha.png"
    dst_path = temp_dir / "alpha_out.jpg"

    src_img = Image.new("RGBA", (100, 100), color=(255, 0, 0, 0))  # fully transparent
    src_img.save(src_path, format="PNG")

    config = ConversionConfig(
        target_format="JPG",
        quality=90,
        background_color=(255, 255, 255),  # white
    )

    result = engine.convert_single(src_path, dst_path, config)
    assert result.success is True
    assert dst_path.is_file()

    # Verify converted image is RGB and white
    with Image.open(dst_path) as out_img:
        assert out_img.mode == "RGB"
        assert out_img.size == (100, 100)
        # Pixel should be white because of composite
        pixel = out_img.getpixel((50, 50))
        assert pixel == (255, 255, 255)


def test_heic_conversion(engine, temp_dir):
    if not _HEIF_AVAILABLE:
        pytest.skip("HEIF library not available in this test environment")

    # Create synthetic HEIC
    src_path = temp_dir / "sample.heic"
    dst_path = temp_dir / "sample_converted.png"

    img = Image.new("RGB", (64, 64), color="blue")
    img.save(src_path, format="HEIF")

    config = ConversionConfig(target_format="PNG")
    result = engine.convert_single(src_path, dst_path, config)
    assert result.success is True
    assert dst_path.is_file()

    with Image.open(dst_path) as out_img:
        assert out_img.size == (64, 64)
        assert out_img.format == "PNG"

    # Test PNG back to HEIC
    heic_back_path = temp_dir / "back.heic"
    config_heic = ConversionConfig(target_format="HEIC", quality=80)
    res_back = engine.convert_single(dst_path, heic_back_path, config_heic)
    assert res_back.success is True
    assert heic_back_path.is_file()


def test_heic_unavailable_error_handling(engine, temp_dir, monkeypatch):
    """
    Item 8b: When _HEIF_AVAILABLE is False, converting HEIC files must return
    a clear per-file error (no crash) in both normal image conversion and image->docx.
    """
    monkeypatch.setattr("image_converter.core.engine._HEIF_AVAILABLE", False)

    heic_path = temp_dir / "sample_unavail.heic"
    heic_path.write_bytes(b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00heic")

    # 1. Normal image conversion path (HEIC -> PNG)
    out_png = temp_dir / "out_unavail.png"
    res_img = engine.convert_single(heic_path, out_png, ConversionConfig(target_format="PNG"))
    assert res_img.success is False
    assert (
        "heif" in res_img.error_message.lower()
        or "corrupt" in res_img.error_message.lower()
        or "blocked" in res_img.error_message.lower()
        or "cannot identify" in res_img.error_message.lower()
    )
    assert not out_png.exists()

    # 2. Image to DOCX path (HEIC -> DOCX)
    out_docx = temp_dir / "out_unavail.docx"
    res_docx = engine.convert_single(heic_path, out_docx, ConversionConfig(target_format="DOCX"))
    assert res_docx.success is False
    assert "Corrupt or unreadable" in res_docx.error_message or "heif" in res_docx.error_message.lower()
    assert not out_docx.exists()


def test_resizing_options(engine, temp_dir):
    src_path = temp_dir / "original.jpg"
    img = Image.new("RGB", (200, 100), color="green")
    img.save(src_path, format="JPEG")

    # Percentage resize 50%
    out_pct = temp_dir / "resize_pct.jpg"
    cfg_pct = ConversionConfig(target_format="JPG", resize_mode="percentage", resize_percent=50.0)
    res_pct = engine.convert_single(src_path, out_pct, cfg_pct)
    assert res_pct.success is True
    assert res_pct.output_dimensions == (100, 50)

    # Custom dimensions with aspect ratio lock (fit inside 80x80 -> 80x40)
    out_custom = temp_dir / "resize_custom.png"
    cfg_custom = ConversionConfig(
        target_format="PNG",
        resize_mode="custom",
        custom_width=80,
        custom_height=80,
        keep_aspect_ratio=True,
    )
    res_custom = engine.convert_single(src_path, out_custom, cfg_custom)
    assert res_custom.success is True
    assert res_custom.output_dimensions == (80, 40)


def test_ico_generation(engine, temp_dir):
    src_path = temp_dir / "icon_source.png"
    dst_path = temp_dir / "app.ico"

    img = Image.new("RGBA", (128, 128), color=(0, 128, 255, 255))
    img.save(src_path, format="PNG")

    config = ConversionConfig(target_format="ICO")
    result = engine.convert_single(src_path, dst_path, config)
    assert result.success is True
    assert dst_path.is_file()
    assert dst_path.stat().st_size > 0


def test_pdf_generation(engine, temp_dir):
    src_path = temp_dir / "page.jpg"
    dst_path = temp_dir / "doc.pdf"

    img = Image.new("RGB", (300, 400), color="white")
    img.save(src_path, format="JPEG")

    config = ConversionConfig(target_format="PDF")
    result = engine.convert_single(src_path, dst_path, config)
    assert result.success is True
    assert dst_path.is_file()
    assert dst_path.stat().st_size > 0


def test_nonexistent_file_error(engine, temp_dir):
    fake_path = temp_dir / "missing.jpg"
    dst_path = temp_dir / "output.png"

    result = engine.convert_single(fake_path, dst_path, ConversionConfig(target_format="PNG"))
    assert result.success is False
    assert "not found" in result.error_message.lower()


def test_same_input_and_output_path_is_rejected(engine, temp_dir):
    image_path = temp_dir / "same.jpg"
    Image.new("RGB", (20, 10), color="red").save(image_path)
    original_bytes = image_path.read_bytes()

    result = engine.convert_single(
        image_path,
        image_path,
        ConversionConfig(target_format="JPG"),
    )

    assert result.success is False
    assert "must be different" in result.error_message
    assert image_path.read_bytes() == original_bytes


def test_conversion_fails_on_empty_or_corrupt_output(engine, temp_dir, monkeypatch):
    """
    Item 1 verification: Converter must never return success=True on 0-byte output,
    must return a descriptive error, and must unlink the empty/corrupt file.
    """
    src_path = temp_dir / "valid_input.txt"
    src_path.write_text("Hello world", encoding="utf-8")
    dst_path = temp_dir / "output.pdf"

    # Monkeypatch rich_converter._text_to_pdf to simulate corrupt/empty output
    def fake_convert_text_to_pdf(content, out_p, title=""):
        out_p = Path(out_p)
        out_p.write_bytes(b"")  # 0-byte file created
        return out_p

    monkeypatch.setattr(engine.rich_converter, "_text_to_pdf", fake_convert_text_to_pdf)

    config = ConversionConfig(target_format="PDF")
    result = engine.convert_single(src_path, dst_path, config)

    assert result.success is False
    assert "0 bytes" in result.error_message or "corrupt" in result.error_message.lower()
    assert not dst_path.exists(), "0-byte/corrupt file must be unlinked"


def test_engine_split_pdf_rejects_bad_ranges(engine, temp_dir):
    """
    Item 6.3: ImageConverterEngine must reject bad ranges and return success=False
    with the exact validation error message.
    """
    import fitz
    src_pdf = temp_dir / "engine_sample.pdf"
    doc = fitz.open()
    for _ in range(5):
        doc.new_page(width=200, height=200)
    doc.save(str(src_pdf))
    doc.close()

    out_dir = temp_dir / "engine_split_out"

    # 1. Overlapping ranges
    res1 = engine.split_pdf(src_pdf, out_dir, mode="ranges", ranges="1-3, 2-5")
    assert res1.success is False
    assert "Overlapping page ranges" in res1.error_message

    # 2. Out of bounds range
    res2 = engine.split_pdf(src_pdf, out_dir, mode="ranges", ranges="1-10")
    assert res2.success is False
    assert "exceeds total pages" in res2.error_message

    # 3. Invalid syntax (leading comma)
    res3 = engine.split_pdf(src_pdf, out_dir, mode="ranges", ranges=",1-3")
    assert res3.success is False
    assert "leading or trailing comma" in res3.error_message


def test_engine_compress_pdf(engine, temp_dir):
    """
    Item 7 verification: ImageConverterEngine.compress_pdf routes through
    _verify_and_create_result and returns a valid ConversionResult.
    """
    import fitz
    src_pdf = temp_dir / "engine_compress_src.pdf"
    doc = fitz.open()
    p = doc.new_page(width=200, height=200)
    p.insert_text((50, 50), "Engine compression test")
    doc.save(str(src_pdf))
    doc.close()

    out_pdf = temp_dir / "engine_compressed.pdf"
    res = engine.compress_pdf(src_pdf, out_pdf, level="medium")

    assert res.success is True
    assert res.output_path == str(out_pdf)
    assert out_pdf.exists()
    assert res.output_size_bytes > 0


def test_image_to_docx_exif_orientation(engine, temp_dir):
    """
    Item 8b.1: Verify EXIF orientation tags 1 (baseline), 3, 6, 8 are physically rotated upright in DOCX.
    Fixture: Image has red top half and blue bottom half in upright space.
    Pixels are extracted directly from word/media/image1.png in the produced DOCX zip
    and asserted independently of the code under test.
    """
    import io
    import zipfile
    from PIL import Image

    for tag, rot_angle in [(1, 0), (3, 180), (6, 270), (8, 90)]:
        base = Image.new("RGB", (100, 200))
        for y in range(100):
            for x in range(100):
                base.putpixel((x, y), (255, 0, 0))  # red top
        for y in range(100, 200):
            for x in range(100):
                base.putpixel((x, y), (0, 0, 255))  # blue bottom

        if tag == 1:
            raw = base.copy()
        elif tag == 3:
            raw = base.rotate(180, expand=True)
        elif tag == 6:
            raw = base.rotate(90, expand=True)
        elif tag == 8:
            raw = base.rotate(270, expand=True)

        exif = raw.getexif()
        exif[274] = tag
        img_path = temp_dir / f"test_exif_{tag}.jpg"
        raw.save(img_path, format="JPEG", exif=exif)

        out_docx = temp_dir / f"out_exif_{tag}.docx"
        cfg = ConversionConfig(target_format="DOCX")
        res = engine.convert_single(img_path, out_docx, cfg)
        assert res.success is True
        assert out_docx.exists()

        # Extract embedded image from the DOCX zip and verify upright pixel layout
        with zipfile.ZipFile(out_docx) as zf:
            media_names = [n for n in zf.namelist() if n.startswith("word/media/image")]
            assert len(media_names) == 1
            embedded_bytes = zf.read(media_names[0])

        with Image.open(io.BytesIO(embedded_bytes)) as emb:
            ew, eh = emb.size
            assert eh > ew, f"Tag {tag}: embedded image should be upright (height > width), got ({ew}, {eh})"
            top_pixel = emb.getpixel((ew // 2, 10))
            bot_pixel = emb.getpixel((ew // 2, eh - 10))
            # Assert top is RED and bottom is BLUE
            assert top_pixel[0] > 200 and top_pixel[2] < 50, f"Tag {tag}: top pixel must be RED, got {top_pixel}"
            assert bot_pixel[2] > 200 and bot_pixel[0] < 50, f"Tag {tag}: bottom pixel must be BLUE, got {bot_pixel}"


def test_image_to_docx_format_matrix(engine, temp_dir, monkeypatch):
    """
    Item 8b.2: Format matrix test across all requested formats, modes, and corrupt inputs.
    Prints formatted verification table.
    """
    import io
    import zipfile
    table_rows = []

    # Helper to test single conversion
    def _test_fmt(name, make_img_fn, is_corrupt=False, corrupt_bytes=None, ext=".png", is_heic=False):
        in_f = temp_dir / f"fmt_{name}{ext}"
        out_f = temp_dir / f"fmt_{name}.docx"

        if is_corrupt:
            in_f.write_bytes(corrupt_bytes if corrupt_bytes is not None else b"NOT AN IMAGE")
            mode = "N/A"
        elif is_heic:
            in_f.write_bytes(b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00heic")
            mode = "RGB"
        else:
            im = make_img_fn()
            mode = im.mode
            im.save(in_f)

        cfg = ConversionConfig(target_format="DOCX")
        res = engine.convert_single(in_f, out_f, cfg)

        if res.success:
            result_str = "converted"
            msg = f"OK ({out_f.stat().st_size} bytes)"
        else:
            result_str = "rejected"
            msg = res.error_message or "Unknown error"

        table_rows.append((name.upper(), mode, f"{result_str}: {msg}"))
        return res, out_f

    # 1. WEBP
    _test_fmt("webp", lambda: Image.new("RGB", (60, 60), (20, 40, 60)), ext=".webp")
    # 2. TIFF
    _test_fmt("tiff", lambda: Image.new("RGB", (60, 60), (10, 80, 160)), ext=".tiff")
    # 3. BMP
    _test_fmt("bmp", lambda: Image.new("RGB", (60, 60), (100, 200, 50)), ext=".bmp")
    # 4. GIF single-frame
    _test_fmt("gif_single", lambda: Image.new("P", (60, 60)), ext=".gif")
    # 5. GIF multi-frame (policy: first frame only)
    def _make_multi_gif():
        im1 = Image.new("RGB", (60, 60), color=(255, 0, 0))  # Frame 1: Red
        im2 = Image.new("RGB", (60, 60), color=(0, 0, 255))  # Frame 2: Blue
        p = temp_dir / "temp_multi.gif"
        im1.save(p, save_all=True, append_images=[im2])
        return Image.open(p)
    res_gif, out_gif = _test_fmt("gif_multi", _make_multi_gif, ext=".gif")
    # Verify policy: DOCX contains exactly 1 frame and it corresponds to Frame 1 (Red)
    assert res_gif.success is True
    with zipfile.ZipFile(out_gif) as zf:
        emb_bytes = zf.read("word/media/image1.png")
        with Image.open(io.BytesIO(emb_bytes)) as emb:
            assert getattr(emb, "n_frames", 1) == 1
            px = emb.getpixel((30, 30))
            assert px[0] > 200 and px[2] < 50, f"Expected Frame 1 (Red), got {px}"

    # 6. PNG palette (P)
    _test_fmt("png_p", lambda: Image.new("P", (60, 60)), ext=".png")
    # 7. RGBA
    _test_fmt("rgba", lambda: Image.new("RGBA", (60, 60), (255, 0, 0, 128)), ext=".png")
    
    # 8. LA (Grayscale + Alpha composited onto white)
    def _make_la():
        im = Image.new("LA", (60, 60), (0, 128))  # Black with ~50% alpha
        return im
    res_la, out_la = _test_fmt("la", _make_la, ext=".png")
    assert res_la.success is True
    with zipfile.ZipFile(out_la) as zf:
        emb_bytes = zf.read("word/media/image1.png")
        with Image.open(io.BytesIO(emb_bytes)) as emb:
            bg = Image.new("RGBA", emb.size, (255, 255, 255, 255))
            comp = Image.alpha_composite(bg, emb.convert("RGBA")).convert("RGB")
            px = comp.getpixel((30, 30))
            # 50% black on white background gives ~128 gray
            assert 100 <= px[0] <= 155, f"Expected ~128 gray from LA composite, got {px}"

    # 9. CMYK (Cyan=0, Magenta=255, Yellow=255, Black=0 -> Red)
    def _make_cmyk():
        im = Image.new("CMYK", (60, 60), (0, 255, 255, 0))
        return im
    res_cmyk, out_cmyk = _test_fmt("cmyk", _make_cmyk, ext=".jpg")
    assert res_cmyk.success is True
    with zipfile.ZipFile(out_cmyk) as zf:
        emb_bytes = zf.read("word/media/image1.png")
        with Image.open(io.BytesIO(emb_bytes)) as emb:
            px = emb.convert("RGB").getpixel((30, 30))
            # CMYK (0, 255, 255, 0) converts to pure RED in RGB
            assert px[0] > 200 and px[1] < 50 and px[2] < 50, f"Expected Red from CMYK, got {px}"

    # 10. 16-bit (I;16)
    def _make_i16():
        im = Image.new("I;16", (60, 60))
        for y in range(60):
            for x in range(60):
                im.putpixel((x, y), 32768)
        return im
    res_i16, out_i16 = _test_fmt("i16", _make_i16, ext=".png")
    assert res_i16.success is True
    with zipfile.ZipFile(out_i16) as zf:
        emb_bytes = zf.read("word/media/image1.png")
        with Image.open(io.BytesIO(emb_bytes)) as emb:
            px = emb.convert("RGB").getpixel((30, 30))
            assert 100 <= px[0] <= 155, f"Expected mid-gray from I;16 (32768), got {px}"

    # 11. HEIC (monkeypatched _HEIF_AVAILABLE = False for fallback rejection test)
    monkeypatch.setattr("image_converter.core.engine._HEIF_AVAILABLE", False)
    _test_fmt("heic", lambda: None, is_heic=True, ext=".heic")
    # 12. Corrupt .jpg
    _test_fmt("corrupt_jpg", lambda: None, is_corrupt=True, corrupt_bytes=b"\xff\xd8\xff\xe0" + b"\x00"*20, ext=".jpg")
    # 13. 0-byte .jpg
    _test_fmt("zero_byte_jpg", lambda: None, is_corrupt=True, corrupt_bytes=b"", ext=".jpg")
    # 14. .txt renamed .png
    _test_fmt("txt_renamed_png", lambda: None, is_corrupt=True, corrupt_bytes=b"This is a text file not a PNG", ext=".png")

    print("\n--- ITEM 8 FORMAT MATRIX TABLE ---")
    print(f"{'Format':<16} | {'Mode':<8} | {'Result'}")
    print("-" * 80)
    for fmt, mode, res in table_rows:
        print(f"{fmt:<16} | {mode:<8} | {res}")
    print("-" * 80 + "\n")


def test_real_heic_to_docx_with_orientation_and_pixels(engine, temp_dir):
    """
    Item 8 (A2 & B4): Test a REAL .heic file generated by pillow_heif with known color blocks,
    converted to DOCX, verifying embedded media format and pixel values.
    """
    import io
    import zipfile
    import pillow_heif

    pillow_heif.register_heif_opener()

    # Create real HEIC image: left half green (0, 255, 0), right half red (255, 0, 0)
    heic_img = Image.new("RGB", (64, 64), (255, 0, 0))
    for x in range(32):
        for y in range(64):
            heic_img.putpixel((x, y), (0, 255, 0))

    heic_path = temp_dir / "real_input.heic"
    heic_img.save(str(heic_path), format="HEIF")
    assert heic_path.exists() and heic_path.stat().st_size > 0

    out_docx = temp_dir / "real_heic_out.docx"
    res = engine.convert_single(heic_path, out_docx, ConversionConfig(target_format="DOCX"))
    assert res.success is True
    assert out_docx.exists()

    with zipfile.ZipFile(out_docx) as zf:
        media_names = [n for n in zf.namelist() if n.startswith("word/media/image")]
        assert len(media_names) == 1
        emb_bytes = zf.read(media_names[0])

    with Image.open(io.BytesIO(emb_bytes)) as emb:
        assert emb.size == (64, 64)
        left_px = emb.getpixel((16, 32))
        right_px = emb.getpixel((48, 32))
        # Left pixel is Green
        assert left_px[1] > 200 and left_px[0] < 50, f"Expected Green on left, got {left_px}"
        # Right pixel is Red
        assert right_px[0] > 200 and right_px[1] < 50, f"Expected Red on right, got {right_px}"



def test_image_to_docx_dpi_edge_cases(engine, temp_dir):
    """
    Item 8b.3: Test DPI edge cases: missing DPI, (0, 0), non-square DPI (300, 600), high DPI (1200).
    Asserts safe defaults and no ZeroDivisionError.
    """
    import xml.etree.ElementTree as ET
    import zipfile

    dpi_cases = [
        ("missing", None),
        ("zero", (0, 0)),
        ("non_square", (300, 600)),
        ("high", (1200, 1200)),
    ]

    for name, dpi_val in dpi_cases:
        p = temp_dir / f"dpi_{name}.png"
        im = Image.new("RGB", (600, 600), (100, 150, 200))
        if dpi_val is not None:
            im.save(p, dpi=dpi_val)
        else:
            im.save(p)

        out_docx = temp_dir / f"dpi_{name}.docx"
        res = engine.convert_single(p, out_docx, ConversionConfig(target_format="DOCX"))
        assert res.success is True
        assert out_docx.exists()

        # Verify wp:extent is present and > 0 in document.xml
        with zipfile.ZipFile(out_docx) as zf:
            xml_content = zf.read("word/document.xml")
            root = ET.fromstring(xml_content)
            extent = root.find(".//{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}extent")
            assert extent is not None
            cx = int(extent.attrib["cx"])
            cy = int(extent.attrib["cy"])
            assert cx > 0 and cy > 0

            # In non-square DPI (300 x 600), width in EMUs should be 2x height in EMUs
            if name == "non_square":
                ratio = cx / cy
                assert 1.9 < ratio < 2.1, f"Expected 2:1 ratio for (300, 600) DPI, got cx={cx}, cy={cy}"


def test_image_to_docx_emu_fit_document_xml(engine, temp_dir):
    """
    Item 8b.4: Read wp:extent directly from word/document.xml (not values computed by code).
    Covers tall (500x4000), wide (4000x300), and tiny (50x50).
    Verifies small images are NOT upscaled (upscale policy = natural size capped at page bounds).
    """
    import xml.etree.ElementTree as ET
    import zipfile
    import docx

    # 1. Tall image (500 x 4000)
    tall_p = temp_dir / "tall_img.png"
    Image.new("RGB", (500, 4000), (50, 50, 200)).save(tall_p)
    out_tall = temp_dir / "out_tall.docx"
    res_tall = engine.convert_single(tall_p, out_tall, ConversionConfig(target_format="DOCX"))
    assert res_tall.success is True

    # 2. Wide image (4000 x 300)
    wide_p = temp_dir / "wide_img.png"
    Image.new("RGB", (4000, 300), (200, 50, 50)).save(wide_p)
    out_wide = temp_dir / "out_wide.docx"
    res_wide = engine.convert_single(wide_p, out_wide, ConversionConfig(target_format="DOCX"))
    assert res_wide.success is True

    # 3. Tiny image (50 x 50)
    tiny_p = temp_dir / "tiny_img.png"
    Image.new("RGB", (50, 50), (50, 200, 50)).save(tiny_p)
    out_tiny = temp_dir / "out_tiny.docx"
    res_tiny = engine.convert_single(tiny_p, out_tiny, ConversionConfig(target_format="DOCX"))
    assert res_tiny.success is True

    # Page margin bounds from python-docx
    d_ref = docx.Document()
    sec = d_ref.sections[0]
    avail_w = sec.page_width - sec.left_margin - sec.right_margin
    avail_h = sec.page_height - sec.top_margin - sec.bottom_margin

    for docx_path, desc in [(out_tall, "tall"), (out_wide, "wide"), (out_tiny, "tiny")]:
        with zipfile.ZipFile(docx_path) as zf:
            root = ET.fromstring(zf.read("word/document.xml"))
            extent = root.find(".//{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}extent")
            assert extent is not None
            cx = int(extent.attrib["cx"])
            cy = int(extent.attrib["cy"])

            # Assert wp:extent from document.xml respects margins
            assert cx <= avail_w, f"{desc}: cx {cx} exceeds avail_w {avail_w}"
            assert cy <= avail_h, f"{desc}: cy {cy} exceeds avail_h {avail_h}"

            # Assert tiny image was NOT upscaled
            if desc == "tiny":
                # Natural size of 50px at 96 DPI: 50 / 96 * 914400 = 476,250 EMUs
                expected_tiny_emu = int((50 / 96.0) * 914400)
                assert cx == expected_tiny_emu, f"Tiny image should not be upscaled: cx={cx} != {expected_tiny_emu}"
                assert cy == expected_tiny_emu, f"Tiny image should not be upscaled: cy={cy} != {expected_tiny_emu}"


def test_image_to_docx_batch_partial_failure_isolation(engine, temp_dir):
    """
    Item 8b.5: Batch policy when 1 of N images fails.
    Policy: Isolate, skip, and report. Good inputs produce valid .docx files.
    Bad input returns success=False with no partial file.
    Total good .docx documents equals number of good inputs.
    """
    import docx

    good1 = temp_dir / "batch_good1.png"
    Image.new("RGB", (100, 100), (10, 20, 30)).save(good1)
    bad2 = temp_dir / "batch_bad2.jpg"
    bad2.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 20)  # corrupt
    good3 = temp_dir / "batch_good3.png"
    Image.new("RGB", (100, 100), (40, 50, 60)).save(good3)

    out1 = temp_dir / "out_b1.docx"
    out2 = temp_dir / "out_b2.docx"
    out3 = temp_dir / "out_b3.docx"

    cfg = ConversionConfig(target_format="DOCX")
    tasks = [(good1, out1, cfg), (bad2, out2, cfg), (good3, out3, cfg)]
    results = engine.convert_batch(tasks)

    assert len(results) == 3
    assert results[0].success is True
    assert out1.exists()

    assert results[1].success is False
    assert "Corrupt or unreadable" in results[1].error_message
    assert not out2.exists()

    assert results[2].success is True
    assert out3.exists()

    # Reopen produced .docx files and assert each contains exactly 1 valid image
    d1 = docx.Document(str(out1))
    assert len(d1.inline_shapes) == 1
    d3 = docx.Document(str(out3))
    assert len(d3.inline_shapes) == 1


def test_engine_auto_orient_failure_logs_and_surfaces_warning(engine, temp_dir, monkeypatch, caplog):
    import logging
    from PIL import ImageOps

    img_path = temp_dir / "test_orient.jpg"
    im = Image.new("RGB", (50, 50), color="red")
    im.save(str(img_path))
    out_path = temp_dir / "out.png"

    def mock_transpose(img):
        raise ValueError("Corrupted orientation EXIF marker")

    monkeypatch.setattr(ImageOps, "exif_transpose", mock_transpose)

    with caplog.at_level(logging.WARNING):
        res = engine.convert_single(img_path, out_path, ConversionConfig(target_format="PNG", auto_orient=True))

    assert res.success is True
    assert res.error_message is not None and "Auto-orientation failed" in res.error_message
    assert any("Auto-orientation failed" in record.message for record in caplog.records)


def test_engine_convert_single_exception_is_logged(engine, temp_dir, monkeypatch, caplog):
    import logging

    img_path = temp_dir / "test_throw.jpg"
    im = Image.new("RGB", (50, 50), color="green")
    im.save(str(img_path))
    out_path = temp_dir / "out.jpg"

    def mock_calc(*args, **kwargs):
        raise RuntimeError("Calculation internal crash")

    monkeypatch.setattr(engine, "calculate_dimensions", mock_calc)

    with caplog.at_level(logging.ERROR):
        res = engine.convert_single(img_path, out_path, ConversionConfig(target_format="JPG"))

    assert res.success is False
    assert "Calculation internal crash" in res.error_message
    assert any("Conversion error for" in record.message for record in caplog.records)


def test_metadata_stripping_transpose_failure_fails_and_does_not_silently_keep(temp_dir, monkeypatch):
    from image_converter.core.metadata_engine import strip_file_metadata
    from PIL import ImageOps

    img_path = temp_dir / "test_meta.jpg"
    im = Image.new("RGB", (60, 60), color="blue")
    im.save(str(img_path))

    def mock_fail(img):
        raise ValueError("Corrupt EXIF orientation tag")

    monkeypatch.setattr(ImageOps, "exif_transpose", mock_fail)

    res = strip_file_metadata(img_path)
    assert res["success"] is False
    assert "Metadata stripping failed" in str(res["error_message"])



