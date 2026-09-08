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
