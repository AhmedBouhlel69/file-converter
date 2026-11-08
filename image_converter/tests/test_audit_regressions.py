"""Regressions found by the static audit (undefined names that only fail at run time)."""

from pathlib import Path

from PIL import Image

from image_converter.core.conversion import engine as engine_module
from image_converter.core.conversion.engine import ConversionConfig, UniversalConverterEngine


def test_text_to_html_escapes_markup_and_succeeds(tmp_path):
    source = tmp_path / "note.txt"
    source.write_text("a <b>bold</b> & more\nsecond line", encoding="utf-8")
    result = UniversalConverterEngine().convert_single(
        source, tmp_path / "note.html", ConversionConfig(target_format="HTML")
    )
    assert result.success, result.error_message
    html = (tmp_path / "note.html").read_text(encoding="utf-8")
    assert "&lt;b&gt;bold&lt;/b&gt; &amp; more\nsecond line" in html
    assert "<br>" not in html  # line breaks inside <pre> are kept, not doubled
    assert "<title>note</title>" in html


def test_image_to_docx_survives_malformed_dpi_metadata(tmp_path, monkeypatch):
    source = tmp_path / "scan.png"
    Image.new("RGB", (60, 40), "white").save(source)
    real_transpose = engine_module.ImageOps.exif_transpose

    def bad_dpi(image):
        result = real_transpose(image)
        (result or image).info["dpi"] = ("unreadable", 72)
        return result

    monkeypatch.setattr(engine_module.ImageOps, "exif_transpose", bad_dpi)
    result = UniversalConverterEngine().convert_single(
        source, tmp_path / "scan.docx", ConversionConfig(target_format="DOCX")
    )
    # Used to raise NameError (img_p) while reporting the bad DPI value.
    assert result.success, result.error_message
    assert Path(tmp_path / "scan.docx").stat().st_size > 0
