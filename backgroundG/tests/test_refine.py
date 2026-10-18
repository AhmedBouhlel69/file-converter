import importlib
from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from numpy.typing import NDArray

from bgremove.refine import RefineOptions, refine


@pytest.mark.parametrize(
    "options",
    [
        {"threshold": -0.1},
        {"threshold": 1.1},
        {"threshold": float("nan")},
        {"threshold": True},
        {"edge_shift": -6},
        {"edge_shift": 6},
        {"edge_shift": 1.5},
        {"edge_shift": True},
        {"min_blob_ratio": -0.001},
        {"min_blob_ratio": 1.1},
        {"feather_sigma": -1},
        {"feather_sigma": float("inf")},
        {"guided_radius": -1},
        {"guided_radius": 1.5},
        {"guided_eps": 0},
        {"guided_eps": float("nan")},
        {"matting": 1},
    ],
)
def test_invalid_options(options: dict[str, Any]) -> None:
    with pytest.raises((ValueError, TypeError)):
        RefineOptions(**options)


def test_options_are_immutable() -> None:
    options = RefineOptions()
    with pytest.raises(FrozenInstanceError):
        options.edge_shift = 1  # type: ignore[misc]


def test_disabled_refinement_is_exact_and_preserves_inputs() -> None:
    rng = np.random.default_rng(1)
    mask = rng.random((17, 23), dtype=np.float32)
    original = mask.copy()
    rgb = rng.integers(0, 256, (17, 23, 3), dtype=np.uint8)
    original_rgb = rgb.copy()
    result, foreground = refine(rgb, mask, RefineOptions(min_blob_ratio=0))
    assert np.array_equal(result, original)
    assert np.array_equal(mask, original)
    assert np.array_equal(rgb, original_rgb)
    assert foreground is None
    assert result is not mask


def test_cleanup_removes_islands_fills_only_enclosed_holes_and_retains_soft_alpha() -> None:
    mask = np.zeros((30, 30), dtype=np.float32)
    mask[5:25, 5:25] = 0.8
    mask[0, 0] = 0.9  # Isolated foreground touching the boundary is still a speck.
    mask[12, 12] = 0.2  # Small enclosed hole.
    mask[5:9, 15] = 0.2  # Narrow notch connected to exterior stays open.
    original = mask.copy()
    result, _ = refine(np.zeros((30, 30, 3), dtype=np.uint8), mask, RefineOptions())
    # Default threshold is 0.9 pixels at this size; explicitly enlarge to remove one pixel.
    assert np.array_equal(result, original)
    result, _ = refine(
        np.zeros((30, 30, 3), dtype=np.uint8), mask, RefineOptions(min_blob_ratio=0.01)
    )
    assert result[0, 0] == 0
    assert result[12, 12] == 1
    assert np.array_equal(result[5:9, 15], mask[5:9, 15])
    assert result[15, 15] == mask[15, 15] == np.float32(0.8)
    assert np.array_equal(mask, original)


def test_threshold_and_edge_shift_change_geometry_in_expected_direction() -> None:
    mask = np.zeros((21, 21), dtype=np.float32)
    mask[6:15, 6:15] = 0.8
    rgb = np.zeros((21, 21, 3), dtype=np.uint8)
    eroded, _ = refine(rgb, mask, RefineOptions(edge_shift=-1, min_blob_ratio=0))
    dilated, _ = refine(rgb, mask, RefineOptions(edge_shift=1, min_blob_ratio=0))
    assert np.count_nonzero(eroded) < np.count_nonzero(mask) < np.count_nonzero(dilated)
    assert eroded[10, 10] == np.float32(0.8)
    assert dilated[5, 10] == np.float32(0.8)
    binary, _ = refine(rgb, mask, RefineOptions(threshold=0.8, min_blob_ratio=0))
    assert set(np.unique(binary)) == {0, 1}
    assert binary[10, 10] == 1


def test_feather_preserves_solid_interior_and_exterior() -> None:
    mask = np.zeros((51, 51), dtype=np.float32)
    mask[10:41, 10:41] = 1
    result, _ = refine(
        np.zeros((51, 51, 3), dtype=np.uint8),
        mask,
        RefineOptions(feather_sigma=1, min_blob_ratio=0),
    )
    assert result[25, 25] == 1
    assert result[0, 0] == 0
    assert 0 < result[9, 25] < 0.5
    assert 0.5 < result[10, 25] < 1
    assert result.dtype == np.float32


def test_guided_filter_retains_image_edges_and_reduces_flat_region_noise() -> None:
    rng = np.random.default_rng(7)
    rgb = np.zeros((41, 60, 3), dtype=np.uint8)
    rgb[:, 30:] = 255
    mask = np.zeros((41, 60), dtype=np.float32)
    mask[:, 30:] = 1
    mask = np.clip(mask + rng.normal(0, 0.1, mask.shape), 0, 1).astype(np.float32)
    result, _ = refine(rgb, mask, RefineOptions(guided_radius=5, guided_eps=1e-4, min_blob_ratio=0))
    assert result[:, :20].std() < mask[:, :20].std()
    assert result[:, 40:].std() < mask[:, 40:].std()
    assert result[:, 29].mean() < 0.1
    assert result[:, 30].mean() > 0.9
    assert result.dtype == np.float32
    assert np.isfinite(result).all()
    assert np.min(result) >= 0 and np.max(result) <= 1


@pytest.mark.parametrize("size", [(1, 1), (1, 100), (100, 1)])
def test_small_and_extreme_images(size: tuple[int, int]) -> None:
    mask = np.full(size, 0.4, dtype=np.float32)
    result, _ = refine(
        np.zeros((*size, 3), dtype=np.uint8),
        mask,
        RefineOptions(edge_shift=-2, feather_sigma=1, guided_radius=8),
    )
    assert result.shape == size
    assert np.allclose(result, 0.4)


@pytest.mark.parametrize(
    "problem", ["rgb_dtype", "rgb_shape", "mask_dtype", "shape", "nan", "range"]
)
def test_invalid_input(problem: str) -> None:
    rgb = np.zeros((5, 5, 3), dtype=np.uint8)
    mask = np.zeros((5, 5), dtype=np.float32)
    if problem == "rgb_dtype":
        rgb = rgb.astype(np.float32)
    elif problem == "rgb_shape":
        rgb = rgb[:, :, :2]
    elif problem == "mask_dtype":
        mask = mask.astype(np.float64)
    elif problem == "shape":
        mask = mask[:3]
    elif problem == "nan":
        mask[0, 0] = np.nan
    else:
        mask[0, 0] = 1.1
    with pytest.raises(ValueError):
        refine(rgb, mask)


def _matting_input(
    height: int = 60, width: int = 80
) -> tuple[NDArray[np.uint8], NDArray[np.float32]]:
    rgb = np.full((height, width, 3), 90, dtype=np.uint8)
    mask = np.zeros((height, width), dtype=np.float32)
    mask[:, width // 2 :] = 1
    return rgb, mask


def test_matting_trimap_and_foreground_decontamination(monkeypatch: pytest.MonkeyPatch) -> None:
    rgb, mask = _matting_input()
    calls: list[str] = []

    def alpha(image: NDArray[np.float64], trimap: NDArray[np.float64]) -> NDArray[np.float64]:
        calls.append("alpha")
        assert image.dtype == np.float64
        assert np.min(image) >= 0 and np.max(image) <= 1
        assert set(np.unique(trimap)) == {0, 0.5, 1}
        assert trimap[30, 10] == 0
        assert trimap[30, 70] == 1
        assert trimap[30, 39] == trimap[30, 40] == 0.5
        return np.full(trimap.shape, 0.6)

    def foreground(
        image: NDArray[np.float64], estimated: NDArray[np.float32]
    ) -> NDArray[np.float64]:
        calls.append("foreground")
        assert estimated[30, 10] == 0 and estimated[30, 70] == 1
        assert estimated[30, 40] == np.float32(0.6)
        colours = np.zeros_like(image)
        colours[:, :, 1] = 1
        return colours

    module = SimpleNamespace(estimate_alpha_cf=alpha, estimate_foreground_ml=foreground)
    monkeypatch.setattr(importlib, "import_module", lambda name: module)
    result, colours = refine(rgb, mask, RefineOptions(matting=True, min_blob_ratio=0))
    assert calls == ["alpha", "foreground"]
    assert result.dtype == np.float32
    assert colours is not None and colours.dtype == np.uint8
    assert np.all(colours[:, :, 0] == 0) and np.all(colours[:, :, 1] == 255)
    assert np.all(rgb == 90)


@pytest.mark.parametrize("size", [(201, 201), (1, 1001), (1001, 1)])
def test_matting_working_copy_obeys_cap_even_for_extreme_aspect(
    monkeypatch: pytest.MonkeyPatch, size: tuple[int, int]
) -> None:
    refinement_module = importlib.import_module("bgremove.refine")
    monkeypatch.setattr(refinement_module, "MATTING_MAX_PIXELS", 100)
    rgb, mask = _matting_input(*size)
    if size[1] == 1:
        mask[: size[0] // 2] = 0
    called: list[int] = []

    def alpha(image: NDArray[np.float64], trimap: NDArray[np.float64]) -> NDArray[np.float64]:
        called.append(trimap.size)
        assert trimap.size <= 100
        return trimap

    module = SimpleNamespace(
        estimate_alpha_cf=alpha,
        estimate_foreground_ml=lambda image, estimated: image,
    )
    monkeypatch.setattr(importlib, "import_module", lambda name: module)
    result, colours = refine(rgb, mask, RefineOptions(matting=True, min_blob_ratio=0))
    assert called
    assert result.shape == size
    assert colours is not None and colours.shape == rgb.shape
    assert result.dtype == np.float32 and colours.dtype == np.uint8
    assert np.min(result) >= 0 and np.max(result) <= 1


def test_missing_matting_dependency_has_install_guidance(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(name: str) -> None:
        raise ModuleNotFoundError("No module named pymatting")

    monkeypatch.setattr(importlib, "import_module", missing)
    rgb, mask = _matting_input()
    with pytest.raises(RuntimeError, match=r"pip install.*\[matting\]"):
        refine(rgb, mask, RefineOptions(matting=True))


def test_matting_import_is_lazy(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(name: str) -> None:
        raise AssertionError("An optional dependency was imported during ordinary refinement")

    monkeypatch.setattr(importlib, "import_module", forbidden)
    rgb, mask = _matting_input()
    result, foreground = refine(rgb, mask, RefineOptions())
    assert np.array_equal(result, mask)
    assert foreground is None


def test_matting_retains_confident_seed_for_thin_subject(monkeypatch: pytest.MonkeyPatch) -> None:
    rgb = np.zeros((30, 30, 3), dtype=np.uint8)
    mask = np.zeros((30, 30), dtype=np.float32)
    mask[15, 15] = 1

    def alpha(image: NDArray[np.float64], trimap: NDArray[np.float64]) -> NDArray[np.float64]:
        assert trimap[15, 15] == 1
        assert trimap[0, 0] == 0
        return trimap

    module = SimpleNamespace(
        estimate_alpha_cf=alpha,
        estimate_foreground_ml=lambda image, estimated: image,
    )
    monkeypatch.setattr(importlib, "import_module", lambda name: module)
    result, _ = refine(rgb, mask, RefineOptions(matting=True, min_blob_ratio=0))
    assert result[15, 15] == 1


@pytest.mark.parametrize("stage", ["alpha", "foreground"])
def test_invalid_matting_output_is_rejected(monkeypatch: pytest.MonkeyPatch, stage: str) -> None:
    rgb, mask = _matting_input()

    def alpha(image: NDArray[np.float64], trimap: NDArray[np.float64]) -> NDArray[np.float64]:
        return np.full(trimap.shape, np.nan) if stage == "alpha" else trimap

    module = SimpleNamespace(
        estimate_alpha_cf=alpha,
        estimate_foreground_ml=lambda image, estimated: np.full(image.shape, np.nan),
    )
    monkeypatch.setattr(importlib, "import_module", lambda name: module)
    with pytest.raises(ValueError, match="Matting returned"):
        refine(rgb, mask, RefineOptions(matting=True, min_blob_ratio=0))


def test_matting_without_known_foreground_is_rejected() -> None:
    rgb = np.zeros((20, 20, 3), dtype=np.uint8)
    mask = np.full((20, 20), 0.5, dtype=np.float32)
    with pytest.raises(ValueError, match="confident foreground and background"):
        refine(rgb, mask, RefineOptions(matting=True))


@pytest.mark.parametrize("value", [0, 1])
def test_matting_handles_uniform_opaque_or_transparent_masks(value: int) -> None:
    rgb = np.zeros((4, 5, 3), dtype=np.uint8)
    mask = np.full((4, 5), value, dtype=np.float32)
    result, colours = refine(rgb, mask, RefineOptions(matting=True))
    assert np.array_equal(result, mask)
    assert np.array_equal(colours, rgb)
