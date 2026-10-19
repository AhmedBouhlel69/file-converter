import os
import re
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from multiprocessing import get_context
from pathlib import Path
from typing import Any

from .compose import ComposeOptions
from .loader import InputError
from .refine import RefineOptions
from .remover import Remover
from .resource_policy import DEFAULT_CPU_THREADS

_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".heic", ".heif"}


@dataclass(frozen=True)
class BatchItem:
    source: Path
    image: Path | None
    mask: Path | None
    output_root: Path | None = None


@dataclass
class BatchResult:
    source: str
    status: str
    error: str | None = None
    input_error: bool = False


@dataclass(frozen=True)
class BatchOptions:
    refinement: RefineOptions = field(default_factory=RefineOptions)
    composition: ComposeOptions = field(default_factory=ComposeOptions)
    two_pass: bool = False
    overwrite: bool = False
    keep_metadata: bool = False


def _safe_stem(stem: str) -> str:
    name = re.sub(r"[^\w. -]", "_", stem).strip(". ") or "image"
    # Windows reserved names remain reserved even with an extension.
    if name.split(".")[0].upper() in {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *[f"COM{i}" for i in range(1, 10)],
        *[f"LPT{i}" for i in range(1, 10)],
    }:
        name = "_" + name
    return name


def plan_batch(
    inputs: list[Path],
    output: Path,
    *,
    recursive: bool = False,
    format: str = "png",
    save_mask: bool = False,
    mask_only: bool = False,
    skip_existing: bool = False,
    overwrite: bool = False,
) -> list[BatchItem]:
    if format not in {"png", "webp"}:
        raise ValueError("Format must be png or webp")
    if skip_existing and overwrite:
        raise ValueError("--skip-existing and --overwrite are mutually exclusive")
    root = output.resolve()
    if output.exists() and not output.is_dir():
        raise ValueError(f"Output directory is not a folder: {output}")
    sources: list[tuple[Path, Path]] = []
    for source in inputs:
        if source.is_dir():
            directory = source.resolve()
            if directory == root:
                raise ValueError("Input and output folders must differ")
            exclude_output = root.is_relative_to(directory)
            iterator = source.rglob("*") if recursive else source.glob("*")
            for path in sorted(iterator):
                if path.is_file() and path.suffix.lower() in _EXTENSIONS:
                    resolved = path.resolve()
                    if not resolved.is_relative_to(directory):
                        raise ValueError(f"Input symlink escapes its folder: {path}")
                    if exclude_output and resolved.is_relative_to(root):
                        continue
                    sources.append((path, path.relative_to(source).parent))
        else:
            sources.append((source, Path()))
    if not sources:
        raise ValueError("No supported images found")
    protected_sources = frozenset(source.resolve() for source, _ in sources)
    seen_sources: set[Path] = set()
    seen_targets: set[Path] = set()
    items: list[BatchItem] = []
    for source, relative in sources:
        resolved = source.resolve()
        if resolved in seen_sources:
            continue
        seen_sources.add(resolved)
        prefix = root / relative / _safe_stem(source.stem)
        image = prefix.with_name(prefix.name + "_nobg." + format) if not mask_only else None
        mask = prefix.with_name(prefix.name + "_mask.png") if save_mask or mask_only else None
        for target in (image, mask):
            if target is None:
                continue
            real_target = _validate_target(target, root, protected_sources)
            if real_target in seen_targets:
                raise ValueError(f"Output name collision: {target}. Use separate output folders.")
            seen_targets.add(real_target)
            if target.exists() and not (overwrite or skip_existing):
                raise ValueError(f"Output exists: {target}; use --skip-existing or --overwrite")
        if skip_existing:
            image = None if image is not None and image.exists() else image
            mask = None if mask is not None and mask.exists() else mask
        items.append(BatchItem(source, image, mask, root))
    return items


def _validate_target(
    target: Path, root: Path | None, sources: frozenset[Path], source: Path | None = None
) -> Path:
    """Check the current filesystem state, including links changed after planning."""
    resolved = target.resolve()
    # The planned root is already canonical. Resolving it again would silently
    # accept a directory swapped for a link to somewhere outside the output tree.
    if root is not None and not resolved.is_relative_to(root.absolute()):
        raise ValueError(f"Output path escapes output directory: {target}")
    if resolved in sources or (source is not None and resolved == source.resolve()):
        raise ValueError(f"An output would overwrite an input: {target}")
    if target.is_symlink():
        raise ValueError(f"Output symlinks are not supported: {target}")
    if target.exists() and not target.is_file():
        raise ValueError(f"Output is not a regular file: {target}")
    return resolved


def _process(
    remover: Remover,
    item: BatchItem,
    options: BatchOptions,
    protected_sources: frozenset[Path] = frozenset(),
) -> BatchResult:
    if item.image is None and item.mask is None:
        return BatchResult(str(item.source), "skipped")
    try:
        for target in (item.image, item.mask):
            if target is not None:
                _validate_target(target, item.output_root, protected_sources, item.source)
        result = remover.remove(
            item.source,
            refinement=options.refinement,
            composition=options.composition,
            two_pass=options.two_pass,
        )
        if item.image is not None:
            _validate_target(item.image, item.output_root, protected_sources, item.source)
            result.save(
                item.image, overwrite=options.overwrite, keep_metadata=options.keep_metadata
            )
        if item.mask is not None:
            _validate_target(item.mask, item.output_root, protected_sources, item.source)
            result.save_mask(item.mask, overwrite=options.overwrite)
        return BatchResult(str(item.source), "saved")
    except (ValueError, OSError, RuntimeError) as exc:
        return BatchResult(str(item.source), "failed", str(exc), isinstance(exc, InputError))


_WORKER: Remover | None = None
_WORKER_OPTIONS = BatchOptions()
_WORKER_SOURCES: frozenset[Path] = frozenset()


def _initialize(config: dict[str, Any], options: BatchOptions, sources: frozenset[Path]) -> None:
    global _WORKER, _WORKER_OPTIONS, _WORKER_SOURCES
    _WORKER = Remover(**config)
    _WORKER_OPTIONS = options
    _WORKER_SOURCES = sources


def _work(item: BatchItem) -> BatchResult:
    if _WORKER is None:
        raise RuntimeError("Batch worker was not initialized")
    return _process(_WORKER, item, _WORKER_OPTIONS, _WORKER_SOURCES)


def physical_cores() -> int:
    try:
        import psutil

        return max(1, int(psutil.cpu_count(logical=False) or os.cpu_count() or 1))
    except ImportError:
        return max(1, (os.cpu_count() or 2) // 2)


def run_batch(
    items: list[BatchItem], config: dict[str, Any], options: BatchOptions, *, jobs: int = 1
) -> list[BatchResult]:
    cores = physical_cores()
    if isinstance(jobs, bool) or not isinstance(jobs, int) or jobs < 1 or jobs > cores:
        raise ValueError(f"Jobs must be between 1 and {cores}")
    config = dict(config)
    requested_threads = config.get("threads", 0)
    if (
        isinstance(requested_threads, bool)
        or not isinstance(requested_threads, int)
        or requested_threads < 0
    ):
        raise ValueError("Threads must be a nonnegative integer")
    threads = requested_threads or min(DEFAULT_CPU_THREADS, max(1, cores // jobs))
    if threads * jobs > cores:
        raise ValueError("Jobs times threads must not exceed physical CPU cores")
    config["threads"] = threads
    sources = frozenset(item.source.resolve() for item in items)
    targets: set[Path] = set()
    for item in items:
        for target in (item.image, item.mask):
            if target is not None:
                resolved = _validate_target(target, item.output_root, sources)
                if resolved in targets:
                    raise ValueError(f"Output name collision: {target}")
                targets.add(resolved)
    if not items or all(item.image is None and item.mask is None for item in items):
        return [BatchResult(str(item.source), "skipped") for item in items]
    remover = Remover(**config)
    if jobs > 1:
        if config.get("device", "auto") != "cpu":
            # Use one process for GPU so its session lock controls all work.
            if remover.warmup().provider != "CPUExecutionProvider":
                raise ValueError("Use --jobs 1 for GPU processing; parallel workers require CPU")
            config["device"] = "cpu"
        with ProcessPoolExecutor(
            max_workers=jobs,
            initializer=_initialize,
            initargs=(config, options, sources),
            # A parent may have warmed a CUDA session before CPU fallback.
            # Spawn prevents its runtime state and locks being inherited by fork.
            mp_context=get_context("spawn"),
        ) as pool:
            return list(pool.map(_work, items))
    return [_process(remover, item, options, sources) for item in items]
