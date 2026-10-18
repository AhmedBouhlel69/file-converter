import cv2
import numpy as np
from numpy.typing import NDArray

from .registry import ModelConfig


def preprocess(
    rgb: NDArray[np.uint8], config: ModelConfig
) -> NDArray[np.float32] | NDArray[np.float16]:
    x = cv2.resize(rgb, config.input_size, interpolation=cv2.INTER_LINEAR).astype(np.float32)
    divisor = max(float(np.max(x)), 1.0) if config.normalize_max else 255.0
    normalized = np.asarray(
        (x / divisor - np.array(config.mean, dtype=np.float32))
        / np.array(config.std, dtype=np.float32),
        dtype=np.float32,
    )
    result = np.ascontiguousarray(
        normalized.transpose(2, 0, 1)[None],
        dtype=np.float16 if config.precision == "fp16" else np.float32,
    )

    return result.astype(np.float16) if config.precision == "fp16" else result.astype(np.float32)
