"""Offline background removal with lazy model loading and protected outputs.

Importing this module does not import ONNX/OpenCV, hash a model, or create a
session. Use one service per worker to reuse its CPU inference session.
"""

from __future__ import annotations

import importlib
import logging
import math
import os
import sys
import tempfile
import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from PIL import Image, ImageColor

from .conversion.engine import ConversionResult

MODEL_PROFILES = ("fast", "balanced", "quality", "portrait")
_MODEL_FILES = {
    "fast": "u2netp.onnx",
    "balanced": "isnet-general-use.onnx",
    "quality": "birefnet-general.onnx",
    "portrait": "birefnet-portrait.onnx",
}
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".jpe", ".png", ".webp", ".bmp", ".dib", ".tif", ".tiff"})
OUTPUT_FORMATS = ("PNG", "WEBP")
MAX_BYTES = 25 * 1024 * 1024
MAX_PIXELS = 120_000_000
_SOURCE_FORMATS = {"JPEG", "PNG", "WEBP", "BMP", "TIFF"}
ProgressCallback = Callable[[int, int, ConversionResult], None]
logger = logging.getLogger(__name__)


def _output_format(value: str) -> str:
    if not isinstance(value, str) or value.upper() not in OUTPUT_FORMATS:
        raise ValueError("Background-removal output must be PNG or WEBP")
    return value.upper()


@dataclass(frozen=True)
class BackgroundRemovalConfig:
    model: str = "fast"
    model_dir: str | Path | None = None
    output_format: str = "PNG"
    bg_color: str | None = None
    crop: bool = False
    padding: int = 0
    feather: float = 0
    edge_shift: int = 0
    two_pass: bool = False
    save_mask: bool = False
    keep_metadata: bool = False

    def __post_init__(self) -> None:
        if self.model not in MODEL_PROFILES:
            raise ValueError(f"Model must be one of: {', '.join(MODEL_PROFILES)}")
        object.__setattr__(self, "output_format", _output_format(self.output_format))
        if self.model_dir is not None:
            object.__setattr__(self, "model_dir", Path(self.model_dir).expanduser().resolve())
        if self.bg_color is not None:
            try:
                if not isinstance(self.bg_color, str) or len(ImageColor.getrgb(self.bg_color)) != 3:
                    raise ValueError()
            except (TypeError, ValueError):
                raise ValueError("Background color must be an RGB color, for example #ffffff") from None
        for name in ("crop", "two_pass", "save_mask", "keep_metadata"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be a boolean")
        if type(self.padding) is not int or self.padding < 0:
            raise ValueError("Padding must be a nonnegative integer")
        if type(self.edge_shift) is not int or not -5 <= self.edge_shift <= 5:
            raise ValueError("Edge shift must be an integer from -5 to 5")
        if (
            isinstance(self.feather, bool)
            or not isinstance(self.feather, (int, float))
            or not math.isfinite(self.feather)
            or self.feather < 0
        ):
            raise ValueError("Feather must be a finite nonnegative number")


@dataclass(frozen=True)
class BackgroundRemovalTask:
    input_path: Path
    output_path: Path
    mask_path: Path | None = None

    def __post_init__(self) -> None:
        for name in ("input_path", "output_path", "mask_path"):
            value = getattr(self, name)
            if value is not None:
                path = Path(value).expanduser()
                object.__setattr__(self, name, path.resolve() if name == "input_path" else _absolute(path))


def _absolute(path: str | Path) -> Path:
    # Preserve a final symlink so an existing broken output symlink also counts
    # as occupied. Identity comparisons below still resolve symlink targets.
    return Path(os.path.abspath(Path(path).expanduser()))


def _key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def _occupied(path: Path, reserved: set[str]) -> bool:
    return _key(path) in reserved or os.path.lexists(path)


def _check_input_path(path: Path) -> None:
    if path.suffix.lower() not in IMAGE_EXTENSIONS:
        raise ValueError(f"Unsupported background-removal input: {path.name}. Use JPEG, PNG, WEBP, BMP or TIFF.")
    if not path.is_file():
        raise ValueError(f"Input file not found: {path}")


def plan_tasks(
    inputs: Iterable[str | Path],
    output_dir: str | Path | None = None,
    output_format: str = "PNG",
    *,
    explicit_output: str | Path | None = None,
    save_mask: bool = False,
    input_root: str | Path | None = None,
) -> list[BackgroundRemovalTask]:
    """Plan unique output pairs without writing anything or loading image pixels.

Existing inputs/outputs and other planned outputs are all reserved. Corrupt or
overlimit images are reported by ``process`` so other batch items can succeed.
    """
    fmt = _output_format(output_format)
    sources = list(dict.fromkeys(Path(p).expanduser().resolve() for p in inputs))
    for source in sources:
        _check_input_path(source)
    if explicit_output is not None and len(sources) != 1:
        raise ValueError("An explicit output requires exactly one input image")
    if explicit_output is not None and output_dir is not None:
        raise ValueError("Choose an output directory or an explicit output file")
    root = Path(input_root).expanduser().resolve() if input_root is not None else None
    destination = Path(output_dir).expanduser().resolve() if output_dir is not None else None
    reserved = {_key(p) for p in sources}
    tasks = []
    for source in sources:
        relative_parent = Path()
        if root is not None:
            try:
                relative_parent = source.relative_to(root).parent
            except ValueError:
                raise ValueError(f"Input is outside input_root: {source}") from None
        parent = destination / relative_parent if destination is not None else source.parent
        if explicit_output is not None:
            output = _absolute(explicit_output)
            if output.suffix.lower() != f".{fmt.lower()}":
                raise ValueError(f"Explicit output must have a .{fmt.lower()} extension")
            mask = output.with_name(f"{output.stem}_mask.png") if save_mask else None
            if any(_occupied(p, reserved) for p in (output, mask) if p is not None):
                raise ValueError("Explicit output or mask already exists or would overwrite an input")
        else:
            number = 1
            while True:
                suffix = "" if number == 1 else f"_{number}"
                output = parent / f"{source.stem}_nobg{suffix}.{fmt.lower()}"
                mask = output.with_name(f"{output.stem}_mask.png") if save_mask else None
                if not any(_occupied(p, reserved) for p in (output, mask) if p is not None):
                    break
                number += 1
        reserved.add(_key(output))
        if mask is not None:
            reserved.add(_key(mask))
        tasks.append(BackgroundRemovalTask(source, output, mask))
    return tasks


def resolve_model_directory(model_dir: str | Path | None = None, model: str = "fast") -> Path | None:
    """Find a local profile; ``None`` delegates to bgremove's cache.

An explicitly configured directory is authoritative. Automatic locations must
contain the selected profile so a bundle with only fast does not hide other
profiles installed in the user's model cache. Full verification stays lazy.
    """
    if model not in _MODEL_FILES:
        raise ValueError(f"Unknown background-removal model: {model}")
    explicit = model_dir if model_dir is not None else os.environ.get("BGREMOVE_MODEL_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve()
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle is not None:
        candidate = Path(bundle) / "background_models"
        if (candidate / _MODEL_FILES[model]).is_file():
            return candidate
    workspace = Path(__file__).resolve().parents[2] / "backgroundG" / "models"
    return workspace if (workspace / _MODEL_FILES[model]).is_file() else None


def _source_info(path: Path) -> tuple[str, tuple[int, int], int]:
    _check_input_path(path)
    size = path.stat().st_size
    if size > MAX_BYTES:
        raise ValueError("Input exceeds the background-removal limit of 25 MiB")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", Image.DecompressionBombWarning)
        with Image.open(path) as image:
            if image.format not in _SOURCE_FORMATS:
                raise ValueError("Unsupported image content. Use JPEG, PNG, WEBP, BMP or TIFF.")
            if image.width * image.height > MAX_PIXELS:
                raise ValueError("Input exceeds the background-removal limit of 120 megapixels")
            if getattr(image, "n_frames", 1) > 1:
                raise ValueError("Animated or multi-page images are not supported for background removal")
            return image.format, image.size, size


class BackgroundRemovalService:
    """Serial worker service. Missing dependency/model failures are cached."""

    def __init__(self, config: BackgroundRemovalConfig | None = None) -> None:
        self.config = config or BackgroundRemovalConfig()
        self._backend = None
        self._remover = None
        self._initialization_error: str | None = None

    def _initialize(self) -> None:
        if self._initialization_error is not None:
            raise RuntimeError(self._initialization_error)
        if self._remover is not None:
            return
        try:
            if sys.version_info < (3, 11):
                raise RuntimeError("Background removal requires Python 3.11 or newer")
            try:
                backend = importlib.import_module("bgremove")
            except (ImportError, OSError) as exc:
                raise RuntimeError(
                    "Background-removal dependencies are unavailable. From the app folder run "
                    "'python -m pip install -r image_converter/requirements-background.txt'. "
                    f"Details: {exc}"
                ) from exc
            remover = backend.Remover(
                model=self.config.model,
                device="cpu",
                model_dir=resolve_model_directory(self.config.model_dir, self.config.model),
                threads=2,
            )
            # Initialize once here so failed sessions are not retried for each file.
            remover.warmup()
            self._backend, self._remover = backend, remover
        except Exception as exc:
            self._initialization_error = f"Cannot initialize background removal ({self.config.model}): {exc}"
            raise RuntimeError(self._initialization_error) from exc

    def close(self) -> None:
        """Release idle model ownership after a job; active external users remain valid."""
        backend, self._backend = self._backend, None
        self._remover = None
        release = getattr(backend, "release_engine_cache", None)
        if release is not None:
            try:
                release()
            except Exception:
                logger.warning("Could not release the idle background model", exc_info=True)

    def _check_targets(self, task: BackgroundRemovalTask, protected: set[str]) -> None:
        if task.output_path.suffix.lower() != f".{self.config.output_format.lower()}":
            raise ValueError("Output extension does not match the selected PNG/WEBP format")
        if self.config.save_mask and task.mask_path is None:
            raise ValueError("Mask export requires a task planned with save_mask=True")
        if task.mask_path is not None and task.mask_path.suffix.lower() != ".png":
            raise ValueError("Mask output must be PNG")
        targets = [p for p in (task.output_path, task.mask_path) if p is not None]
        if len({_key(p) for p in targets}) != len(targets):
            raise ValueError("Output and mask paths must be different")
        for path in targets:
            if _key(path) in protected:
                raise ValueError(f"Output would overwrite an input: {path}")
            if os.path.lexists(path):
                raise FileExistsError(f"Output already exists: {path}")

    def process(self, task: BackgroundRemovalTask) -> ConversionResult:
        try:
            return self._process(task, {_key(task.input_path)}, None)
        finally:
            self.close()

    def _process(self, task: BackgroundRemovalTask, protected: set[str], cancel_check) -> ConversionResult:
        started = time.perf_counter()
        result = ConversionResult(False, str(task.input_path), str(task.output_path), output_format=self.config.output_format)
        try:
            self._check_targets(task, protected)
            result.input_format, result.input_dimensions, result.input_size_bytes = _source_info(task.input_path)
            self._initialize()
            if cancel_check is not None and cancel_check():
                raise RuntimeError("Background removal cancelled")
            removed = self._remover.remove(
                task.input_path,
                refinement=self._backend.RefineOptions(feather_sigma=self.config.feather, edge_shift=self.config.edge_shift),
                composition=self._backend.ComposeOptions(bg_color=self.config.bg_color, crop=self.config.crop, padding=self.config.padding),
                two_pass=self.config.two_pass,
            )
            result.output_dimensions = removed.rgba.size
            self._publish(removed, task, cancel_check)
            result.output_size_bytes = task.output_path.stat().st_size
            result.success = True
        except Exception as exc:
            result.error_message = str(exc) or type(exc).__name__
        result.duration_seconds = time.perf_counter() - started
        return result

    def _publish(self, removed, task: BackgroundRemovalTask, cancel_check) -> None:
        staged: list[tuple[Path, Path]] = []
        published: list[tuple[Path, Path]] = []
        try:
            if cancel_check is not None and cancel_check():
                raise RuntimeError("Background removal cancelled; no outputs were saved")
            for target, is_mask in ((task.output_path, False), (task.mask_path, True)):
                if target is None:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                fd, name = tempfile.mkstemp(prefix=".bgremove-", suffix=target.suffix, dir=target.parent)
                os.close(fd)
                temporary = Path(name)
                staged.append((temporary, target))
                if is_mask:
                    removed.save_mask(temporary, overwrite=True)
                else:
                    removed.save(temporary, overwrite=True, keep_metadata=self.config.keep_metadata)
            if cancel_check is not None and cancel_check():
                raise RuntimeError("Background removal cancelled; no outputs were saved")
            for temporary, target in staged:
                # Atomic publication with exclusive creation, including race checks.
                os.link(temporary, target)
                published.append((temporary, target))
        except Exception:
            for temporary, target in reversed(published):
                # Never remove a pre-existing or concurrently replaced file.
                try:
                    if os.path.samefile(temporary, target):
                        target.unlink()
                except FileNotFoundError:
                    pass
            raise
        finally:
            for temporary, _target in staged:
                temporary.unlink(missing_ok=True)

    def run_batch(
        self,
        tasks: Iterable[BackgroundRemovalTask],
        progress_callback: ProgressCallback | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> list[ConversionResult]:
        items = list(tasks)
        protected = {_key(task.input_path) for task in items}
        results = []
        try:
            for task in items:
                if cancel_check is not None and cancel_check():
                    break
                result = self._process(task, protected, cancel_check)
                results.append(result)
                if progress_callback is not None:
                    progress_callback(len(results), len(items), result)
            return results
        finally:
            self.close()
