import json
import socket
from io import BytesIO

import numpy as np
import pytest
from PIL import Image
from typer.testing import CliRunner

from bgremove import Remover
from bgremove.cli import app
from bgremove.export import export
from bgremove.loader import InputError, load
from bgremove.registry import ModelError


def test_offline_pipeline(model, monkeypatch, tmp_path):
    def blocked(*args, **kwargs):
        raise AssertionError("Network use forbidden")

    monkeypatch.setattr(socket, "socket", blocked)
    registry, directory = model
    remover = Remover(registry=registry, model_dir=directory, device="cpu")
    image = Image.new("RGB", (17, 11), (128, 128, 128))
    first, second = remover.remove(image), remover.remove(image)
    assert first.rgba.size == image.size
    assert np.asarray(first.rgba).dtype == np.uint8
    assert first.mask.dtype == np.float32
    assert np.allclose(first.mask, 128 / 255)
    assert first.provider == "CPUExecutionProvider"
    assert np.array_equal(first.rgba, second.rgba)
    first.save(tmp_path / "a.png")
    second.save(tmp_path / "b.png")
    assert (tmp_path / "a.png").read_bytes() == (tmp_path / "b.png").read_bytes()
    with pytest.raises(FileExistsError):
        first.save(tmp_path / "a.png")


@pytest.mark.parametrize("mode", ["L", "LA", "P", "RGBA", "CMYK", "I;16"])
@pytest.mark.parametrize("size", [(1, 1), (3000, 1)])
def test_modes(mode, size):
    result = load(Image.new(mode, size))
    assert result.rgb.shape == (size[1], size[0], 3)


def test_orientation_and_metadata(tmp_path):
    image = Image.new("RGB", (10, 20))
    exif = image.getexif()
    exif[274] = 6
    exif[315] = "private author"
    data = BytesIO()
    image.save(data, format="JPEG", exif=exif)
    loaded = load(data.getvalue())
    assert loaded.rgb.shape == (10, 20, 3)
    path = tmp_path / "result.png"
    export(Image.fromarray(loaded.rgb), path)
    with Image.open(path) as output:
        assert not output.getexif()


@pytest.mark.parametrize("data", [b"", b"not an image"])
def test_corrupt(data):
    with pytest.raises(InputError):
        load(data)


def test_limits():
    with pytest.raises(InputError):
        load(Image.new("RGB", (10, 10)), max_pixels=99)
    with pytest.raises(InputError):
        load(b"abc", max_bytes=2)


def test_hash_and_licence(model):
    registry, directory = model
    data = json.loads(registry.read_text())
    data["balanced"]["commercial_use"] = False
    registry.write_text(json.dumps(data))
    with pytest.raises(ModelError, match="noncommercial"):
        Remover(registry=registry, model_dir=directory)
    (directory / "test.onnx").write_bytes(b"tampered")
    with pytest.raises(ModelError, match="hash mismatch"):
        Remover(registry=registry, model_dir=directory, allow_noncommercial=True)


def test_cli(model, tmp_path):
    registry, directory = model
    source = tmp_path / "photo.png"
    Image.new("RGB", (13, 7), "white").save(source)
    result = CliRunner().invoke(
        app,
        [
            str(source),
            "-o",
            str(tmp_path / "out"),
            "--registry",
            str(registry),
            "--model-dir",
            str(directory),
            "--device",
            "cpu",
        ],
    )
    assert result.exit_code == 0, result.output
    assert Image.open(tmp_path / "out/photo_nobg.png").size == (13, 7)


def test_icc_and_webp(tmp_path):
    from PIL import ImageCms

    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    data = BytesIO()
    Image.new("RGB", (4, 5)).save(data, format="PNG", icc_profile=profile)
    loaded = load(data.getvalue())
    assert loaded.icc == profile
    target = tmp_path / "icc.webp"
    export(Image.fromarray(loaded.rgb), target, icc=loaded.icc)
    with Image.open(target) as image:
        assert image.info["icc_profile"] == profile


def test_tensor_transforms():
    from bgremove.postprocess import postprocess
    from bgremove.preprocess import preprocess
    from bgremove.registry import ModelConfig

    config = ModelConfig(
        "test", "test.onnx", "", (8, 4), (0, 0, 0), (1, 1, 1), output_activation="sigmoid"
    )
    tensor = preprocess(np.zeros((1, 1, 3), dtype=np.uint8), config)
    assert tensor.shape == (1, 3, 4, 8)
    mask = postprocess(np.zeros((1, 1, 4, 8), dtype=np.float32), (1, 1), config)
    assert mask.shape == (1, 1)
    assert mask[0, 0] == 0.5
