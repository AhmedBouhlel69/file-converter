"""Background-removal CLI routing, safety, and diagnostics without inference."""

from pathlib import Path

from PIL import Image
import pytest

from image_converter.cli import main
from image_converter.core import background_removal
from image_converter.core.engine import ConversionResult


@pytest.fixture
def photo(tmp_path):
    source = tmp_path / "photo.png"
    Image.new("RGB", (20, 12), "red").save(source)
    return source


@pytest.fixture
def service_calls(monkeypatch):
    calls = {"configs": [], "batches": []}

    class FakeService:
        def __init__(self, config):
            calls["configs"].append(config)

        def run_batch(self, tasks, progress_callback=None, cancel_check=None):
            calls["batches"].append(tasks)
            results = []
            for index, task in enumerate(tasks, start=1):
                result = ConversionResult(
                    input_path=task.input_path,
                    output_path=task.output_path,
                    success=True,
                )
                results.append(result)
                if progress_callback:
                    progress_callback(index, len(tasks), result)
            return results

    monkeypatch.setattr(background_removal, "BackgroundRemovalService", FakeService)
    return calls


def test_background_defaults_are_transparent_and_preserve_source(photo, service_calls, capsys):
    original = photo.read_bytes()

    assert main([str(photo), "--remove-background"]) == 0

    config = service_calls["configs"][0]
    task = service_calls["batches"][0][0]
    assert config.model == "fast"
    assert config.output_format == "PNG"
    assert config.bg_color is None
    assert config.keep_metadata is False
    assert task.output_path == photo.with_name("photo_nobg.png")
    assert photo.read_bytes() == original
    assert "1 succeeded, 0 failed" in capsys.readouterr().out


def test_background_webp_advanced_options(photo, tmp_path, service_calls):
    destination = tmp_path / "cutout.webp"
    models = tmp_path / "models"
    assert main([
        str(photo), "--remove-background", "-o", str(destination),
        "--bg-model", "balanced", "--bg-model-dir", str(models),
        "--save-mask", "--bg-feather", "0.8", "--bg-edge-shift", "-1",
        "--bg-two-pass", "--bg-crop", "--bg-padding", "20",
        "--bg-fill-color", "255,128,0", "--keep-metadata",
    ]) == 0

    config = service_calls["configs"][0]
    task = service_calls["batches"][0][0]
    assert config.output_format == "WEBP"
    assert config.model == "balanced"
    assert config.model_dir == models.resolve()
    assert config.bg_color == "#ff8000"
    assert config.feather == 0.8 and config.edge_shift == -1
    assert config.crop and config.two_pass and config.padding == 20
    assert config.keep_metadata and config.save_mask
    assert task.output_path == destination
    assert task.mask_path == tmp_path / "cutout_mask.png"


def test_recursive_background_batch_preserves_subdirectories(tmp_path, service_calls):
    source = tmp_path / "input"
    output = tmp_path / "output"
    for folder in (source / "one", source / "two"):
        folder.mkdir(parents=True)
        Image.new("RGB", (8, 8), "blue").save(folder / "same.jpg")
        (folder / "document.pdf").write_bytes(b"not an image")

    assert main([str(source), "--remove-background", "-r", "-o", str(output), "--save-mask"]) == 0

    tasks = service_calls["batches"][0]
    assert [task.output_path.relative_to(output).as_posix() for task in tasks] == [
        "one/same_nobg.png", "two/same_nobg.png",
    ]
    assert all(task.mask_path.name == "same_nobg_mask.png" for task in tasks)


def test_background_batch_uses_unique_names_for_same_stem(tmp_path, service_calls):
    Image.new("RGB", (8, 8)).save(tmp_path / "same.jpg")
    Image.new("RGB", (8, 8)).save(tmp_path / "same.png")
    (tmp_path / "same_nobg.png").write_bytes(b"existing output")

    assert main([str(tmp_path), "--remove-background"]) == 0

    tasks = service_calls["batches"][0]
    destinations = [task.output_path for task in tasks]
    assert len(destinations) == len(set(destinations))
    assert tmp_path / "same_nobg.png" not in destinations
    assert (tmp_path / "same_nobg.png").read_bytes() == b"existing output"


def test_recursive_background_excludes_nested_output_folder(tmp_path, service_calls):
    source = tmp_path / "photos"
    output = source / "cutouts"
    output.mkdir(parents=True)
    Image.new("RGB", (8, 8)).save(source / "original.jpg")
    Image.new("RGBA", (8, 8)).save(output / "old_nobg.png")

    assert main([str(source), "--remove-background", "-r", "-o", str(output)]) == 0

    tasks = service_calls["batches"][0]
    assert len(tasks) == 1
    assert tasks[0].input_path == source / "original.jpg"
    assert tasks[0].output_path == output / "original_nobg.png"


@pytest.mark.parametrize("extra", [
    ["--clean-metadata"], ["--inspect-metadata"], ["--ocr"],
    ["--width", "100"], ["--no-auto-orient"], ["--workers", "2"],
    ["--bg-color", "#fff"], ["-f", "JPG"],
    ["--keep-metadata", "--strip-metadata"],
    ["--bg-feather", "-1"], ["--bg-feather", "nan"],
    ["--bg-padding", "-1"], ["--bg-edge-shift", "6"],
])
def test_background_rejects_incompatible_or_invalid_options(photo, service_calls, extra, capsys):
    assert main([str(photo), "--remove-background", *extra]) == 1
    assert "Error:" in capsys.readouterr().err
    assert not service_calls["batches"]


@pytest.mark.parametrize("extra", [
    ["--bg-model", "fast"], ["--save-mask"], ["--bg-feather", "0"],
    ["--bg-padding", "0"], ["--keep-metadata"],
])
def test_background_options_require_mode(photo, service_calls, extra, capsys):
    assert main([str(photo), *extra]) == 1
    assert "require --remove-background" in capsys.readouterr().err
    assert not service_calls["batches"]


@pytest.mark.parametrize("destination_name", ["existing.png", "photo.png"])
def test_background_explicit_output_never_overwrites(photo, service_calls, destination_name, capsys):
    destination = photo.parent / destination_name
    if destination != photo:
        destination.write_bytes(b"preserve me")
    original = destination.read_bytes()

    assert main([str(photo), "--remove-background", "-o", str(destination)]) == 1

    assert destination.read_bytes() == original
    assert "overwrite" in capsys.readouterr().err
    assert not service_calls["configs"]


def test_background_explicit_output_rejects_existing_mask(photo, service_calls, capsys):
    destination = photo.parent / "new.png"
    mask = photo.parent / "new_mask.png"
    mask.write_bytes(b"preserve mask")

    assert main([str(photo), "--remove-background", "--save-mask", "-o", str(destination)]) == 1

    assert mask.read_bytes() == b"preserve mask"
    assert not destination.exists()
    assert "already exists" in capsys.readouterr().err
    assert not service_calls["configs"]


def test_background_rejects_extension_mismatch(photo, service_calls, capsys):
    assert main([str(photo), "--remove-background", "-f", "PNG", "-o", str(photo.parent / "out.webp")]) == 1
    assert "extension must match" in capsys.readouterr().err
    assert not service_calls["batches"]


def test_background_requires_native_image_input(tmp_path, service_calls, capsys):
    document = tmp_path / "document.pdf"
    document.write_bytes(b"%PDF-1.7")
    assert main([str(document), "--remove-background"]) == 1
    assert "Supported inputs" in capsys.readouterr().err
    assert not service_calls["batches"]


def test_background_dependency_error_is_actionable(photo, monkeypatch, capsys):
    class UnavailableService:
        def __init__(self, config):
            raise RuntimeError("Install image_converter/requirements-background.txt to enable background removal.")

    monkeypatch.setattr(background_removal, "BackgroundRemovalService", UnavailableService)
    assert main([str(photo), "--remove-background"]) == 1
    assert "requirements-background.txt" in capsys.readouterr().err


def test_background_file_failure_returns_nonzero(photo, monkeypatch, capsys):
    class FailingService:
        def __init__(self, config):
            pass

        def run_batch(self, tasks, progress_callback=None):
            result = ConversionResult(
                input_path=tasks[0].input_path,
                output_path=tasks[0].output_path,
                success=False,
                error_message="Model missing: install fast explicitly",
            )
            progress_callback(1, 1, result)
            return [result]

    monkeypatch.setattr(background_removal, "BackgroundRemovalService", FailingService)
    assert main([str(photo), "--remove-background"]) == 1
    captured = capsys.readouterr()
    assert "Model missing" in captured.err
    assert "0 succeeded, 1 failed" in captured.out
