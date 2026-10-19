import cv2
import numpy as np
from numpy.typing import NDArray

from .registry import ModelConfig


def preprocess(
    rgb: NDArray[np.uint8], config: ModelConfig
) -> NDArray[np.float32] | NDArray[np.float16]:
    x = cv2.resize(rgb, config.input_size, interpolation=cv2.INTER_LINEAR).astype(np.float32)
    divisor = max(float(np.max(x)), 1.0) if config.normalize_max else 255.0
    # Reuse the resized float buffer for normalization. The registered input
    # dimensions/normalization and resulting numerical values are unchanged.
    x /= divisor
    x -= np.asarray(config.mean, dtype=np.float32)
    x /= np.asarray(config.std, dtype=np.float32)
    return np.ascontiguousarray(
        x.transpose(2, 0, 1)[None],
        dtype=np.float16 if config.precision == "fp16" else np.float32,
    )
