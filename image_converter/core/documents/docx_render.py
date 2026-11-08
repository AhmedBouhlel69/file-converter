"""Walk a Word document in reading order and render it to text or HTML.

python-docx exposes paragraphs and tables as separate lists, which made earlier
exports move every table to the end and lose lists, emphasis, links and
pictures. This module walks the body in order and keeps that structure.
"""

from __future__ import annotations

import base64
import html
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_V = "{urn:schemas-microsoft-com:vml}"

_ORDERED_FORMATS = {
    "decimal", "decimalZero", "upperRoman", "lowerRoman", "upperLetter", "lowerLetter",
    "ordinal", "cardinalText", "ordinalText", "decimalEnclosedCircle", "arabicAlpha", "arabicAbjad",
}


@dataclass
class _ListInfo:
    num_id: str
    level: int
    ordered: bool


class _Numbering:
    """Resolve whether a paragraph is a bulleted or numbered list item."""

    def __init__(self, document):
        self._formats: Dict[Tuple[str, int], str] = {}
        try:
            numbering = document.part.numbering_part.element
        except Exception:
            return
        abstract: Dict[str, Dict[int, str]] = {}
        for node in numbering.findall(f"{_W}abstractNum"):
            levels = {}
            for lvl in node.findall(f"{_W}lvl"):
                fmt = lvl.find(f"{_W}numFmt")
                levels[int(lvl.get(f"{_W}ilvl", "0"))] = fmt.get(f"{_W}val") if fmt is not None else "bullet"
            abstract[node.get(f"{_W}abstractNumId")] = levels
        for num in numbering.findall(f"{_W}num"):
            ref = num.find(f"{_W}abstractNumId")
            if ref is None:
                continue
            for level, fmt in abstract.get(ref.get(f"{_W}val"), {}).items():
                self._formats[(num.get(f"{_W}numId"), level)] = fmt

    def info(self, paragraph) -> Optional[_ListInfo]:
        num_pr = None
        ppr = paragraph._p.pPr
        if ppr is not None and ppr.numPr is not None:
            num_pr = ppr.numPr
        style = paragraph.style
        level_from_style = 0
        while num_pr is None and style is not None:
            sppr = style.element.pPr
            if sppr is not None and sppr.numPr is not None:
                num_pr = sppr.numPr
                break
            style = style.base_style
        if num_pr is None:
            name = (paragraph.style.name if paragraph.style is not None else "").lower()
            if name.startswith("list bullet"):
                return _ListInfo("style-bullet", level_from_style, False)
            if name.startswith("list number"):
                return _ListInfo("style-number", level_from_style, True)
            return None
        num_id = num_pr.numId.val if num_pr.numId is not None else None
        if num_id is None or str(num_id) == "0":
            return None
        level = num_pr.ilvl.val if num_pr.ilvl is not None else 0
        fmt = self._formats.get((str(num_id), int(level)), "bullet")
        return _ListInfo(str(num_id), int(level), fmt in _ORDERED_FORMATS)


@dataclass
class _Cell:
    text: str
    html: str
    colspan: int = 1
    rowspan: int = 1


@dataclass
class Block:
    kind: str  # "heading", "paragraph", "list", "table", "image-only"
    text: str = ""
    html: str = ""
    level: int = 0
    list_info: Optional[_ListInfo] = None
    rows: List[List[_Cell]] = field(default_factory=list)


def _run_html(run, document, images: bool) -> Tuple[str, str]:
    """Return (text, html) for a run, including pictures and line breaks."""
    text_parts: List[str] = []
    html_parts: List[str] = []
    for child in run._r.iterchildren():
        tag = child.tag
        if tag == f"{_W}t":
            text_parts.append(child.text or "")
            html_parts.append(html.escape(child.text or ""))
        elif tag == f"{_W}tab":
            text_parts.append("\t")
            html_parts.append("&emsp;")
        elif tag in (f"{_W}br", f"{_W}cr"):
            text_parts.append("\n")
            html_parts.append("<br>")
        elif tag in (f"{_W}drawing", f"{_W}pict") and images:
            for blip in child.iter(f"{_A}blip", f"{_V}imagedata"):
                rel = blip.get(f"{_R}embed") or blip.get(f"{_R}id")
                part = document.part.related_parts.get(rel) if rel else None
                if part is None:
                    continue
                content_type = getattr(part, "content_type", "image/png")
                if not content_type.startswith("image/") or content_type in ("image/x-emf", "image/x-wmf"):
                    continue
                encoded = base64.b64encode(part.blob).decode("ascii")
                html_parts.append(f'<img src="data:{content_type};base64,{encoded}" alt="">')
    inner = "".join(html_parts)
    if not inner:
        return "".join(text_parts), ""
    if run.bold:
        inner = f"<strong>{inner}</strong>"
    if run.italic:
        inner = f"<em>{inner}</em>"
    if run.underline:
        inner = f"<u>{inner}</u>"
    if getattr(run.font, "strike", False):
        inner = f"<s>{inner}</s>"
    if getattr(run.font, "superscript", False):
        inner = f"<sup>{inner}</sup>"
    elif getattr(run.font, "subscript", False):
        inner = f"<sub>{inner}</sub>"
    return "".join(text_parts), inner


def _paragraph_content(paragraph, document, images: bool) -> Tuple[str, str]:
    from docx.text.hyperlink import Hyperlink
    from docx.text.run import Run

    texts: List[str] = []
    htmls: List[str] = []
    try:
        items = list(paragraph.iter_inner_content())
    except AttributeError:  # python-docx < 1.0
        items = list(paragraph.runs)
    for item in items:
        if isinstance(item, Run):
            t, h = _run_html(item, document, images)
            texts.append(t)
            htmls.append(h)
        elif isinstance(item, Hyperlink):
            parts = [_run_html(r, document, images) for r in item.runs]
            t = "".join(p[0] for p in parts)
            h = "".join(p[1] for p in parts)
            address = getattr(item, "url", "") or ""
            texts.append(t)
            htmls.append(f'<a href="{html.escape(address, quote=True)}">{h}</a>' if address else h)
    return "".join(texts), "".join(htmls)


def _heading_level(paragraph) -> int:
    name = (paragraph.style.name if paragraph.style is not None else "").lower()
    if name == "title":
        return 1
    if name.startswith("heading"):
        try:
            return max(1, min(6, int(name.split()[-1])))
        except ValueError:
            return 2
    return 0


def _table_rows(table, document, images: bool) -> List[List[_Cell]]:
    """Return table rows with merged cells collapsed into colspan/rowspan."""
    from docx.table import _Cell as DocxCell

    grid: List[List[Optional[_Cell]]] = []
    origin_by_column: Dict[int, _Cell] = {}
    for tr in table._tbl.tr_lst:
        row: List[Optional[_Cell]] = []
        column = 0
        for tc in tr.tc_lst:
            span = tc.grid_span or 1
            vmerge = tc.vMerge
            if vmerge == "continue" and column in origin_by_column:
                origin_by_column[column].rowspan += 1
                column += span
                continue
            cell = DocxCell(tc, table)
            texts, htmls = [], []
            for paragraph in cell.paragraphs:
                t, h = _paragraph_content(paragraph, document, images)
                texts.append(t)
                htmls.append(h)
            text = "\n".join(t for t in texts).strip()
            markup = "<br>".join(h for h in htmls if h)
            item = _Cell(text=text, html=markup, colspan=span)
            for offset in range(span):
                origin_by_column.pop(column + offset, None)
            if vmerge == "restart":
                origin_by_column[column] = item
            row.append(item)
            column += span
        grid.append(row)
    return [[c for c in row if c is not None] for row in grid]


def read_blocks(document, images: bool = False) -> List[Block]:
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    numbering = _Numbering(document)
    blocks: List[Block] = []
    for item in document.iter_inner_content():
        if isinstance(item, Table):
            blocks.append(Block(kind="table", rows=_table_rows(item, document, images)))
            continue
        if not isinstance(item, Paragraph):
            continue
        text, markup = _paragraph_content(item, document, images)
        if not text.strip() and "<img" not in markup:
            blocks.append(Block(kind="blank"))
            continue
        level = _heading_level(item)
        if level:
            blocks.append(Block(kind="heading", text=text.strip(), html=markup, level=level))
            continue
        info = numbering.info(item)
        if info is not None:
            blocks.append(Block(kind="list", text=text.strip(), html=markup, list_info=info))
            continue
        blocks.append(Block(kind="paragraph", text=text, html=markup))
    return blocks


def blocks_to_text(blocks: List[Block]) -> str:
    lines: List[str] = []
    counters: Dict[Tuple[str, int], int] = {}

    def gap():
        if lines and lines[-1] != "":
            lines.append("")

    previous_kind = None
    for block in blocks:
        if block.kind == "blank":
            continue
        if block.kind == "list":
            info = block.list_info
            if previous_kind != "list":
                gap()
            key = (info.num_id, info.level)
            for deeper in [k for k in counters if k[0] == info.num_id and k[1] > info.level]:
                counters.pop(deeper)
            counters[key] = counters.get(key, 0) + 1
            marker = f"{counters[key]}." if info.ordered else "•"
            lines.append(f"{'    ' * info.level}{marker} {block.text}")
        elif block.kind == "table":
            gap()
            for row in block.rows:
                lines.append("\t".join(cell.text.replace("\n", " ") for cell in row))
            lines.append("")
        else:
            gap()
            lines.extend(block.text.strip("\n").split("\n"))
            if block.kind == "heading":
                lines.append("")
        previous_kind = block.kind
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


def _dir(text: str) -> str:
    from image_converter.core.text_io import _is_rtl

    return ' dir="rtl"' if _is_rtl(text) else ""


def blocks_to_html(blocks: List[Block]) -> str:
    out: List[str] = []
    open_lists: List[Tuple[str, int]] = []  # (tag, level)

    def close_lists(to_level: int = -1):
        while open_lists and open_lists[-1][1] > to_level:
            tag, _ = open_lists.pop()
            out.append(f"</li></{tag}>")

    for block in blocks:
        if block.kind != "list":
            close_lists()
        if block.kind == "blank":
            continue
        if block.kind == "heading":
            out.append(f'<h{block.level}{_dir(block.text)}>{block.html or html.escape(block.text)}</h{block.level}>')
        elif block.kind == "paragraph":
            out.append(f'<p{_dir(block.text)}>{block.html or html.escape(block.text)}</p>')
        elif block.kind == "list":
            info = block.list_info
            tag = "ol" if info.ordered else "ul"
            close_lists(info.level)
            if open_lists and open_lists[-1][1] == info.level and open_lists[-1][0] != tag:
                close_lists(info.level - 1)
            if open_lists and open_lists[-1][1] == info.level:
                out.append("</li><li>")
            else:
                out.append(f"<{tag}><li>")
                open_lists.append((tag, info.level))
            out.append(block.html or html.escape(block.text))
        elif block.kind == "table":
            rows_html = []
            for index, row in enumerate(block.rows):
                tag = "th" if index == 0 else "td"
                cells = []
                for cell in row:
                    attrs = ""
                    if cell.colspan > 1:
                        attrs += f' colspan="{cell.colspan}"'
                    if cell.rowspan > 1:
                        attrs += f' rowspan="{cell.rowspan}"'
                    cells.append(f"<{tag}{attrs}>{cell.html or html.escape(cell.text)}</{tag}>")
                rows_html.append("<tr>" + "".join(cells) + "</tr>")
            out.append("<table>" + "".join(rows_html) + "</table>")
    close_lists()
    return "\n".join(out)
