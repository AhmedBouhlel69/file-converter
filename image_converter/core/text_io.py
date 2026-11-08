"""Shared helpers for reading text files and rendering text/HTML to PDF.

Reading: plain-text inputs arrive in many encodings on Windows (UTF-8, UTF-8 with
BOM, "Unicode" = UTF-16 from Notepad, and legacy ANSI code pages such as
Windows-1252). ``read_text_file`` detects the encoding instead of silently
dropping every non-ASCII character.

Rendering: ``html_to_pdf`` uses PyMuPDF's Story layout engine, which shapes
complex scripts (Arabic joins and runs right-to-left) and falls back to built-in
Noto/Droid fonts for CJK, so no glyph turns into a black box and no system font
is required.
"""

from __future__ import annotations

import codecs
import html
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

_BOMS = (
    (codecs.BOM_UTF32_LE, "utf-32"),
    (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
)

# Characters that XML 1.0 (DOCX, PPTX, ODT, XLSX) cannot store.
_XML_INVALID = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")


def detect_encoding(data: bytes) -> str:
    """Best-effort encoding for raw text bytes. Never raises."""
    for bom, name in _BOMS:
        if data.startswith(bom):
            return name
    sample = data[:65536]
    # UTF-16 without BOM: every other byte is NUL for Latin text.
    if len(sample) >= 4:
        even_nuls = sample[0::2].count(0)
        odd_nuls = sample[1::2].count(0)
        half = len(sample) / 2
        if odd_nuls > half * 0.4 and even_nuls < half * 0.05:
            return "utf-16-le"
        if even_nuls > half * 0.4 and odd_nuls < half * 0.05:
            return "utf-16-be"
    try:
        data.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        from charset_normalizer import from_bytes

        best = from_bytes(sample).best()
        if best is not None and best.encoding:
            name = codecs.lookup(best.encoding).name
            # Short Western files are often guessed as a sibling Latin code page
            # (Central European, Baltic, Turkish). Windows-1252 is far more
            # likely on Windows when it decodes to ordinary Western letters.
            if not _is_non_latin(name) and _plausible_cp1252(data):
                return "cp1252"
            if name not in ("cp1252", "latin-1", "iso8859-1", "ascii"):
                try:
                    data.decode(name)
                    return name
                except (UnicodeDecodeError, LookupError):
                    pass
    except Exception as exc:  # pragma: no cover - optional dependency
        logger.debug("charset detection failed: %s", exc)
    return "cp1252"


_LATIN_SIBLINGS = {
    "cp1250", "cp1254", "cp1257", "cp850", "cp437", "mac-roman", "mac_roman",
    "iso8859-2", "iso8859-3", "iso8859-4", "iso8859-9", "iso8859-10", "iso8859-13",
    "iso8859-14", "iso8859-15", "iso8859-16", "latin-1", "iso8859-1",
}
_NON_LATIN_HINTS = (
    "1251", "koi8", "8859-5", "866", "855", "mac-cyrillic",  # Cyrillic
    "1253", "8859-7", "737", "869", "mac-greek",  # Greek
    "1255", "8859-8", "862", "424",  # Hebrew
    "1256", "8859-6", "720", "864", "mac-arabic",  # Arabic
    "874", "tis", "1258",  # Thai, Vietnamese
    "932", "jis", "euc", "gb", "big5", "949", "950", "hz", "johab", "uhc",  # CJK
)


def _is_non_latin(name: str) -> bool:
    lowered = name.lower().replace("_", "-")
    return any(hint in lowered for hint in _NON_LATIN_HINTS)


_WESTERN_EXTRA = set("€‚„…†‡ˆ‰‹Œ‘’“”•–—˜™›œŸ ¡¢£¤¥¦§¨©ª«¬­®¯°±²³´µ¶·¸¹º»¼½¾¿×÷")


def _plausible_cp1252(data: bytes) -> bool:
    try:
        text = data.decode("cp1252")
    except UnicodeDecodeError:
        return False
    high = [c for c in text if ord(c) > 127]
    if not high:
        return True
    good = sum(1 for c in high if c.isalpha() or c in _WESTERN_EXTRA)
    return good / len(high) >= 0.95


def decode_text(data: bytes) -> Tuple[str, str]:
    """Decode bytes to text, returning ``(text, encoding)``."""
    encoding = detect_encoding(data)
    try:
        text = data.decode(encoding)
    except (UnicodeDecodeError, LookupError):
        encoding = "cp1252"
        text = data.decode(encoding, errors="replace")
    if text.startswith("﻿"):
        text = text[1:]
    return text, encoding


def read_text_file(path: str | Path) -> str:
    """Read a text file of unknown encoding with universal newlines."""
    text, _ = decode_text(Path(path).read_bytes())
    return text.replace("\r\n", "\n").replace("\r", "\n")


def xml_safe(text: str) -> str:
    """Remove characters that Office/OpenDocument XML cannot store."""
    return _XML_INVALID.sub("", text)


def rtf_escape(text: str) -> str:
    """Escape text for an RTF body, including non-ASCII as \\uN? sequences."""
    out = []
    for char in text:
        code = ord(char)
        if char in "\\{}":
            out.append("\\" + char)
        elif char == "\t":
            out.append("\\tab ")
        elif code < 128:
            out.append(char)
        else:
            # RTF \u takes a signed 16-bit value; astral chars use surrogates.
            for unit in _utf16_units(char):
                out.append(f"\\u{unit if unit < 32768 else unit - 65536}?")
    return "".join(out)


def _utf16_units(char: str):
    data = char.encode("utf-16-le")
    for index in range(0, len(data), 2):
        yield data[index] | (data[index + 1] << 8)


BASE_CSS = """
body { font-family: sans-serif; font-size: 10.5pt; line-height: 1.4; color: #1e293b; }
h1 { font-size: 17pt; color: #0f172a; margin: 0 0 10pt 0; }
h2 { font-size: 14pt; color: #0f172a; margin: 12pt 0 6pt 0; }
h3 { font-size: 12pt; color: #0f172a; margin: 10pt 0 4pt 0; }
p { margin: 0 0 4pt 0; }
pre, .pre { white-space: pre-wrap; margin: 0; }
.mono { font-family: monospace; font-size: 9.5pt; }
table { border-collapse: collapse; width: 100%; }
th { font-weight: bold; text-align: left; padding: 3pt 4pt; color: #0f172a;
     border-bottom: 1.2pt solid #0f172a; }
td { padding: 3pt 4pt; border-bottom: 0.5pt solid #cbd5e1; vertical-align: top; }
td.num, th.num { text-align: right; }
"""


def _is_rtl(line: str) -> bool:
    """True when the first strongly-directional character is Arabic or Hebrew."""
    import unicodedata

    for char in line:
        kind = unicodedata.bidirectional(char)
        if kind in ("R", "AL"):
            return True
        if kind == "L":
            return False
    return False


def text_to_html_body(text: str) -> str:
    """Turn plain text into Story HTML that keeps blank lines and indentation."""
    lines = text.split("\n")
    indented = sum(1 for line in lines if line[:1] in (" ", "\t") and line.strip())
    aligned = sum(1 for line in lines if "  " in line.strip() or "\t" in line)
    nonblank = max(1, sum(1 for line in lines if line.strip()))
    # Code, logs and column-aligned text read better in a fixed-width font.
    css_class = "pre mono" if (indented + aligned) / nonblank > 0.3 else "pre"
    parts = []
    for line in lines:
        expanded = line.expandtabs(4)
        rtl = " dir='rtl'" if _is_rtl(expanded) else ""
        parts.append(f"<p class='{css_class}'{rtl}>{html.escape(expanded) or '&#160;'}</p>")
    return "\n".join(parts)


def html_to_pdf(
    body_html: str,
    out_path: str | Path,
    *,
    title: Optional[str] = None,
    landscape: bool = False,
    paper: str = "a4",
    extra_css: str = "",
    footer: bool = True,
) -> Path:
    """Lay out HTML across as many pages as needed and save atomically."""
    import pymupdf

    out_p = Path(out_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    temp = out_p.with_name(f".tmp_pdf_{os.getpid()}_{time.time_ns()}_{out_p.name}")
    page_rect = pymupdf.paper_rect(f"{paper}-l" if landscape else paper)
    margin = 36
    where = page_rect + (margin, margin, -margin, -margin - (14 if footer else 0))
    heading = f"<h1>{html.escape(title)}</h1>" if title else ""
    story = pymupdf.Story(html=f"<body>{heading}{body_html}</body>", user_css=BASE_CSS + extra_css)
    try:
        writer = pymupdf.DocumentWriter(str(temp))
        more = True
        pages = 0
        while more:
            device = writer.begin_page(page_rect)
            more, _ = story.place(where)
            story.draw(device)
            writer.end_page()
            pages += 1
            if pages > 20000:
                raise RuntimeError("Document is too long to lay out.")
        writer.close()
        if footer and pages:
            doc = pymupdf.open(str(temp))
            for number, page in enumerate(doc, 1):
                text = f"{number} / {pages}"
                width = pymupdf.get_text_length(text, fontname="helv", fontsize=7.5)
                page.insert_text(
                    (page.rect.width - margin - width, page.rect.height - margin + 6),
                    text,
                    fontname="helv",
                    fontsize=7.5,
                    color=(0.45, 0.5, 0.58),
                )
            doc.save(str(temp), incremental=True, encryption=0)
            doc.close()
        os.replace(temp, out_p)
    finally:
        if temp.exists():
            try:
                temp.unlink()
            except OSError:
                pass
    return out_p
