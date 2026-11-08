"""
Data conversion engine for CSV and Excel (.xlsx, .xls) files.
Supports converting between CSV, Excel, PDF tables, JSON, HTML, and Text.
"""

from __future__ import annotations

import csv
import datetime as _dt
import html
import io
import json
import re
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd

from image_converter.core.text_io import xml_safe

logger = logging.getLogger(__name__)

# Check openpyxl
_OPENPYXL_AVAILABLE = False
try:
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    _OPENPYXL_AVAILABLE = True
except ImportError:
    pass

# Check reportlab
_REPORTLAB_AVAILABLE = False
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table as RLTable,
        TableStyle as RLTableStyle,
    )
    _REPORTLAB_AVAILABLE = True
except ImportError:
    pass


_DELIMITERS = (",", ";", "\t", "|")
_INT_RE = re.compile(r"^[+-]?\d+$")
_DOT_FLOAT_RE = re.compile(r"^[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?$")
_COMMA_FLOAT_RE = re.compile(r"^[+-]?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?$")


def _sniff_delimiter(text: str) -> str:
    """Pick the delimiter that splits the first lines into a consistent column count."""
    lines = [line for line in text.splitlines()[:60] if line.strip()]
    if not lines:
        return ","
    best, best_score = ",", -1.0
    for delimiter in _DELIMITERS:
        try:
            counts = [len(row) for row in csv.reader(lines, delimiter=delimiter)]
        except csv.Error:
            continue
        if not counts:
            continue
        common = max(set(counts), key=counts.count)
        if common < 2:
            continue
        consistency = counts.count(common) / len(counts)
        score = consistency * 10 + min(common, 50) / 50
        if score > best_score + 1e-9:
            best, best_score = delimiter, score
    return best


def _has_leading_zero(value: str) -> bool:
    digits = value.lstrip("+-")
    return len(digits) > 1 and digits[0] == "0" and digits[1].isdigit()


def infer_column_types(df: pd.DataFrame, decimal: str = ".") -> pd.DataFrame:
    """Convert text columns to numbers only when that loses nothing.

    Columns stay text when any value has a leading zero (IDs, phone numbers, ZIP
    codes), has more than 15 significant digits, or is not a number. Whole
    numbers become nullable integers so they never print as ``1.0``.
    """
    result = df.copy()
    for column in result.columns:
        series = result[column]
        values = [str(v).strip() for v in series if v is not None and not (isinstance(v, float) and pd.isna(v)) and str(v).strip() != ""]
        if not values:
            result[column] = series.replace("", None)
            continue
        if any(_has_leading_zero(v) for v in values) or any(len(v.lstrip("+-").replace(".", "").replace(",", "")) > 15 for v in values):
            result[column] = series.replace("", None)
            continue
        if all(_INT_RE.match(v) for v in values):
            result[column] = pd.array([int(str(v).strip()) if str(v).strip() else None for v in series], dtype="Int64")
            continue
        if decimal == ",":
            if all(_COMMA_FLOAT_RE.match(v) for v in values):
                converted = [float(str(v).strip().replace(".", "").replace(",", ".")) if str(v).strip() else None for v in series]
                result[column] = pd.array(converted, dtype="Float64")
                continue
        elif all(_DOT_FLOAT_RE.match(v) for v in values):
            result[column] = pd.array([float(str(v).strip()) if str(v).strip() else None for v in series], dtype="Float64")
            continue
        result[column] = series.replace("", None)
    return result


def read_csv_with_fallback(file_path: str | Path, **kwargs) -> pd.DataFrame:
    """
    Read a CSV file the way a person would expect it to look in Excel.

    The encoding is detected (UTF-8, UTF-8 with BOM, UTF-16 and ANSI code pages),
    the delimiter is detected (comma, semicolon, tab or pipe), decimal commas are
    recognised for semicolon files, and text such as leading-zero IDs or phone
    numbers is kept exactly as written.
    """
    from image_converter.core.text_io import decode_text

    p = Path(file_path).resolve()
    text, encoding = decode_text(p.read_bytes())
    delimiter = kwargs.pop("sep", None) or _sniff_delimiter(text)
    infer = kwargs.pop("infer_types", True)
    df = pd.read_csv(
        io.StringIO(text),
        sep=delimiter,
        dtype=str,
        keep_default_na=False,
        skipinitialspace=False,
        **kwargs,
    )
    df.columns = [str(c).strip() if str(c).strip() else f"Column {i + 1}" for i, c in enumerate(df.columns)]
    df.attrs["encoding"] = encoding
    df.attrs["delimiter"] = delimiter
    if not infer:
        return df
    decimal = "."
    if delimiter != ",":
        sample = [str(v).strip() for column in df.columns for v in df[column].head(200)]
        if any(re.match(r"^[+-]?\d+,\d+$", v) for v in sample) and not any(re.match(r"^[+-]?\d+\.\d+$", v) for v in sample):
            decimal = ","
    df = infer_column_types(df, decimal=decimal)
    df.attrs["encoding"] = encoding
    df.attrs["delimiter"] = delimiter
    return df


def _plain(value: Any) -> Any:
    """Convert pandas/numpy scalars to JSON- and openpyxl-friendly Python values."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            value = value.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e15:
        return int(value)
    if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
        return _format_temporal(value)
    if isinstance(value, pd.Timestamp):
        return _format_temporal(value.to_pydatetime())
    return value


def _format_temporal(value: Any) -> str:
    if isinstance(value, _dt.datetime):
        if value.time() == _dt.time(0, 0):
            return value.date().isoformat()
        return value.isoformat(sep=" ", timespec="seconds" if value.second else "minutes")
    if isinstance(value, _dt.date):
        return value.isoformat()
    if isinstance(value, _dt.time):
        return value.isoformat(timespec="seconds" if value.second else "minutes")
    return str(value)


def _display(value: Any) -> str:
    plain = _plain(value)
    if plain is None:
        return ""
    if isinstance(plain, float):
        return repr(plain) if abs(plain) >= 1e15 else f"{plain:.15g}"
    return str(plain)


def dataframe_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    return [{str(column): _plain(value) for column, value in zip(df.columns, row)} for row in df.itertuples(index=False, name=None)]


def read_excel_sheets(path: str | Path, sheet_name: Optional[str] = None) -> Dict[str, pd.DataFrame]:
    """Read sheets with their real cell types (ints stay ints, dates stay dates)."""
    p = Path(path)
    if p.suffix.lower() in (".xlsx", ".xlsm") and _OPENPYXL_AVAILABLE:
        wb = openpyxl.load_workbook(str(p), read_only=True, data_only=True)
        try:
            names = [sheet_name] if sheet_name is not None else list(wb.sheetnames)
            frames: Dict[str, pd.DataFrame] = {}
            for name in names:
                if name not in wb.sheetnames:
                    raise ValueError(f"Worksheet '{name}' was not found. Sheets: {', '.join(wb.sheetnames)}")
                rows = [list(r) for r in wb[name].iter_rows(values_only=True)]
                while rows and all(v is None or (isinstance(v, str) and not v.strip()) for v in rows[-1]):
                    rows.pop()
                while rows and all(v is None or (isinstance(v, str) and not v.strip()) for v in rows[0]):
                    rows.pop(0)
                if not rows:
                    frames[name] = pd.DataFrame()
                    continue
                width = max(
                    (max((i + 1 for i, v in enumerate(r) if v is not None and v != ""), default=0) for r in rows),
                    default=0,
                )
                header = rows[0][:width] + [None] * (width - len(rows[0][:width]))
                columns, seen = [], {}
                for i, h in enumerate(header):
                    label = _display(h).strip() or f"Column {i + 1}"
                    if label in seen:
                        seen[label] += 1
                        label = f"{label} ({seen[label]})"
                    else:
                        seen[label] = 1
                    columns.append(label)
                body = [[_plain(v) for v in (r[:width] + [None] * (width - len(r[:width])))] for r in rows[1:]]
                frames[name] = pd.DataFrame(body, columns=columns, dtype=object)
            return frames
        finally:
            wb.close()
    result = pd.read_excel(str(p), sheet_name=sheet_name if sheet_name is not None else None, dtype=object)
    if isinstance(result, pd.DataFrame):
        return {str(sheet_name): result}
    return {str(k): v for k, v in result.items()}


def get_csv_metadata(file_path: str | Path) -> Dict[str, Any]:
    """Extract metadata, row count, and column names from a CSV file."""
    p = Path(file_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"CSV file not found: {file_path}")

    file_size = p.stat().st_size
    rows = 0
    cols = 0
    col_names: List[str] = []

    try:
        df = read_csv_with_fallback(p, nrows=100)
        cols = len(df.columns)
        col_names = [str(c) for c in df.columns]

        # Fast line count
        with open(p, "rb") as f:
            rows = max(0, sum(1 for _ in f) - 1)
    except Exception as e:
        logger.warning(f"Error extracting CSV metadata for {p.name}: {e}", exc_info=True)

    return {
        "file_name": p.name,
        "file_path": str(p),
        "file_size": file_size,
        "width": cols,
        "height": rows,
        "rows": rows,
        "cols": cols,
        "columns": col_names[:10],
        "format": "CSV",
        "has_alpha": False,
    }


def get_excel_metadata(file_path: str | Path) -> Dict[str, Any]:
    """Extract metadata, sheet names, and dimensions from an Excel file."""
    p = Path(file_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"Excel file not found: {file_path}")

    file_size = p.stat().st_size
    sheet_names: List[str] = []
    total_rows = 0
    total_cols = 0

    if _OPENPYXL_AVAILABLE:
        try:
            wb = openpyxl.load_workbook(str(p), read_only=True)
            sheet_names = wb.sheetnames
            if sheet_names:
                ws = wb[sheet_names[0]]
                total_rows = ws.max_row or 0
                total_cols = ws.max_column or 0
            wb.close()
        except Exception as e:
            logger.warning(f"openpyxl failed to read Excel metadata for {p.name}: {e}", exc_info=True)

    if not sheet_names:
        try:
            xl = pd.ExcelFile(str(p))
            sheet_names = xl.sheet_names
            df = xl.parse(sheet_names[0], nrows=5)
            total_rows = len(df)
            total_cols = len(df.columns)
        except Exception as e:
            logger.warning(f"pandas fallback failed to read Excel metadata for {p.name}: {e}", exc_info=True)

    return {
        "file_name": p.name,
        "file_path": str(p),
        "file_size": file_size,
        "width": total_cols,
        "height": total_rows,
        "rows": total_rows,
        "cols": total_cols,
        "sheets": sheet_names,
        "format": "XLSX",
        "has_alpha": False,
    }


class DataConverter:
    """Core data conversion engine handling CSV and Excel spreadsheets."""

    PDF_MAX_ROWS = 20000

    def __init__(self):
        self.has_openpyxl = _OPENPYXL_AVAILABLE
        self.has_reportlab = _REPORTLAB_AVAILABLE
        self.last_warning: Optional[str] = None

    # -------------------------------------------------------------------------
    # CSV Input Conversions
    # -------------------------------------------------------------------------

    def convert_csv_to_excel(
        self,
        csv_path: str | Path,
        output_path: str | Path,
        sheet_name: str = "Data",
    ) -> Path:
        """Convert CSV to a styled workbook with real numbers and untouched text."""
        in_p = Path(csv_path).resolve()
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        df = read_csv_with_fallback(in_p)
        self._write_workbook({sheet_name: df}, out_p)
        return out_p

    def _write_workbook(self, frames: Dict[str, pd.DataFrame], out_p: Path) -> None:
        if not self.has_openpyxl:
            with pd.ExcelWriter(str(out_p)) as writer:
                for name, df in frames.items():
                    df.to_excel(writer, sheet_name=name[:31] or "Sheet", index=False)
            return
        from openpyxl.cell import WriteOnlyCell

        # Write-only mode streams rows: ~10x faster and far less memory on big files.
        wb = openpyxl.Workbook(write_only=True)
        header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        header_align = Alignment(horizontal="center", vertical="center")
        for name, df in frames.items():
            ws = wb.create_sheet(title=(re.sub(r"[\\/*?:\[\]]", "_", name)[:31] or "Sheet"))
            headers = [xml_safe(str(c)) for c in df.columns]
            sample = df.head(2000)
            for c_idx, column in enumerate(df.columns, start=1):
                longest = max([len(headers[c_idx - 1])] + [len(_display(v)) for v in sample[column]])
                ws.column_dimensions[get_column_letter(c_idx)].width = max(10, min(longest + 3, 50))
            if headers:
                ws.freeze_panes = "A2"
                if len(df):
                    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(df) + 1}"
            header_cells = []
            for header in headers:
                cell = WriteOnlyCell(ws, value=header)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = header_align
                header_cells.append(cell)
            ws.append(header_cells)
            for row in df.itertuples(index=False, name=None):
                values = []
                for value in row:
                    value = _plain(value)
                    if isinstance(value, str):
                        value = xml_safe(value)
                        if value.startswith(("=", "+", "-", "@")) and not _is_number_text(value):
                            # Never let CSV text become a live formula.
                            cell = WriteOnlyCell(ws, value=value)
                            cell.data_type = "s"
                            value = cell
                    values.append(value)
                ws.append(values)
        if not wb.sheetnames:
            wb.create_sheet("Sheet")
        wb.save(str(out_p))

    def convert_csv_to_pdf(
        self,
        csv_path: str | Path,
        output_path: str | Path,
        title: Optional[str] = None,
        max_rows: Optional[int] = None,
    ) -> Path:
        """Convert CSV data into a printable PDF table (any script, any length)."""
        in_p = Path(csv_path).resolve()
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        df = read_csv_with_fallback(in_p)
        return self._frames_to_pdf({"": df}, out_p, title or in_p.stem, max_rows=max_rows)

    def convert_csv_to_json(
        self,
        csv_path: str | Path,
        output_path: str | Path,
        indent: int = 2,
    ) -> Path:
        """Convert CSV to JSON records with real numbers and readable text."""
        in_p = Path(csv_path).resolve()
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        df = read_csv_with_fallback(in_p)
        out_p.write_text(json.dumps(dataframe_records(df), indent=indent, ensure_ascii=False), encoding="utf-8")
        return out_p

    def convert_csv_to_html(
        self,
        csv_path: str | Path,
        output_path: str | Path,
    ) -> Path:
        """Convert CSV to a standalone responsive HTML page with modern styling."""
        in_p = Path(csv_path).resolve()
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        df = read_csv_with_fallback(in_p)
        return self._dataframe_to_html(df, out_p, in_p.stem)

    def convert_csv_to_text(
        self,
        csv_path: str | Path,
        output_path: str | Path,
        delimiter: str = "\t",
    ) -> Path:
        """Convert CSV to tab-separated text."""
        in_p = Path(csv_path).resolve()
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        df = read_csv_with_fallback(in_p)
        self._frame_to_delimited(df, out_p, delimiter=delimiter, encoding="utf-8")
        return out_p

    @staticmethod
    def _frame_to_delimited(df: pd.DataFrame, out_p: Path, delimiter: str, encoding: str) -> None:
        with open(out_p, "w", encoding=encoding, newline="") as handle:
            writer = csv.writer(handle, delimiter=delimiter)
            writer.writerow([str(c) for c in df.columns])
            for row in df.itertuples(index=False, name=None):
                writer.writerow([_display(v) for v in row])

    # -------------------------------------------------------------------------
    # Excel (XLSX) Input Conversions
    # -------------------------------------------------------------------------

    def _non_empty_sheets(self, in_p: Path, sheet_name: Optional[str]) -> Dict[str, pd.DataFrame]:
        frames = read_excel_sheets(in_p, sheet_name=sheet_name)
        if sheet_name is not None:
            return frames
        filled = {name: df for name, df in frames.items() if not df.empty or len(df.columns)}
        return filled or frames

    def convert_excel_to_csv(
        self,
        xlsx_path: str | Path,
        output_path: str | Path,
        sheet_name: Optional[str] = None,
    ) -> Path:
        """Convert a workbook to CSV; extra non-empty sheets get their own files."""
        in_p = Path(xlsx_path).resolve()
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        self.last_warning = None
        frames = self._non_empty_sheets(in_p, sheet_name)
        names = list(frames)
        if not names:
            raise ValueError(f"Workbook '{in_p.name}' has no worksheets.")
        self._frame_to_delimited(frames[names[0]], out_p, delimiter=",", encoding="utf-8-sig")
        extra = []
        for name in names[1:]:
            safe = re.sub(r'[<>:"/\\|?*]+', "_", name).strip() or "Sheet"
            side = out_p.with_name(f"{out_p.stem} - {safe}{out_p.suffix}")
            counter = 2
            while side.exists():
                side = out_p.with_name(f"{out_p.stem} - {safe} ({counter}){out_p.suffix}")
                counter += 1
            self._frame_to_delimited(frames[name], side, delimiter=",", encoding="utf-8-sig")
            extra.append(side.name)
        if extra:
            self.last_warning = f"Sheet '{names[0]}' saved as {out_p.name}; other sheets saved as: {', '.join(extra)}"
        return out_p

    def convert_excel_to_pdf(
        self,
        xlsx_path: str | Path,
        output_path: str | Path,
        sheet_name: Optional[str] = None,
    ) -> Path:
        """Convert Excel to PDF with Excel itself when available, else as tables."""
        in_p = Path(xlsx_path).resolve()
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        self.last_warning = None
        try:
            return self._excel_com_to_pdf(in_p, out_p, sheet_name)
        except _OfficeUnavailable:
            pass
        from image_converter.core.platform import libreoffice

        if sheet_name is None and libreoffice.is_available():
            try:
                return libreoffice.convert(in_p, out_p, "PDF")
            except RuntimeError as exc:
                logger.warning("LibreOffice Excel-to-PDF failed, using table rendering: %s", exc)
        try:
            frames = self._non_empty_sheets(in_p, sheet_name)
            self._frames_to_pdf(frames, out_p, in_p.stem)
        except Exception as exc:
            raise RuntimeError(
                "Native Excel to PDF conversion requires Microsoft Excel on Windows, "
                f"and '{in_p.name}' could not be read as tables: {exc}"
            ) from exc
        self.last_warning = "Microsoft Excel was not available; the PDF shows cell values as tables without the workbook's formatting."
        return out_p

    def _excel_com_to_pdf(self, in_p: Path, out_p: Path, sheet_name: Optional[str]) -> Path:
        if os.name != "nt":
            raise _OfficeUnavailable()
        import time
        from image_converter.core.com_utils import (
            com_initialized,
            EXCEL_ALERTS_NONE,
            MSO_AUTOMATION_SECURITY_FORCE_DISABLE,
            XL_TYPE_PDF,
        )
        with com_initialized():
            try:
                import win32com.client
                excel = win32com.client.DispatchEx("Excel.Application")
            except Exception as dispatch_err:
                logger.warning(f"Excel COM not available: {dispatch_err}")
                raise _OfficeUnavailable() from dispatch_err

            try:
                excel.Visible = False
                excel.DisplayAlerts = EXCEL_ALERTS_NONE
                excel.AutomationSecurity = MSO_AUTOMATION_SECURITY_FORCE_DISABLE
                wb = None
                tmp_out = out_p.with_name(f"{out_p.stem}_tmp_{os.getpid()}_{time.time_ns()}.pdf")
                try:
                    try:
                        wb = excel.Workbooks.Open(str(in_p), ReadOnly=True)
                        if sheet_name:
                            ws = wb.Sheets(sheet_name)
                            ws.ExportAsFixedFormat(XL_TYPE_PDF, str(tmp_out))
                        else:
                            wb.ExportAsFixedFormat(XL_TYPE_PDF, str(tmp_out))
                    finally:
                        if wb is not None:
                            try:
                                wb.Close(False)
                            except Exception as close_err:
                                logger.warning(f"Error closing Excel workbook: {close_err}")
                    if tmp_out.is_file() and tmp_out.stat().st_size > 0:
                        os.replace(tmp_out, out_p)
                finally:
                    if tmp_out.exists():
                        try:
                            tmp_out.unlink()
                        except Exception as unlink_err:
                            logger.warning(f"Could not remove temporary file {tmp_out}: {unlink_err}")
            except Exception as e:
                logger.warning(f"MS Excel COM conversion failed for {in_p.name}: {e}", exc_info=True)
                raise RuntimeError(f"Microsoft Excel conversion failed for '{in_p.name}': {e}") from e
            finally:
                ws = None
                wb = None
                try:
                    excel.Quit()
                except Exception as quit_err:
                    logger.warning(f"Error quitting Excel application: {quit_err}")
                excel = None
                import gc
                gc.collect()
        if out_p.is_file() and out_p.stat().st_size > 0:
            return out_p
        raise RuntimeError(f"Microsoft Excel did not produce a PDF for '{in_p.name}'.")

    def convert_excel_to_json(
        self,
        xlsx_path: str | Path,
        output_path: str | Path,
        sheet_name: Optional[str] = None,
    ) -> Path:
        """Convert one sheet to a JSON list, or all sheets to {sheet: rows}."""
        in_p = Path(xlsx_path).resolve()
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        frames = read_excel_sheets(in_p, sheet_name=sheet_name)
        if sheet_name is not None:
            payload: Any = dataframe_records(next(iter(frames.values())))
        else:
            payload = {name: dataframe_records(df) for name, df in frames.items()}
        out_p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return out_p

    def convert_excel_to_html(
        self,
        xlsx_path: str | Path,
        output_path: str | Path,
        sheet_name: Optional[str] = None,
    ) -> Path:
        """Convert Excel sheet(s) to modern responsive HTML tables."""
        in_p = Path(xlsx_path).resolve()
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        frames = read_excel_sheets(in_p, sheet_name=sheet_name)
        if sheet_name is not None:
            return self._dataframe_to_html(next(iter(frames.values())), out_p, f"{in_p.stem} - {sheet_name}")
        sections = []
        for s_name, s_df in frames.items():
            sections.append(f"<h2>Sheet: {html.escape(s_name)}</h2>")
            sections.append(self._table_html(s_df))
        return self._write_html_page("\n".join(sections), out_p, in_p.stem)

    # -------------------------------------------------------------------------
    # Shared Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _numeric_columns(df: pd.DataFrame) -> List[bool]:
        flags = []
        for column in df.columns:
            values = [_plain(v) for v in df[column]]
            present = [v for v in values if v is not None]
            flags.append(bool(present) and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in present))
        return flags

    def _table_html(self, df: pd.DataFrame, max_rows: Optional[int] = None) -> str:
        numeric = self._numeric_columns(df)
        num_attr = [' class="num"' if flag else "" for flag in numeric]
        head = "".join(f"<th{num_attr[i]}>{html.escape(str(c))}</th>" for i, c in enumerate(df.columns))
        body = []
        for r_idx, row in enumerate(df.itertuples(index=False, name=None)):
            if max_rows is not None and r_idx >= max_rows:
                break
            cells = "".join(f"<td{num_attr[i]}>{html.escape(_display(v))}</td>" for i, v in enumerate(row))
            body.append(f"<tr>{cells}</tr>")
        return f'<table class="data-table"><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>'

    def _frames_to_pdf(
        self,
        frames: Dict[str, pd.DataFrame],
        out_path: Path,
        title: str,
        max_rows: Optional[int] = None,
    ) -> Path:
        from image_converter.core.text_io import html_to_pdf

        limit = max_rows or self.PDF_MAX_ROWS
        widest = max((len(df.columns) for df in frames.values()), default=0)
        parts = []
        for name, df in frames.items():
            if name:
                parts.append(f"<h2>{html.escape(name)}</h2>")
            if df.empty and not len(df.columns):
                parts.append("<p>(empty sheet)</p>")
                continue
            # Story tables draw header backgrounds wrongly across page breaks,
            # so the header row is plain table cells styled by CSS instead.
            table = self._table_html(df, max_rows=limit).replace("<thead>", "").replace("</thead>", "").replace("<tbody>", "").replace("</tbody>", "")
            parts.append(table)
            if len(df) > limit:
                parts.append(f"<p><i>Showing the first {limit:,} of {len(df):,} rows.</i></p>")
        font = "9pt" if widest <= 8 else ("7.5pt" if widest <= 14 else "6pt")
        html_to_pdf(
            "\n".join(parts),
            out_path,
            title=title,
            landscape=widest > 5,
            extra_css=f"table {{ font-size: {font}; margin-bottom: 12pt; }}",
        )
        return out_path

    def _dataframe_to_html(self, df: pd.DataFrame, out_path: Path, title: str) -> Path:
        """Render DataFrame into standalone HTML."""
        return self._write_html_page(self._table_html(df), out_path, title)

    def _write_html_page(self, content: str, out_path: Path, title: str) -> Path:
        full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      margin: 40px auto;
      max-width: 1200px;
      padding: 0 20px;
      color: #1f2937;
    }}
    h1, h2 {{ color: #111827; }}
    .table-wrap {{ overflow-x: auto; }}
    .data-table {{
      width: 100%;
      border-collapse: collapse;
      margin: 20px 0 32px 0;
      font-size: 14px;
    }}
    .data-table th {{
      background-color: #1e293b;
      color: white;
      text-align: left;
      padding: 10px 12px;
      font-weight: 600;
      position: sticky;
      top: 0;
    }}
    .data-table td {{
      padding: 8px 12px;
      border-bottom: 1px solid #e5e7eb;
    }}
    .data-table .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .data-table tr:nth-child(even) td {{ background-color: #f8fafc; }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <div class="table-wrap">
  {content}
  </div>
</body>
</html>"""
        out_path.write_text(full_html, encoding="utf-8")
        return out_path


class _OfficeUnavailable(Exception):
    """Raised internally when Microsoft Office automation cannot be used."""


def _is_number_text(value: str) -> bool:
    return bool(_DOT_FLOAT_RE.match(value.strip()))
