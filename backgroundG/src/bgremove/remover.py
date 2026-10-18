import logging
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from .compose import ComposeOptions, compose, subject_box
from .engine import Engine, get_engine
from .export import export
from .loader import load
from .postprocess import postprocess
from .preprocess import preprocess
from .refine import RefineOptions, refine
from .registry import read_registry, verify_model


@dataclass
class Result:
    rgba: Image.Image
    mask: NDArray[np.float32]
    timings: dict[str, float]
    icc: bytes | None
    exif: bytes | None
    provider: str

    def save(
        self, path: str | Path, *, overwrite: bool = False, keep_metadata: bool = False
    ) -> None:
        start = perf_counter()
        export(
            self.rgba,
            path,
            icc=self.icc,
            exif=self.exif if keep_metadata else None,
            overwrite=overwrite,
        )
        self.timings["export"] = perf_counter() - start
        logging.getLogger(__name__).debug("export %.6fs", self.timings["export"])

    def save_mask(self, path: str | Path, *, overwrite: bool = False) -> None:
        export(
            Image.fromarray(np.rint(self.mask * 255).astype(np.uint8)), path, overwrite=overwrite
        )


class Remover:
    def __init__(
        self,
        model: str = "balanced",
        device: str = "auto",
        *,
        registry: Path | None = None,
        model_dir: Path | None = None,
        strict_device: bool = False,
        allow_noncommercial: bool = False,
        threads: int = 0,
    ) -> None:
        if device not in {"auto", "cpu", "cuda", "coreml", "dml"}:
            raise ValueError(f"Unknown device: {device}")
        if isinstance(threads, bool) or not isinstance(threads, int) or threads < 0:
            raise ValueError("Threads must be a nonnegative integer")
        configs = read_registry(registry)
        if model not in configs:
            raise ValueError(f"Unknown model profile: {model}")
        self.config = configs[model]
        self.path = verify_model(self.config, model_dir, allow_noncommercial)
        self.device, self.strict, self.threads = device, strict_device, threads

    def warmup(self) -> Engine:
        return get_engine(self.path, self.config, self.device, self.strict, self.threads)

    def _predict(
        self, engine: Engine, rgb: NDArray[np.uint8], timings: dict[str, float]
    ) -> NDArray[np.float32]:
        start = perf_counter()
        tensor = preprocess(rgb, self.config)
        timings["preprocess"] = timings.get("preprocess", 0) + perf_counter() - start
        start = perf_counter()
        raw = engine.run(tensor)
        timings["inference"] = timings.get("inference", 0) + perf_counter() - start
        start = perf_counter()
        mask = postprocess(raw, (rgb.shape[1], rgb.shape[0]), self.config)
        timings["postprocess"] = timings.get("postprocess", 0) + perf_counter() - start
        return mask

    def remove(
        self,
        source: str | Path | bytes | Image.Image,
        *,
        refinement: RefineOptions | None = None,
        composition: ComposeOptions | None = None,
        two_pass: bool = False,
        matting: bool | None = None,
    ) -> Result:
        from dataclasses import replace

        options = refinement or RefineOptions()
        if matting is not None:
            options = replace(options, matting=matting)
        composition = composition or ComposeOptions()
        timings: dict[str, float] = {}
        start = perf_counter()
        loaded = load(source)
        background = load(composition.bg_image).rgb if composition.bg_image else None
        timings["load"] = perf_counter() - start
        start = perf_counter()
        engine = self.warmup()
        timings["session"] = perf_counter() - start
        mask = self._predict(engine, loaded.rgb, timings)
        if two_pass:
            box = subject_box(mask, margin=0.1)
            if box is not None and box != (0, 0, loaded.rgb.shape[1], loaded.rgb.shape[0]):
                left, top, right, bottom = box
                cropped = self._predict(engine, loaded.rgb[top:bottom, left:right], timings)
                mask = np.zeros_like(mask)
                mask[top:bottom, left:right] = cropped
        start = perf_counter()
        mask, foreground = refine(loaded.rgb, mask, options)
        timings["refine"] = perf_counter() - start
        start = perf_counter()
        rgba = compose(
            foreground if foreground is not None else loaded.rgb,
            mask,
            composition,
            original=loaded.rgb,
            background=background,
        )
        timings["compose"] = perf_counter() - start
        for stage, duration in timings.items():
            logging.getLogger(__name__).debug("%s %.6fs", stage, duration)
        # Keep the profile available to callers using Pillow directly as well.
        if loaded.icc:
            rgba.info["icc_profile"] = loaded.icc
        return Result(rgba, mask, timings, loaded.icc, loaded.exif, engine.provider)
