"""Halo removal, alpha levels, flip averaging and cached model verification."""

import time

import cv2
import numpy as np
import pytest
from PIL import Image

from bgremove import Remover
from bgremove import registry as registry_module
from bgremove.refine import RefineOptions, estimate_foreground, refine


def _soft_disc(height: int = 120, width: int = 160, radius: float = 40, soft: float = 6):
    rows, columns = np.mgrid[:height, :width]
    distance = np.hypot(rows - height / 2, columns - width / 2)
    alpha = np.clip((radius - distance) / soft + 0.5, 0, 1).astype(np.float32)
    foreground = np.zeros((height, width, 3), dtype=np.float32)
    foreground[:] = (0.15, 0.25, 0.75)
    backdrop = np.zeros_like(foreground)
    backdrop[:] = (0.95, 0.85, 0.2)
    mixed = alpha[..., None] * foreground + (1 - alpha[..., None]) * backdrop
    rgb = np.rint(np.clip(mixed, 0, 1) * 255).astype(np.uint8)
    truth = np.rint(foreground * 255)
    return rgb, alpha, truth, distance


@pytest.mark.parametrize(("size", "factor"), [((400, 600), 3), ((120, 160), 1.5)])
def test_estimate_foreground_removes_backdrop_colour_from_soft_edges(size, factor) -> None:
    rgb, alpha, truth, _ = _soft_disc(*size, radius=min(size) * 0.35)
    estimate = estimate_foreground(rgb, alpha)
    edge = (alpha > 0.05) & (alpha < 0.95)
    assert edge.sum() > 200
    raw_error = np.abs(rgb.astype(float) - truth)[edge].mean()
    fixed_error = np.abs(estimate.astype(float) - truth)[edge].mean()
    assert fixed_error < raw_error / factor
    assert estimate.dtype == np.uint8


def test_estimate_foreground_keeps_opaque_pixels_and_blanks_far_hidden_pixels() -> None:
    rgb, alpha, _, distance = _soft_disc()
    estimate = estimate_foreground(rgb, alpha)
    assert np.array_equal(estimate[alpha >= 1], rgb[alpha >= 1])
    far = distance > 70
    assert far.any()
    # Hidden colour data must not leak the removed background.
    assert estimate[far].max() == 0


def test_estimate_foreground_has_no_seams_between_stripes(monkeypatch) -> None:
    from bgremove import refine as refine_module

    rgb, alpha, truth, _ = _soft_disc(height=900, width=300, radius=130, soft=8)
    monkeypatch.setattr(refine_module, "_FG_STRIPE_ROWS", 10**6)
    whole = estimate_foreground(rgb, alpha)
    monkeypatch.setattr(refine_module, "_FG_STRIPE_ROWS", 97)
    striped = estimate_foreground(rgb, alpha)
    # Striping with a halo is only a memory optimisation: results must agree
    # apart from one-level rounding.
    assert np.abs(whole.astype(int) - striped.astype(int)).max() <= 1
    edge = (alpha > 0.05) & (alpha < 0.95)
    assert np.abs(striped.astype(float) - truth)[edge].mean() < 25


def test_estimate_foreground_rejects_invalid_input() -> None:
    with pytest.raises(ValueError):
        estimate_foreground(np.zeros((4, 4), dtype=np.uint8), np.zeros((4, 4), dtype=np.float32))
    with pytest.raises(ValueError):
        estimate_foreground(np.zeros((4, 4, 3), dtype=np.uint8), np.zeros((5, 4), dtype=np.float32))


def test_decontaminate_option_returns_foreground_and_default_does_not() -> None:
    rgb, alpha, _, _ = _soft_disc()
    _, plain = refine(rgb, alpha, RefineOptions(min_blob_ratio=0))
    assert plain is None
    result, foreground = refine(rgb, alpha, RefineOptions(min_blob_ratio=0, decontaminate=True))
    assert foreground is not None and foreground.shape == rgb.shape
    assert np.array_equal(result, alpha)


def test_levels_remove_faint_ghosting_and_keep_solid_regions() -> None:
    mask = np.zeros((20, 20), dtype=np.float32)
    mask[5:15, 5:15] = 1
    mask[0:2, 0:2] = 0.1  # faint ghost
    mask[8, 2] = 0.5
    rgb = np.zeros((20, 20, 3), dtype=np.uint8)
    result, _ = refine(rgb, mask, RefineOptions(min_blob_ratio=0, levels_low=0.2, levels_high=0.8))
    assert result[0, 0] == 0
    assert result[10, 10] == 1
    assert result[8, 2] == pytest.approx(0.5)
    assert result.dtype == np.float32


@pytest.mark.parametrize(
    "options",
    [
        {"levels_low": 0.6, "levels_high": 0.4},
        {"levels_low": 0.5, "levels_high": 0.5},
        {"levels_low": -0.1},
        {"levels_high": 1.1},
        {"decontaminate": 1},
    ],
)
def test_new_options_are_validated(options) -> None:
    with pytest.raises((ValueError, TypeError)):
        RefineOptions(**options)


def test_flip_averaging_runs_two_inferences_and_stays_in_range(model) -> None:
    registry, directory = model
    remover = Remover(registry=registry, model_dir=directory, device="cpu")
    image = Image.new("RGB", (17, 11), (128, 128, 128))
    plain = remover.remove(image)
    averaged = remover.remove(image, tta=True)
    # The fixture is symmetric, so mirroring cannot change its prediction.
    assert np.allclose(plain.mask, averaged.mask, atol=1e-6)
    assert averaged.timings["inference"] > 0
    assert averaged.mask.dtype == np.float32
    assert 0 <= averaged.mask.min() and averaged.mask.max() <= 1


def test_flip_averaging_mirrors_prediction_back(model, monkeypatch) -> None:
    registry, directory = model
    remover = Remover(registry=registry, model_dir=directory, device="cpu")
    calls: list[np.ndarray] = []

    def fake_once(engine, rgb, timings):
        calls.append(rgb.copy())
        mask = np.zeros(rgb.shape[:2], dtype=np.float32)
        mask[:, 0] = 1  # left column only, in whatever orientation we were given
        return mask

    monkeypatch.setattr(remover, "_predict_once", fake_once)
    mask = remover._predict(remover.warmup(), np.zeros((4, 6, 3), dtype=np.uint8), {}, tta=True)
    assert len(calls) == 2
    assert mask[:, 0].tolist() == [0.5] * 4 and mask[:, -1].tolist() == [0.5] * 4
    assert mask[:, 1:-1].max() == 0


def test_model_verification_is_cached_until_the_file_changes(model, monkeypatch) -> None:
    registry, directory = model
    registry_module._VERIFIED.clear()
    reads = []
    real = registry_module.hashlib.file_digest

    def counting(stream, algorithm):
        reads.append(1)
        return real(stream, algorithm)

    monkeypatch.setattr(registry_module.hashlib, "file_digest", counting)
    Remover(registry=registry, model_dir=directory, device="cpu")
    Remover(registry=registry, model_dir=directory, device="cpu")
    assert len(reads) == 1
    path = directory / "test.onnx"
    path.write_bytes(path.read_bytes() + b"\0")
    time.sleep(0.01)
    with pytest.raises(registry_module.ModelError, match="hash mismatch"):
        Remover(registry=registry, model_dir=directory, device="cpu")
    assert len(reads) == 2


def test_export_falls_back_when_the_drive_has_no_hard_links(tmp_path, monkeypatch) -> None:
    from bgremove import export as export_module

    def no_links(source, target):
        raise PermissionError("no hard links here")

    monkeypatch.setattr(export_module.os, "link", no_links)
    image = Image.new("RGBA", (6, 4), (1, 2, 3, 4))
    export_module.export(image, tmp_path / "out.png")
    with Image.open(tmp_path / "out.png") as saved:
        assert saved.size == (6, 4)
    with pytest.raises(FileExistsError):
        export_module.export(image, tmp_path / "out.png")
    assert not list(tmp_path.glob("tmp*"))


def test_hidden_colours_are_blank_even_under_faint_alpha_tails() -> None:
    rgb, alpha, _, distance = _soft_disc(height=200, width=300, radius=60)
    tails = alpha.copy()
    tails[(distance > 80) & (distance < 140)] = 0.0015  # rounds to alpha 0 when saved as 8-bit
    estimate = estimate_foreground(rgb, tails)
    invisible = np.rint(tails * 255) == 0
    visible = ~invisible
    near = cv2.dilate(visible.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    leaked = invisible & ~near & (estimate.max(axis=2) > 0)
    assert not leaked.any()
    # ... while the ring next to the subject keeps usable colours for scalers.
    ring = invisible & near
    assert ring.any() and estimate[ring].max() > 0
