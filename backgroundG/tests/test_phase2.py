import numpy as np
import pytest
from PIL import Image
from typer.testing import CliRunner

from bgremove import ComposeOptions, RefineOptions, Remover
from bgremove.batch import BatchOptions, plan_batch, run_batch
from bgremove.cli import app
from bgremove.compose import compose


def test_composition_and_crop():
    rgb = np.full((20, 30, 3), 200, dtype=np.uint8)
    mask = np.zeros((20, 30), dtype=np.float32)
    mask[5:15, 10:20] = 1
    output = compose(rgb, mask, ComposeOptions(bg_color="#123456"))
    assert output.getpixel((0, 0)) == (18, 52, 86, 255)
    assert output.getpixel((15, 10)) == (200, 200, 200, 255)
    cropped = compose(rgb, mask, ComposeOptions(crop=True, padding=2, aspect=1))
    assert cropped.size == (14, 14)
    assert cropped.getpixel((0, 0))[3] == 0
    assert compose(rgb, np.zeros_like(mask), ComposeOptions(crop=True)).size == (30, 20)


def test_background_cover_shadow_and_blur():
    rgb = np.full((20, 30, 3), 200, dtype=np.uint8)
    mask = np.zeros((20, 30), dtype=np.float32)
    mask[5:15, 10:20] = 1
    background = np.full((5, 30, 3), 50, dtype=np.uint8)
    image = compose(rgb, mask, background=background)
    assert image.size == (30, 20)
    assert image.getpixel((0, 0)) == (50, 50, 50, 255)
    shadow = compose(rgb, mask, ComposeOptions(shadow=True))
    assert np.asarray(shadow)[:, :, 3].sum() > mask.sum() * 255
    blur = compose(rgb, mask, ComposeOptions(bg_blur=3))
    assert blur.getpixel((0, 0)) == (200, 200, 200, 255)


@pytest.mark.parametrize(
    "options",
    [
        {"padding": -1},
        {"bg_blur": 0},
        {"bg_blur": float("nan")},
        {"aspect": 0},
        {"bg_color": "invalid"},
        {"bg_color": "red", "bg_blur": 2},
    ],
)
def test_bad_composition(options):
    with pytest.raises(ValueError):
        ComposeOptions(**options)


def test_plan_recursive_resume_and_collision(tmp_path):
    source = tmp_path / "source"
    nested = source / "nested"
    nested.mkdir(parents=True)
    Image.new("RGB", (8, 8)).save(nested / "a.jpg")
    output = source / "out"
    items = plan_batch([source], output, recursive=True, save_mask=True)
    assert len(items) == 1
    assert items[0].image == output / "nested/a_nobg.png"
    assert items[0].mask == output / "nested/a_mask.png"
    items[0].image.parent.mkdir(parents=True)
    items[0].image.write_bytes(b"keep")
    resumed = plan_batch([source], output, recursive=True, save_mask=True, skip_existing=True)
    assert len(resumed) == 1 and resumed[0].image is None and resumed[0].mask is not None
    Image.new("RGB", (8, 8)).save(nested / "a.png")
    with pytest.raises(ValueError, match="collision"):
        plan_batch([source], output, recursive=True, overwrite=True)


def test_parallel_batch_and_resume(model, tmp_path):
    registry, directory = model
    source = tmp_path / "input"
    source.mkdir()
    for name in ("a", "b"):
        Image.new("RGB", (11, 7), "white").save(source / f"{name}.png")
    output = tmp_path / "out"
    config = {"registry": registry, "model_dir": directory, "device": "cpu", "threads": 1}
    items = plan_batch([source], output, save_mask=True, format="webp")
    results = run_batch(items, config, BatchOptions(), jobs=2)
    assert [x.status for x in results] == ["saved", "saved"]
    for item in items:
        assert Image.open(item.image).size == (11, 7)
        assert Image.open(item.mask).mode == "L"
    resumed = plan_batch([source], output, save_mask=True, format="webp", skip_existing=True)
    assert all(x.status == "skipped" for x in run_batch(resumed, config, BatchOptions()))


def test_cli_options_and_errors(model, tmp_path):
    registry, directory = model
    source = tmp_path / "photo.png"
    Image.new("RGB", (13, 7), "white").save(source)
    base = [
        str(source),
        "-o",
        str(tmp_path / "out"),
        "--registry",
        str(registry),
        "--model-dir",
        str(directory),
    ]
    runner = CliRunner()
    result = runner.invoke(app, base + ["--mask-only", "--threshold", "0.5"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "out/photo_mask.png").exists()
    assert not (tmp_path / "out/photo_nobg.png").exists()
    invalid = runner.invoke(app, base + ["--threshold", "2"])
    assert invalid.exit_code == 2, invalid.output
    corrupt = tmp_path / "corrupt.jpg"
    corrupt.write_bytes(b"bad")
    bad = runner.invoke(
        app,
        [
            "remove",
            str(corrupt),
            "-o",
            str(tmp_path / "out"),
            "--registry",
            str(registry),
            "--model-dir",
            str(directory),
        ],
    )
    assert bad.exit_code == 4, bad.output


def test_two_pass_tiny_subject(model, monkeypatch):
    registry, directory = model
    remover = Remover(registry=registry, model_dir=directory, device="cpu")
    calls = []

    def predict(engine, rgb, timings):
        calls.append(rgb.shape)
        result = np.zeros(rgb.shape[:2], dtype=np.float32)
        if len(calls) == 1:
            result[40:60, 40:60] = 1
        else:
            result[:] = 0.8
        return result

    monkeypatch.setattr(remover, "_predict", predict)
    result = remover.remove(
        Image.new("RGB", (100, 100)), two_pass=True, refinement=RefineOptions(min_blob_ratio=0)
    )
    assert calls == [(100, 100, 3), (24, 24, 3)]
    assert result.mask[50, 50] == np.float32(0.8)
    assert result.mask[0, 0] == 0
    assert result.mask.shape == (100, 100)


def test_model_commands(model):
    registry, directory = model
    runner = CliRunner()
    args = ["--registry", str(registry), "--model-dir", str(directory)]
    listed = runner.invoke(app, ["models", "list", *args])
    assert listed.exit_code == 0, listed.output
    assert '"installed": true' in listed.output
    verified = runner.invoke(app, ["models", "verify", "balanced", *args])
    assert verified.exit_code == 0, verified.output
