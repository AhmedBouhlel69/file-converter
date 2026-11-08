"""Offline background removal with lazy model loading and protected outputs.

Importing this module does not import ONNX/OpenCV, hash a model, or create a
session. Use one service per worker to reuse its CPU inference session.
"""

from __future__ import annotations

import importlib
import logging
import math
import os
import shutil
import sys
import tempfile
import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping

from PIL import Image, ImageColor

from .conversion.engine import ConversionResult

MODEL_PROFILES = ("fast", "balanced", "quality", "portrait")
# "auto" picks the best lightweight profile that is actually installed. The two
# BiRefNet profiles are never chosen automatically because they need >= 8 GiB free RAM.
MODEL_CHOICES = ("auto", *MODEL_PROFILES)
_AUTO_ORDER = ("balanced", "fast")
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
    # Recover true subject colours at soft edges so no halo of the old background
    # remains, and clear the colour data hidden under transparent pixels.
    clean_edges: bool = True
    # Average the prediction with its mirror image: slower (2x) but steadier edges.
    accurate: bool = False

    def __post_init__(self) -> None:
        if self.model not in MODEL_CHOICES:
            raise ValueError(f"Model must be one of: {', '.join(MODEL_CHOICES)}")
        object.__setattr__(self, "output_format", _output_format(self.output_format))
        if self.model_dir is not None:
            object.__setattr__(self, "model_dir", Path(self.model_dir).expanduser().resolve())
        if self.bg_color is not None:
            try:
                if not isinstance(self.bg_color, str) or len(ImageColor.getrgb(self.bg_color)) != 3:
                    raise ValueError()
            except (TypeError, ValueError):
                raise ValueError("Background color must be an RGB color, for example #ffffff") from None
        for name in ("crop", "two_pass", "save_mask", "keep_metadata", "clean_edges", "accurate"):
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


def _link_exclusive(temporary: Path, target: Path) -> None:
    """Publish ``temporary`` as ``target`` without ever replacing an existing file.

    A hard link is atomic. FAT/exFAT drives and some network or cloud-sync folders
    cannot create them, so those fall back to exclusive creation plus a copy.
    """
    try:
        os.link(temporary, target)
        return
    except FileExistsError:
        raise
    except OSError:
        pass
    with open(target, "xb") as destination:  # FileExistsError if someone else won the race
        try:
            with open(temporary, "rb") as source:
                shutil.copyfileobj(source, destination, 1024 * 1024)
        except BaseException:
            destination.close()
            target.unlink(missing_ok=True)
            raise


def _signature(path: Path) -> tuple[int, int, int, int]:
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


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
    default_dirs: Mapping[str | Path, str | Path] | None = None,
) -> list[BackgroundRemovalTask]:
    """Plan unique output pairs without writing anything or loading image pixels.

Existing inputs/outputs and other planned outputs are all reserved. Corrupt or
overlimit images are reported by ``process`` so other batch items can succeed.
``default_dirs`` maps a source to the folder used when no output folder is chosen
(pasted images have no meaningful folder of their own).
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
    fallback = {
        Path(key).expanduser().resolve(): Path(value).expanduser().resolve()
        for key, value in (default_dirs or {}).items()
    }
    reserved = {_key(p) for p in sources}
    tasks = []
    for source in sources:
        relative_parent = Path()
        if root is not None:
            try:
                relative_parent = source.relative_to(root).parent
            except ValueError:
                raise ValueError(f"Input is outside input_root: {source}") from None
        if destination is not None:
            parent = destination / relative_parent
        else:
            parent = fallback.get(source, source.parent)
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


def _cache_directory() -> Path | None:
    """The default bgremove model cache, without importing ONNX/OpenCV."""
    try:
        from platformdirs import user_cache_dir
    except ImportError:
        return None
    return Path(user_cache_dir("bgremove"))


def _profile_location(profile: str, model_dir: str | Path | None = None) -> Path | None:
    """Return the folder that contains this profile's file, or ``None`` if absent."""
    folder = resolve_model_directory(model_dir, profile)
    if folder is None:
        folder = _cache_directory()
    try:
        return folder if folder is not None and (folder / _MODEL_FILES[profile]).is_file() else None
    except OSError:
        return None


def installed_profiles(model_dir: str | Path | None = None) -> list[str]:
    """Profiles whose model file is present. Hashes are still verified lazily on use."""
    return [profile for profile in MODEL_PROFILES if _profile_location(profile, model_dir)]


def auto_candidates(model_dir: str | Path | None = None) -> list[str]:
    """Installed profiles that ``auto`` may use, best first."""
    present = set(installed_profiles(model_dir))
    return [profile for profile in _AUTO_ORDER if profile in present]


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
        # The profile actually in use; differs from the configured one for "auto".
        self.active_model: str | None = None

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
            if self.config.model == "auto":
                candidates = auto_candidates(self.config.model_dir)
                if not candidates:
                    raise RuntimeError(
                        "No background-removal model is installed. Install one with "
                        "'bgremove models pull balanced' (needs internet once) or choose a "
                        "model folder in the advanced settings."
                    )
            else:
                candidates = [self.config.model]
            failures: list[str] = []
            for profile in candidates:
                try:
                    remover = backend.Remover(
                        model=profile,
                        device="cpu",
                        model_dir=resolve_model_directory(self.config.model_dir, profile),
                        threads=2,
                    )
                    # Initialize once here so failed sessions are not retried for each file.
                    remover.warmup()
                except Exception as exc:
                    failures.append(f"{profile}: {exc}")
                    if len(candidates) == 1:
                        raise
                    continue
                self._backend, self._remover, self.active_model = backend, remover, profile
                return
            raise RuntimeError("; ".join(failures))
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
            refine_options = {"feather_sigma": self.config.feather, "edge_shift": self.config.edge_shift}
            if self.config.clean_edges:
                refine_options["decontaminate"] = True
            extra = {"tta": True} if self.config.accurate else {}
            removed = self._remover.remove(
                task.input_path,
                refinement=self._backend.RefineOptions(**refine_options),
                composition=self._backend.ComposeOptions(bg_color=self.config.bg_color, crop=self.config.crop, padding=self.config.padding),
                two_pass=self.config.two_pass,
                **extra,
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
        published: list[tuple[Path, tuple[int, int, int, int]]] = []
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
                # Exclusive creation, including race checks; never replaces a file.
                _link_exclusive(temporary, target)
                published.append((target, _signature(target)))
        except Exception:
            for target, signature in reversed(published):
                # Never remove a pre-existing or concurrently replaced file.
                try:
                    if _signature(target) == signature:
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
