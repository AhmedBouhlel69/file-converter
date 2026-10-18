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


def _run_background_removal(args: argparse.Namespace, in_path: Path) -> int:
    """Route the opt-in local image tool without loading ONNX for other CLI modes."""
    from image_converter.core.background_removal import (
        BackgroundRemovalConfig,
        BackgroundRemovalService,
        IMAGE_EXTENSIONS,
        plan_tasks,
    )
    from image_converter.core.logging_config import get_logger

    incompatible = (
        args.clean_metadata or args.inspect_metadata or args.ocr or
        args.resize_percent is not None or args.width is not None or
        args.height is not None or args.no_keep_ratio or args.no_auto_orient or
        args.sheet_name is not None or args.password is not None or
        args.workers is not None or args.quality != 90 or args.dpi != 150
    )
    if incompatible:
        print("Error: Background removal cannot be combined with conversion, resize, OCR, metadata inspection/cleaning, or worker options.", file=sys.stderr)
        return 1
    if args.bg_color is not None:
        print("Error: Use --bg-fill-color with --remove-background; its default output is transparent.", file=sys.stderr)
        return 1
    if args.keep_metadata and (args.strip_metadata or args.no_metadata):
        print("Error: --keep-metadata cannot be combined with --strip-metadata or --no-metadata.", file=sys.stderr)
        return 1

    out_arg = Path(args.output_path) if args.output_path else None
    explicit_output = out_arg if out_arg and not out_arg.is_dir() and out_arg.suffix else None
    if explicit_output is not None and in_path.is_dir():
        print("Error: A directory input requires an output directory; use a single image for an explicit output filename.", file=sys.stderr)
        return 1
    excluded_output_root = None
    if in_path.is_dir() and out_arg is not None and explicit_output is None:
        source_root = in_path.resolve()
        output_root = out_arg.resolve()
        if output_root != source_root and output_root.is_relative_to(source_root):
            excluded_output_root = output_root

    supported = {extension.lower() for extension in IMAGE_EXTENSIONS}
    if in_path.is_dir():
        iterator = in_path.rglob("*") if args.recursive else in_path.glob("*")
        inputs = sorted(
            path for path in iterator
            if path.is_file() and path.suffix.lower() in supported
            and (excluded_output_root is None or not path.resolve().is_relative_to(excluded_output_root))
        )
    else:
        inputs = [in_path] if in_path.suffix.lower() in supported else []
    if not inputs:
        print("Error: No background-removal images found. Supported inputs: JPG, JPEG, PNG, WebP, BMP, TIF, TIFF.", file=sys.stderr)
        return 1

    target_format = (args.target_format or (explicit_output.suffix[1:] if explicit_output else "PNG")).upper()
    if target_format not in {"PNG", "WEBP"}:
        print("Error: Background removal supports PNG or lossless WEBP output only.", file=sys.stderr)
        return 1
    if explicit_output and explicit_output.suffix.lower() != f".{target_format.lower()}":
        print("Error: Output filename extension must match the background-removal format (PNG or WEBP).", file=sys.stderr)
        return 1

    try:
        config = BackgroundRemovalConfig(
            model=args.bg_model or "fast",
            model_dir=Path(args.bg_model_dir) if args.bg_model_dir else None,
            output_format=target_format,
            bg_color=("#{:02x}{:02x}{:02x}".format(*args.bg_fill_color) if args.bg_fill_color is not None else None),
            crop=args.bg_crop,
            padding=args.bg_padding or 0,
            feather=args.bg_feather or 0,
            edge_shift=args.bg_edge_shift or 0,
            two_pass=args.bg_two_pass,
            save_mask=args.save_mask,
            keep_metadata=args.keep_metadata,
        )
        tasks = plan_tasks(
            inputs,
            output_dir=None if explicit_output else out_arg,
            output_format=target_format,
            explicit_output=explicit_output,
            save_mask=args.save_mask,
            input_root=in_path if in_path.is_dir() else None,
        )
        service = BackgroundRemovalService(config)
        print(f"\nRemoving backgrounds from {len(tasks)} image(s) -> {target_format}, model: {config.model}, CPU...")

        def on_progress(completed: int, total: int, result: ConversionResult):
            if result.success:
                print(f"[{completed}/{total}] OK: {Path(result.input_path).name} -> {result.output_path}")
            else:
                print(f"[{completed}/{total}] FAILED: {Path(result.input_path).name} - {result.error_message}", file=sys.stderr)

        results = service.run_batch(tasks, progress_callback=on_progress)
    except KeyboardInterrupt:
        print("\nBackground removal interrupted.", file=sys.stderr)
        return 130
    except (ImportError, OSError, ValueError, RuntimeError) as error:
        get_logger("cli").error("Background removal failed: %s", error)
        print(f"Error: {error}", file=sys.stderr)
        return 1

    successes = sum(result.success for result in results)
    failures = len(results) - successes
    print(f"\nCompleted: {successes} succeeded, {failures} failed.")
    return 0 if failures == 0 else 1


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
        "positional_input",
        nargs="?",
        default=None,
        help="Optional input file or directory path (shorthand for -i).",
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
        help="Strip metadata from converted files (alias for --strip-metadata).",
    )
    parser.add_argument(
        "--strip-metadata",
        dest="strip_metadata",
        action="store_true",
        default=False,
        help="Strip all personal, tracking, and device metadata (EXIF, author, GPS, timestamps) from converted files.",
    )
    parser.add_argument(
        "--clean-metadata",
        action="store_true",
        default=False,
        help="Directly sanitize and delete all metadata from input files without changing format.",
    )
    parser.add_argument(
        "--inspect-metadata",
        action="store_true",
        default=False,
        help="Inspect and display detailed metadata found in the input file.",
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
        default=None,
        help="Solid background color for transparent images when converting to JPG/BMP (hex '#ffffff' or '255,255,255').",
    )
    background = parser.add_argument_group("Local background removal (optional Python 3.11+ module)")
    background.add_argument("--remove-background", action="store_true", help="Remove image backgrounds locally on CPU; transparent PNG by default.")
    background.add_argument("--bg-model", choices=("fast", "balanced", "quality", "portrait"), default=None, help="Installed segmentation model (default: fast); never downloads automatically.")
    background.add_argument("--bg-model-dir", default=None, help="Directory containing verified local ONNX model files.")
    background.add_argument("--save-mask", action="store_true", help="Also export the full-size grayscale mask as PNG.")
    background.add_argument("--bg-feather", type=float, default=None, help="Mask feather radius in pixels (default: 0).")
    background.add_argument("--bg-edge-shift", type=int, default=None, help="Expand (+) or contract (-) mask edges in pixels (default: 0).")
    background.add_argument("--bg-two-pass", action="store_true", help="Refine the detected subject using a second inference pass.")
    background.add_argument("--bg-crop", action="store_true", help="Crop output around the detected foreground.")
    background.add_argument("--bg-padding", type=int, default=None, help="Padding around cropped foreground in pixels (default: 0).")
    background.add_argument("--bg-fill-color", type=parse_color, default=None, help="Optional solid fill for removed pixels; omit to keep transparency.")
    background.add_argument("--keep-metadata", action="store_true", help="Preserve image metadata in background-removal output (default: strip EXIF/GPS).")
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
        "--password",
        type=str,
        default=None,
        help="Password for encrypted PDF or Word documents.",
    )
    parser.add_argument(
        "--ocr",
        action="store_true",
        help="Enable OCR text extraction fallback for scanned PDFs and images.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Number of concurrent worker threads for batch processing (default: auto).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable detailed debug logging to console and log file.",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Path to write execution logs.",
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
        except Exception as e:
            import logging
            logging.getLogger("cli").warning(f"Failed to reconfigure stdout/stderr encoding: {e}", exc_info=True)

    args = parser.parse_args(argv)

    from image_converter.core.logging_config import setup_logger, get_logger
    from image_converter.core.ocr_engine import get_ocr_status_message

    setup_logger(verbose=args.verbose, log_file=args.log_file)
    logger = get_logger("cli")

    background_options_used = any((
        args.bg_model is not None, args.bg_model_dir is not None, args.save_mask,
        args.bg_feather is not None, args.bg_edge_shift is not None, args.bg_two_pass,
        args.bg_crop, args.bg_padding is not None, args.bg_fill_color is not None,
        args.keep_metadata,
    ))
    if background_options_used and not args.remove_background:
        print("Error: Background-removal options require --remove-background.", file=sys.stderr)
        return 1

    if args.list_formats:
        print("\n=== Universal File Converter Formats ===")
        print("\n[Images]")
        print("  Inputs:  .jpg, .jpeg, .png, .heic, .heif, .webp, .bmp, .tiff, .gif, .ico, .ppm, .tga, .eps")
        print("  Outputs: JPG, PNG, WEBP, HEIC, BMP, TIFF, GIF, ICO, PDF, TXT (OCR), DOCX (OCR)")
        print("\n[Documents]")
        print("  Inputs:  .pdf, .docx, .doc")
        print("  Outputs: PDF, DOCX, TXT, HTML, PNG, JPG, WEBP, CSV, XLSX, PPTX, ODT, RTF")
        print("\n[Spreadsheets & Data]")
        print("  Inputs:  .csv, .xlsx, .xls")
        print("  Outputs: XLSX, CSV, PDF, JSON, HTML, TXT")
        print("\n[Presentations & Rich Documents]")
        print("  Inputs:  .pptx, .odt, .rtf, .txt")
        print("  Outputs: PPTX, ODT, RTF, PDF, DOCX, TXT, HTML, PNG, JPG")
        print(f"\n[OCR Status]")
        print(f"  {get_ocr_status_message()}")
        print("\nAll Input Extensions:")
        print("  " + ", ".join(get_supported_input_extensions()))
        print("All Output Formats:")
        print("  " + ", ".join(get_supported_output_formats()) + "\n")
        print("[Background Removal]")
        print("  --remove-background: JPG/JPEG, PNG, WEBP, BMP, TIF/TIFF -> transparent PNG or lossless WEBP")
        print("  Optional Python 3.11+ local module and a verified model are required. Default: fast, CPU.\n")
        return 0

    input_target = args.input_path or args.positional_input
    if not input_target:
        parser.print_help()
        return 1

    in_path = Path(input_target)
    if not in_path.exists():
        print(f"Error: Input path does not exist: {in_path}", file=sys.stderr)
        return 1

    if args.remove_background:
        return _run_background_removal(args, in_path)

    files_to_process = collect_convertible_files(in_path, recursive=args.recursive)
    if not files_to_process:
        print(f"No supported files found in {in_path}", file=sys.stderr)
        return 1

    engine = UniversalConverterEngine()

    # Metadata inspection mode
    if getattr(args, "inspect_metadata", False):
        from image_converter.core.metadata_engine import get_detailed_metadata
        info = get_detailed_metadata(in_path, password=args.password)
        print(f"\n=== Metadata Inspection: {in_path.name} ===")
        print(f"File Size: {info['file_size']} bytes | Format: {info['extension']}")
        print(f"Has Metadata: {'Yes' if info['has_metadata'] else 'No'} ({info['fields_count']} tag(s))")
        if info["warnings"]:
            for w in info["warnings"]:
                print(f"  ⚠️ Warning: {w}")
        if info["fields"]:
            print("\nMetadata Fields Found:")
            for k, v in info["fields"].items():
                print(f"  • {k}: {v}")
        else:
            print("No personal or tracking metadata tags found.")
        print()
        return 0

    # Determine default target format
    target_format = args.target_format
    is_clean_mode = getattr(args, "clean_metadata", False)
    strip_meta = getattr(args, "strip_metadata", False) or getattr(args, "no_metadata", False) or is_clean_mode

    if is_clean_mode:
        target_format = "STRIP_METADATA"
    elif not target_format:
        if args.output_path and Path(args.output_path).suffix:
            ext = Path(args.output_path).suffix.lstrip(".").upper()
            target_format = "JPG" if ext == "JPEG" else ext
        else:
            print("Error: Target format must be specified with -f/--format (e.g. -f PNG, -f PDF, -f XLSX) or use --clean-metadata.", file=sys.stderr)
            return 1

    target_format = target_format.upper()
    if target_format == "JPEG":
        target_format = "JPG"

    if target_format not in ("STRIP_METADATA", "CLEAN") and not engine.is_format_supported(target_format):
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
        preserve_metadata=not strip_meta,
        strip_metadata=strip_meta,
        auto_orient=not args.no_auto_orient,
        resize_mode=resize_mode,
        resize_percent=args.resize_percent or 100.0,
        custom_width=args.width,
        custom_height=args.height,
        keep_aspect_ratio=not args.no_keep_ratio,
        background_color=args.bg_color or (255, 255, 255),
        dpi=args.dpi,
        sheet_name=args.sheet_name,
        password=args.password,
        enable_ocr=args.ocr,
        max_workers=args.workers,
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
            if target_format in ("STRIP_METADATA", "CLEAN"):
                dest_name = f"{f.stem}_clean{f.suffix}" if out_dir.resolve() == f.parent.resolve() else f"{f.name}"
            else:
                dest_name = f"{f.stem}{ext}"
                if out_dir.resolve() == f.parent.resolve() and dest_name == f.name:
                    suffix_tag = "_clean" if strip_meta else "_converted"
                    dest_name = f"{f.stem}{suffix_tag}{ext}"
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

    def on_progress(completed: int, total: int, res: ConversionResult):
        nonlocal success_count, fail_count
        if res.success:
            success_count += 1
            size_kb_in = res.input_size_bytes / 1024.0
            size_kb_out = res.output_size_bytes / 1024.0
            warn_suffix = f" [WARNING: {res.error_message}]" if res.error_message else ""
            print(f"[{completed}/{total}] OK: {Path(res.input_path).name} -> {Path(res.output_path).name} ({size_kb_in:.1f}KB -> {size_kb_out:.1f}KB, {res.duration_seconds*1000:.1f}ms){warn_suffix}")
        else:
            fail_count += 1
            print(f"[{completed}/{total}] FAILED: {Path(res.input_path).name} - {res.error_message}", file=sys.stderr)

    engine.convert_batch(tasks, progress_callback=on_progress, max_workers=args.workers)

    print(f"\nCompleted: {success_count} succeeded, {fail_count} failed.")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
