"""
Command Line Interface for Universal File Converter.
Supports Images, PDF, Word (DOCX), CSV, and Excel (XLSX).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from image_converter.core.engine import (
    ConversionConfig,
    ConversionResult,
    FORMAT_EXTENSIONS,
    ImageConverterEngine,
    UniversalConverterEngine,
    get_supported_input_extensions,
    get_supported_output_formats,
)


def parse_color(color_str: str) -> tuple[int, int, int]:
    """Parse hex '#ffffff' or '255,255,255' into (R, G, B) tuple."""
    color_str = color_str.strip()
    if color_str.startswith("#"):
        color_str = color_str.lstrip("#")
        if len(color_str) == 6:
            values = (
                int(color_str[0:2], 16),
                int(color_str[2:4], 16),
                int(color_str[4:6], 16),
            )
        elif len(color_str) == 3:
            values = (
                int(color_str[0] * 2, 16),
                int(color_str[1] * 2, 16),
                int(color_str[2] * 2, 16),
            )
        else:
            raise ValueError("hex colors must contain 3 or 6 digits")
    elif "," in color_str:
        parts = [int(p.strip()) for p in color_str.split(",")]
        if len(parts) != 3:
            raise ValueError("RGB colors must contain exactly 3 channels")
        values = tuple(parts)
    else:
        raise ValueError("use #rgb, #rrggbb, or r,g,b")

    if any(value < 0 or value > 255 for value in values):
        raise ValueError("color channels must be between 0 and 255")
    return values


def collect_convertible_files(path: Path, recursive: bool = False) -> List[Path]:
    """Scan directory or single file for supported images, documents, and data files."""
    supported_exts = set(get_supported_input_extensions())
    if path.is_file():
        if path.suffix.lower() in supported_exts:
            return [path]
        return []

    if path.is_dir():
        files: List[Path] = []
        iterator = path.rglob("*") if recursive else path.glob("*")
        for item in iterator:
            if item.is_file() and item.suffix.lower() in supported_exts:
                files.append(item)
        return sorted(files)

    return []


# Maintain backward compatibility with existing tests and imports
collect_image_files = collect_convertible_files


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Universal File Converter: Convert Images, PDF, Word (DOCX), CSV, and Excel (XLSX) files."
    )
    parser.add_argument(
        "-i",
        "--input",
        dest="input_path",
        type=str,
        help="Path to an input file or directory containing files to convert.",
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="output_path",
        type=str,
        help="Path to output file or output directory.",
    )
    parser.add_argument(
        "-f",
        "--format",
        dest="target_format",
        type=str,
        help=f"Target format: {', '.join(get_supported_output_formats())}",
    )
    parser.add_argument(
        "-q",
        "--quality",
        dest="quality",
        type=int,
        default=90,
        help="Compression quality (1-100) for JPG, WEBP, HEIC (default: 90).",
    )
    parser.add_argument(
        "--lossless",
        action="store_true",
        help="Use lossless compression for WebP.",
    )
    parser.add_argument(
        "--no-metadata",
        action="store_true",
        help="Strip EXIF metadata from converted images.",
    )
    parser.add_argument(
        "--no-auto-orient",
        action="store_true",
        help="Disable automatic EXIF orientation rotation.",
    )
    parser.add_argument(
        "--resize-percent",
        type=float,
        help="Resize image by percentage scale (e.g. 50 for 50%%).",
    )
    parser.add_argument(
        "--width",
        type=int,
        help="Target custom width in pixels.",
    )
    parser.add_argument(
        "--height",
        type=int,
        help="Target custom height in pixels.",
    )
    parser.add_argument(
        "--no-keep-ratio",
        action="store_true",
        help="Do not preserve aspect ratio when custom width and height are provided.",
    )
    parser.add_argument(
        "--bg-color",
        type=parse_color,
        default="#ffffff",
        help="Solid background color for transparent images when converting to JPG/BMP (hex '#ffffff' or '255,255,255').",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=150,
        help="DPI resolution when rendering PDF or DOCX pages to images (default: 150).",
    )
    parser.add_argument(
        "--sheet",
        dest="sheet_name",
        type=str,
        default=None,
        help="Specific sheet name for Excel (.xlsx) conversions.",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Scan directories recursively.",
    )
    parser.add_argument(
        "--list-formats",
        action="store_true",
        help="Print list of supported input and output formats.",
    )

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    args = parser.parse_args(argv)

    if args.list_formats:
        print("\n=== Universal File Converter Formats ===")
        print("\n[Images]")
        print("  Inputs:  .jpg, .jpeg, .png, .heic, .heif, .webp, .bmp, .tiff, .gif, .ico, .ppm, .tga, .eps")
        print("  Outputs: JPG, PNG, WEBP, HEIC, BMP, TIFF, GIF, ICO, PDF")
        print("\n[Documents]")
        print("  Inputs:  .pdf, .docx, .doc")
        print("  Outputs: PDF, DOCX, TXT, HTML, PNG, JPG, WEBP, CSV, XLSX")
        print("\n[Spreadsheets & Data]")
        print("  Inputs:  .csv, .xlsx, .xls")
        print("  Outputs: XLSX, CSV, PDF, JSON, HTML, TXT")
        print("\nAll Input Extensions:")
        print("  " + ", ".join(get_supported_input_extensions()))
        print("All Output Formats:")
        print("  " + ", ".join(get_supported_output_formats()) + "\n")
        return 0

    if not args.input_path:
        parser.print_help()
        return 1

    in_path = Path(args.input_path)
    if not in_path.exists():
        print(f"Error: Input path does not exist: {in_path}", file=sys.stderr)
        return 1

    files_to_process = collect_convertible_files(in_path, recursive=args.recursive)
    if not files_to_process:
        print(f"No supported files found in {in_path}", file=sys.stderr)
        return 1

    engine = UniversalConverterEngine()

    # Determine default target format
    target_format = args.target_format
    if not target_format:
        if args.output_path and Path(args.output_path).suffix:
            ext = Path(args.output_path).suffix.lstrip(".").upper()
            target_format = "JPG" if ext == "JPEG" else ext
        else:
            print("Error: Target format must be specified with -f/--format (e.g. -f PNG, -f PDF, -f XLSX).", file=sys.stderr)
            return 1

    target_format = target_format.upper()
    if target_format == "JPEG":
        target_format = "JPG"

    if not engine.is_format_supported(target_format):
        print(f"Error: Unsupported output format '{target_format}'. Available: {', '.join(get_supported_output_formats())}", file=sys.stderr)
        return 1

    # Configure resize options
    resize_mode = "none"
    if args.resize_percent:
        resize_mode = "percentage"
    elif args.width or args.height:
        resize_mode = "custom"

    config = ConversionConfig(
        target_format=target_format,
        quality=args.quality,
        lossless=args.lossless,
        preserve_metadata=not args.no_metadata,
        auto_orient=not args.no_auto_orient,
        resize_mode=resize_mode,
        resize_percent=args.resize_percent or 100.0,
        custom_width=args.width,
        custom_height=args.height,
        keep_aspect_ratio=not args.no_keep_ratio,
        background_color=args.bg_color,
        dpi=args.dpi,
        sheet_name=args.sheet_name,
    )

    ext = FORMAT_EXTENSIONS.get(target_format, f".{target_format.lower()}")

    # Determine output paths
    out_arg = Path(args.output_path) if args.output_path else None
    tasks = []

    if len(files_to_process) == 1 and out_arg and not out_arg.is_dir() and out_arg.suffix:
        # Single input to single explicit output file
        tasks.append((files_to_process[0], out_arg, config))
    else:
        # Batch or directory output
        out_dir = out_arg if out_arg else (in_path if in_path.is_dir() else in_path.parent)
        for f in files_to_process:
            dest_name = f"{f.stem}{ext}"
            dest_file = out_dir / dest_name
            tasks.append((f, dest_file, config))

    destinations = {}
    for src, dst, _ in tasks:
        source_key = src.resolve()
        destination_key = dst.resolve()
        if source_key == destination_key:
            print(
                f"Error: Output would overwrite the input file: {src}",
                file=sys.stderr,
            )
            return 1
        if destination_key in destinations:
            print(
                f"Error: Multiple inputs would overwrite '{dst}': "
                f"{destinations[destination_key]} and {src}",
                file=sys.stderr,
            )
            return 1
        destinations[destination_key] = src

    print(f"\nProcessing {len(tasks)} file(s) -> Format: {target_format}...")
    success_count = 0
    fail_count = 0

    for idx, (src, dst, cfg) in enumerate(tasks, 1):
        res: ConversionResult = engine.convert_single(src, dst, cfg)
        if res.success:
            success_count += 1
            size_kb_in = res.input_size_bytes / 1024.0
            size_kb_out = res.output_size_bytes / 1024.0
            print(f"[{idx}/{len(tasks)}] OK: {src.name} -> {Path(res.output_path).name} ({size_kb_in:.1f}KB -> {size_kb_out:.1f}KB, {res.duration_seconds*1000:.1f}ms)")
        else:
            fail_count += 1
            print(f"[{idx}/{len(tasks)}] FAILED: {src.name} - {res.error_message}", file=sys.stderr)

    print(f"\nCompleted: {success_count} succeeded, {fail_count} failed.")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
