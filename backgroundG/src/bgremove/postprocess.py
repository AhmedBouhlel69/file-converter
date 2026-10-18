import cv2
import numpy as np
from numpy.typing import NDArray

from .registry import ModelConfig


def postprocess(
    raw: NDArray[np.float32] | NDArray[np.float16], size: tuple[int, int], config: ModelConfig
) -> NDArray[np.float32]:
    mask = np.asarray(raw, dtype=np.float32)
    if mask.ndim == 4 and mask.shape[:2] == (1, 1):
        mask = mask[0, 0]
    elif mask.ndim == 3 and mask.shape[0] == 1:
        mask = mask[0]
    if mask.ndim != 2 or not np.isfinite(mask).all():
        raise ValueError("Model must return a finite single-channel mask")
    if config.output_activation == "sigmoid":
        mask = 1 / (1 + np.exp(-np.clip(mask, -50, 50)))
    if config.minmax:
        low, high = float(np.min(mask)), float(np.max(mask))
        mask = (mask - low) / (high - low) if high > low else np.zeros_like(mask)
    return np.asarray(
        np.clip(cv2.resize(mask, size, interpolation=cv2.INTER_CUBIC), 0, 1), dtype=np.float32
    )
