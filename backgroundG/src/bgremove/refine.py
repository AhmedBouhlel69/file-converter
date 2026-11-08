"""Optional mask cleanup, edge refinement, and foreground colour recovery."""

import importlib
import math
from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray

MATTING_MAX_PIXELS = 4_000_000


@dataclass(frozen=True)
class RefineOptions:
    threshold: float | None = None
    edge_shift: int = 0
    min_blob_ratio: float = 0.001
    feather_sigma: float = 0
    guided_radius: int = 0
    guided_eps: float = 1e-3
    matting: bool = False
    # Recover true foreground colours at soft edges (removes halos left by the
    # old background) and clear the colour data hidden under transparent pixels.
    decontaminate: bool = False
    # Stretch alpha between these points: values <= low become transparent and
    # values >= high become opaque. This removes faint ghosting from soft masks.
    levels_low: float = 0.0
    levels_high: float = 1.0

    def __post_init__(self) -> None:
        if self.threshold is not None:
            _number("threshold", self.threshold, 0, 1)
        _integer("edge_shift", self.edge_shift, -5, 5)
        _number("min_blob_ratio", self.min_blob_ratio, 0, 1)
        _number("feather_sigma", self.feather_sigma, 0)
        _integer("guided_radius", self.guided_radius, 0)
        _number("guided_eps", self.guided_eps, 0)
        if self.guided_eps == 0:
            raise ValueError("guided_eps must be greater than zero")
        for name in ("matting", "decontaminate"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be a boolean")
        _number("levels_low", self.levels_low, 0, 1)
        _number("levels_high", self.levels_high, 0, 1)
        if self.levels_low >= self.levels_high:
            raise ValueError("levels_low must be smaller than levels_high")


def _number(name: str, value: float, minimum: float, maximum: float | None = None) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < minimum
        or (maximum is not None and value > maximum)
    ):
        bounds = f"{minimum} to {maximum}" if maximum is not None else f"at least {minimum}"
        raise ValueError(f"{name} must be a finite number {bounds}")


def _integer(name: str, value: int, minimum: int, maximum: int | None = None) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or (maximum is not None and value > maximum)
    ):
        bounds = f"{minimum} to {maximum}" if maximum is not None else f"at least {minimum}"
        raise ValueError(f"{name} must be an integer {bounds}")


_DEFAULT_OPTIONS = RefineOptions()


def refine(
    rgb: NDArray[np.uint8],
    mask: NDArray[np.float32],
    options: RefineOptions = _DEFAULT_OPTIONS,
) -> tuple[NDArray[np.float32], NDArray[np.uint8] | None]:
    """Return refined alpha and, for matting, estimated foreground RGB.

    Inputs are never modified. Set ``min_blob_ratio=0`` to disable the cleanup
    enabled by default; all other refinement operations are opt-in.
    """
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("rgb must be an H x W x 3 uint8 array")
    if (
        mask.dtype != np.float32
        or mask.ndim != 2
        or mask.shape != rgb.shape[:2]
        or mask.size == 0
        or not np.isfinite(mask).all()
        or np.any(mask < 0)
        or np.any(mask > 1)
    ):
        raise ValueError("mask must be a matching, nonempty float32 array in [0, 1]")
    alpha = mask.copy()
    if options.threshold is not None:
        alpha = (alpha >= options.threshold).astype(np.float32)
    if options.min_blob_ratio:
        alpha = _cleanup(alpha, options.min_blob_ratio)
    if options.levels_low > 0 or options.levels_high < 1:
        span = np.float32(options.levels_high - options.levels_low)
        alpha = np.asarray(
            np.clip((alpha - np.float32(options.levels_low)) / span, 0, 1), dtype=np.float32
        )
    if options.edge_shift:
        radius = abs(options.edge_shift)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius + 1,) * 2)
        operation = cv2.erode if options.edge_shift < 0 else cv2.dilate
        alpha = np.asarray(operation(alpha, kernel), dtype=np.float32)
    if options.feather_sigma:
        alpha = _feather(alpha, options.feather_sigma)
    if options.guided_radius:
        alpha = _guided(rgb, alpha, options.guided_radius, options.guided_eps)
    if options.matting:
        return _matte(rgb, alpha)
    if options.decontaminate:
        return alpha, estimate_foreground(rgb, alpha)
    return alpha, None


def _cleanup(alpha: NDArray[np.float32], ratio: float) -> NDArray[np.float32]:
    # Classify topology at 0.5 without quantising the surviving soft mask.
    binary = (alpha >= 0.5).astype(np.uint8)
    minimum_area = alpha.size * ratio
    count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    small = np.zeros(count, dtype=np.bool_)
    small[1:] = stats[1:, cv2.CC_STAT_AREA] < minimum_area
    alpha[small[labels]] = 0
    binary[small[labels]] = 0

    count, labels, stats, _ = cv2.connectedComponentsWithStats(1 - binary, connectivity=8)
    holes = np.zeros(count, dtype=np.bool_)
    holes[1:] = stats[1:, cv2.CC_STAT_AREA] < minimum_area
    # Background touching any image boundary is exterior, including tiny pockets.
    boundary = np.concatenate((labels[0], labels[-1], labels[:, 0], labels[:, -1]))
    holes[np.unique(boundary)] = False
    alpha[holes[labels]] = 1
    return alpha


def _feather(alpha: NDArray[np.float32], sigma: float) -> NDArray[np.float32]:
    radius = max(1, math.ceil(3 * sigma))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2 * radius + 1,) * 2)
    edge_band = cv2.dilate(alpha, kernel) != cv2.erode(alpha, kernel)
    blurred = cv2.GaussianBlur(alpha, (2 * radius + 1,) * 2, sigma, sigmaY=sigma)
    alpha[edge_band] = blurred[edge_band]
    return alpha


def _guided(
    rgb: NDArray[np.uint8], alpha: NDArray[np.float32], radius: int, epsilon: float
) -> NDArray[np.float32]:
    guide = np.asarray(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), dtype=np.float32) / np.float32(255)
    size = (2 * radius + 1,) * 2

    def mean(values: NDArray[np.float32]) -> NDArray[np.float32]:
        return np.asarray(cv2.boxFilter(values, -1, size, normalize=True), dtype=np.float32)

    guide_mean, alpha_mean = mean(guide), mean(alpha)
    variance = np.maximum(mean(guide * guide) - guide_mean * guide_mean, 0)
    covariance = mean(guide * alpha) - guide_mean * alpha_mean
    a = np.asarray(covariance / (variance + epsilon), dtype=np.float32)
    b = np.asarray(alpha_mean - a * guide_mean, dtype=np.float32)
    return np.asarray(np.clip(mean(a) * guide + mean(b), 0, 1), dtype=np.float32)


def _trimap(alpha: NDArray[np.float32]) -> NDArray[np.float64]:
    radius = max(1, min(25, round(math.sqrt(alpha.size) / 100)))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius + 1,) * 2)
    foreground = (alpha > 0.95).astype(np.uint8)
    background = (alpha < 0.05).astype(np.uint8)
    # Keep both known regions away from uncertain boundaries. Eroding the
    # background is equivalent to dilating the subject's possible support.
    known_fg = cv2.erode(foreground, kernel).astype(np.bool_)
    known_bg = cv2.erode(background, kernel).astype(np.bool_)
    # A thin but confident object must retain seeds even if erosion removes it.
    if not np.any(known_fg):
        known_fg = foreground.astype(np.bool_)
    if not np.any(known_bg):
        known_bg = background.astype(np.bool_)
    if not np.any(known_fg) or not np.any(known_bg):
        raise ValueError("Alpha matting requires both confident foreground and background")
    trimap = np.full(alpha.shape, 0.5, dtype=np.float64)
    trimap[known_fg] = 1
    trimap[known_bg] = 0
    return trimap


def _matte(
    rgb: NDArray[np.uint8], alpha: NDArray[np.float32]
) -> tuple[NDArray[np.float32], NDArray[np.uint8]]:
    if np.all(alpha < 0.05):
        return np.zeros_like(alpha), rgb.copy()
    if np.all(alpha > 0.95):
        return np.ones_like(alpha), rgb.copy()
    height, width = alpha.shape
    scale = min(1.0, math.sqrt(MATTING_MAX_PIXELS / alpha.size))
    working_size = (max(1, math.floor(width * scale)), max(1, math.floor(height * scale)))
    if working_size[0] * working_size[1] > MATTING_MAX_PIXELS:
        # Rounding a very thin image up to one pixel must still obey the cap.
        if working_size[0] >= working_size[1]:
            working_size = (MATTING_MAX_PIXELS // working_size[1], working_size[1])
        else:
            working_size = (working_size[0], MATTING_MAX_PIXELS // working_size[0])
    working_rgb = rgb
    working_alpha = alpha
    if working_size != (width, height):
        working_rgb = np.asarray(
            cv2.resize(rgb, working_size, interpolation=cv2.INTER_AREA), dtype=np.uint8
        )
        working_alpha = np.asarray(
            cv2.resize(alpha, working_size, interpolation=cv2.INTER_AREA), dtype=np.float32
        )
    trimap = _trimap(working_alpha)
    try:
        pymatting = importlib.import_module("pymatting")
    except ImportError as error:
        raise RuntimeError(
            "Alpha matting requires pymatting; install it with pip install 'local-bgremove[matting]'"
        ) from error
    image = working_rgb.astype(np.float64) / 255
    estimate = np.asarray(pymatting.estimate_alpha_cf(image, trimap), dtype=np.float32)
    if estimate.shape != working_alpha.shape or not np.isfinite(estimate).all():
        raise ValueError("Matting returned an invalid alpha mask")
    estimate = np.clip(estimate, 0, 1)
    estimate[trimap == 0] = 0
    estimate[trimap == 1] = 1
    foreground = np.asarray(pymatting.estimate_foreground_ml(image, estimate), dtype=np.float64)
    if foreground.shape != working_rgb.shape or not np.isfinite(foreground).all():
        raise ValueError("Matting returned invalid foreground colours")
    colours = np.asarray(np.rint(np.clip(foreground, 0, 1) * 255), dtype=np.uint8)
    if working_size != (width, height):
        estimate = np.asarray(
            np.clip(cv2.resize(estimate, (width, height), interpolation=cv2.INTER_CUBIC), 0, 1),
            dtype=np.float32,
        )
        colours = np.asarray(
            cv2.resize(colours, (width, height), interpolation=cv2.INTER_LINEAR), dtype=np.uint8
        )
    return estimate, colours


_FG_STRIPE_ROWS = 384


def _fb_blur_fusion(
    image: NDArray[np.float32],
    foreground: NDArray[np.float32],
    background: NDArray[np.float32],
    alpha: NDArray[np.float32],
    size: int,
) -> tuple[NDArray[np.float32], NDArray[np.float32]]:
    """One blur-fusion step (Germer et al., 2021) with a box kernel."""
    kernel = (size, size)
    a = alpha[:, :, None]
    blurred_alpha = cv2.blur(alpha, kernel)[:, :, None]
    blurred_fg = cv2.blur(foreground * a, kernel) / (blurred_alpha + np.float32(1e-5))
    blurred_bg = cv2.blur(background * (1 - a), kernel) / ((1 - blurred_alpha) + np.float32(1e-5))
    estimate = blurred_fg + a * (image - a * blurred_fg - (1 - a) * blurred_bg)
    return np.clip(estimate, 0, 1, out=estimate), blurred_bg


def estimate_foreground(rgb: NDArray[np.uint8], alpha: NDArray[np.float32]) -> NDArray[np.uint8]:
    """Estimate un-mixed foreground colours for an alpha matte.

    Soft edge pixels contain a blend of subject and old background; compositing
    them on a new background leaves a halo. Blur-fusion removes that background
    contribution. Fully opaque pixels are returned untouched. Pixels that are
    invisible once the alpha is saved as 8-bit (apart from a two-pixel ring) come
    back black, so a transparent result no longer carries the removed background
    in its hidden colour channels.

    Runs in horizontal stripes with a halo so memory stays small on large images.
    """
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("rgb must be an H x W x 3 uint8 array")
    if alpha.shape != rgb.shape[:2]:
        raise ValueError("alpha must match the image size")
    height, width = alpha.shape
    large = max(9, min(90, round(max(height, width) * 0.03)))
    small = max(3, round(large / 15))
    large, small = large | 1, small | 1
    halo = large + small
    output = np.zeros_like(rgb)
    solid = alpha >= 1
    for top in range(0, height, _FG_STRIPE_ROWS):
        bottom = min(height, top + _FG_STRIPE_ROWS)
        start, stop = max(0, top - halo), min(height, bottom + halo)
        window = alpha[start:stop]
        if not np.any(window > 0):
            continue  # nothing visible nearby: leave hidden pixels black
        if np.all(window >= 1):
            output[top:bottom] = rgb[top:bottom]
            continue
        image = rgb[start:stop].astype(np.float32) / np.float32(255)
        a = np.ascontiguousarray(window)
        first, background = _fb_blur_fusion(image, image, image, a, large)
        second, _ = _fb_blur_fusion(image, first, background, a, small)
        estimate = np.rint(second[top - start : bottom - start] * 255).astype(np.uint8)
        output[top:bottom] = estimate
    output[solid] = rgb[solid]
    # Soft masks have faint tails that round to alpha 0 once saved as 8-bit. Keep
    # estimated colours only in a thin ring around visible pixels (so naive image
    # scalers do not pull in black fringes) and blank everything else.
    visible = (alpha >= np.float32(0.5 / 255)).astype(np.uint8)
    keep = cv2.dilate(visible, np.ones((5, 5), np.uint8)).astype(np.bool_)
    output[~keep] = 0
    return output
