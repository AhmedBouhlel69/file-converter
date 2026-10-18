import math
from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageColor

from .config import MAX_PIXELS


@dataclass(frozen=True)
class ComposeOptions:
    bg_color: str | None = None
    bg_image: str | None = None
    bg_blur: float | None = None
    shadow: bool = False
    crop: bool = False
    padding: int = 0
    aspect: float | None = None

    def __post_init__(self) -> None:
        if sum(x is not None for x in (self.bg_color, self.bg_image, self.bg_blur)) > 1:
            raise ValueError("Choose only one background option")
        if self.bg_color is not None and len(ImageColor.getrgb(self.bg_color)) != 3:
            raise ValueError("Background colour must be RGB")
        if isinstance(self.padding, bool) or not isinstance(self.padding, int) or self.padding < 0:
            raise ValueError("Padding must be nonnegative")
        if self.bg_blur is not None and (not math.isfinite(self.bg_blur) or self.bg_blur <= 0):
            raise ValueError("Background blur must be positive")
        if self.aspect is not None and (not math.isfinite(self.aspect) or self.aspect <= 0):
            raise ValueError("Canvas aspect must be positive")


def subject_box(
    mask: NDArray[np.float32], padding: int = 0, margin: float = 0.0
) -> tuple[int, int, int, int] | None:
    active = mask > 0.05
    rows = np.flatnonzero(np.any(active, axis=1))
    columns = np.flatnonzero(np.any(active, axis=0))
    if not len(rows):
        return None
    left, top = int(np.min(columns)), int(np.min(rows))
    right, bottom = int(np.max(columns)) + 1, int(np.max(rows)) + 1
    dx = padding + math.ceil((right - left) * margin)
    dy = padding + math.ceil((bottom - top) * margin)
    return (
        max(0, left - dx),
        max(0, top - dy),
        min(mask.shape[1], right + dx),
        min(mask.shape[0], bottom + dy),
    )


def cover_fit(rgb: NDArray[np.uint8], size: tuple[int, int]) -> NDArray[np.uint8]:
    width, height = size
    source_height, source_width = rgb.shape[:2]
    if source_width * height > width * source_height:
        crop_width = max(1, round(source_height * width / height))
        x = (source_width - crop_width) // 2
        cropped = rgb[:, x : x + crop_width]
    else:
        crop_height = max(1, round(source_width * height / width))
        y = (source_height - crop_height) // 2
        cropped = rgb[y : y + crop_height]
    return np.asarray(
        cv2.resize(cropped, (width, height), interpolation=cv2.INTER_LINEAR), dtype=np.uint8
    )


_DEFAULT_COMPOSITION = ComposeOptions()


def compose(
    rgb: NDArray[np.uint8],
    mask: NDArray[np.float32],
    options: ComposeOptions = _DEFAULT_COMPOSITION,
    *,
    original: NDArray[np.uint8] | None = None,
    background: NDArray[np.uint8] | None = None,
) -> Image.Image:
    height, width = mask.shape
    alpha = np.asarray(np.clip(mask, 0, 1), dtype=np.float32)
    foreground = rgb
    # Work per channel to avoid several simultaneous full-resolution float RGB copies.
    canvas: NDArray[np.uint8] | None = None
    if options.bg_color is not None:
        canvas = np.empty_like(rgb)
        canvas[:] = ImageColor.getrgb(options.bg_color)[:3]
    elif background is not None:
        canvas = cover_fit(background, (width, height))
    elif options.bg_blur is not None:
        canvas = np.asarray(
            cv2.GaussianBlur(original if original is not None else rgb, (0, 0), options.bg_blur),
            dtype=np.uint8,
        )
    if options.shadow:
        shadow = cv2.GaussianBlur(alpha, (0, 0), max(1, min(width, height) * 0.015)) * 0.4
        offset = max(1, round(min(width, height) * 0.02))
        shadow = np.asarray(
            cv2.warpAffine(
                shadow,
                np.array([[1, 0, offset], [0, 1, offset]], dtype=np.float32),
                (width, height),
            ),
            dtype=np.float32,
        )
        if canvas is not None:
            canvas = np.stack(
                [np.rint(canvas[:, :, i] * (1 - shadow)).astype(np.uint8) for i in range(3)], axis=2
            )
        else:
            combined = alpha + shadow * (1 - alpha)
            factor = np.divide(alpha, combined, out=np.zeros_like(alpha), where=combined > 0)
            foreground = np.stack(
                [np.rint(rgb[:, :, i] * factor).astype(np.uint8) for i in range(3)], axis=2
            )
            alpha = combined
    if canvas is not None:
        foreground = np.stack(
            [
                np.rint(alpha * foreground[:, :, i] + (1 - alpha) * canvas[:, :, i])
                .clip(0, 255)
                .astype(np.uint8)
                for i in range(3)
            ],
            axis=2,
        )
        alpha = np.ones_like(alpha)
    image = Image.fromarray(np.dstack((foreground, np.rint(alpha * 255).astype(np.uint8))))
    if options.crop:
        box = subject_box(mask, options.padding)
        if box is not None:
            image = image.crop(box)
    if options.aspect is not None:
        w, h = image.size
        target = (max(w, math.ceil(h * options.aspect)), max(h, math.ceil(w / options.aspect)))
        fill = (
            ImageColor.getrgb(options.bg_color)[:3] + (255,) if options.bg_color else (0, 0, 0, 0)
        )
        if target[0] * target[1] > MAX_PIXELS:
            raise ValueError("Padded canvas exceeds pixel limit")
        padded = Image.new("RGBA", target, fill)
        padded.paste(image, ((target[0] - w) // 2, (target[1] - h) // 2))
        image = padded
    return image
