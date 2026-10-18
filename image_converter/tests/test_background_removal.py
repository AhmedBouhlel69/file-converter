"""Background removal safety and batch behavior, without downloading models."""

from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
import pytest

from image_converter.core import background_removal as bg


@pytest.fixture
def photo(tmp_path):
    path = tmp_path / "photo.png"
    Image.new("RGB", (12, 8), "red").save(path)
    return path


@pytest.fixture
def backend(monkeypatch):
    state = SimpleNamespace(initializations=0, warmups=0, calls=[], options=[], fail_init=None,
                            fail_remove=None, on_remove=None, on_save_mask=None)

    class Removed:
        rgba = Image.new("RGBA", (12, 8), (255, 0, 0, 128))

        def save(self, path, *, overwrite=False, keep_metadata=False):
            state.options.append(("save", overwrite, keep_metadata))
            fmt = "WEBP" if Path(path).suffix == ".webp" else "PNG"
            self.rgba.save(path, format=fmt, lossless=True)

        def save_mask(self, path, *, overwrite=False):
            if state.on_save_mask:
                state.on_save_mask()
            Image.new("L", (12, 8), 128).save(path, format="PNG")

    class Remover:
        def __init__(self, **kwargs):
            state.initializations += 1
            state.init_options = kwargs
            if state.fail_init:
                raise state.fail_init

        def warmup(self):
            state.warmups += 1

        def remove(self, source, **kwargs):
            state.calls.append(source)
            state.options.append(kwargs)
            if state.on_remove:
                state.on_remove()
            if state.fail_remove:
                raise state.fail_remove
            return Removed()

    fake = SimpleNamespace(Remover=Remover, RefineOptions=lambda **kwargs: kwargs,
                           ComposeOptions=lambda **kwargs: kwargs)
    real_import = bg.importlib.import_module
    monkeypatch.setattr(bg.importlib, "import_module", lambda name, *a, **k:
                        fake if name == "bgremove" else real_import(name, *a, **k))
    return state


def test_configuration_is_validated_without_initialization(backend):
    config = bg.BackgroundRemovalConfig(output_format="webp", bg_color="#fff")
    service = bg.BackgroundRemovalService(config)
    assert service.config.output_format == "WEBP"
    assert backend.initializations == 0
    with pytest.raises(FrozenInstanceError):
        config.model = "quality"


@pytest.mark.parametrize("options", [
    {"model": "unknown"}, {"output_format": "JPEG"}, {"bg_color": "bad-color"},
    {"bg_color": "#ffffff00"}, {"padding": -1}, {"padding": True},
    {"feather": float("nan")}, {"feather": -1}, {"feather": True},
    {"edge_shift": 6}, {"edge_shift": 1.5}, {"crop": "yes"},
])
def test_invalid_configuration(options):
    with pytest.raises(ValueError):
        bg.BackgroundRemovalConfig(**options)


def test_planner_reserves_existing_outputs_masks_and_all_sources(photo, tmp_path):
    existing = tmp_path / "photo_nobg.png"
    Image.new("RGB", (3, 3)).save(existing)
    mask = tmp_path / "photo_nobg_2_mask.png"
    mask.write_bytes(b"keep")
    tasks = bg.plan_tasks([photo, existing, photo], save_mask=True)
    assert len(tasks) == 2
    assert tasks[0].output_path.name == "photo_nobg_3.png"
    assert tasks[0].mask_path.name == "photo_nobg_3_mask.png"
    assert tasks[1].output_path.name == "photo_nobg_nobg.png"
    assert mask.read_bytes() == b"keep"


def test_planner_preserves_directory_structure_and_duplicate_names(tmp_path):
    sources = []
    for folder in ("left", "right"):
        source = tmp_path / "in" / folder / "same.jpg"
        source.parent.mkdir(parents=True)
        Image.new("RGB", (4, 4)).save(source)
        sources.append(source)
    tasks = bg.plan_tasks(sources, tmp_path / "out", input_root=tmp_path / "in")
    assert [task.output_path.relative_to(tmp_path / "out").as_posix() for task in tasks] == [
        "left/same_nobg.png", "right/same_nobg.png"]
    flat = bg.plan_tasks(sources, tmp_path / "flat")
    assert [task.output_path.name for task in flat] == ["same_nobg.png", "same_nobg_2.png"]
    assert not (tmp_path / "out").exists()
    with pytest.raises(ValueError, match="outside input_root"):
        bg.plan_tasks(sources, input_root=tmp_path / "elsewhere")


def test_explicit_output_never_overwrites_and_checks_format(photo, tmp_path):
    with pytest.raises(ValueError, match="overwrite"):
        bg.plan_tasks([photo], explicit_output=photo)
    with pytest.raises(ValueError, match="extension"):
        bg.plan_tasks([photo], explicit_output=tmp_path / "out.jpg")
    output = tmp_path / "out.png"
    output.with_name("out_mask.png").write_bytes(b"existing mask")
    with pytest.raises(ValueError, match="already exists"):
        bg.plan_tasks([photo], explicit_output=output, save_mask=True)
    with pytest.raises(ValueError, match="exactly one"):
        bg.plan_tasks([], explicit_output=output)


def test_unsupported_extensions_are_rejected(photo, tmp_path):
    gif = tmp_path / "input.gif"
    Image.new("RGB", (2, 2)).save(gif)
    with pytest.raises(ValueError, match="Unsupported"):
        bg.plan_tasks([gif])
    assert ".heic" not in bg.IMAGE_EXTENSIONS
    assert ".gif" not in bg.IMAGE_EXTENSIONS


def test_process_reuses_cpu_session_and_writes_alpha_and_mask(photo, tmp_path, backend):
    second = tmp_path / "second.png"
    Image.new("RGB", (2, 2)).save(second)
    config = bg.BackgroundRemovalConfig(save_mask=True, feather=1.2, edge_shift=-1,
                                       crop=True, padding=4, two_pass=True, keep_metadata=True)
    service = bg.BackgroundRemovalService(config)
    tasks = bg.plan_tasks([photo, second], tmp_path / "out", save_mask=True)
    progress = []
    results = service.run_batch(tasks, lambda n, total, result: progress.append((n, total, result)))
    assert all(result.success for result in results)
    assert backend.initializations == backend.warmups == 1
    assert backend.init_options["device"] == "cpu"
    assert [(n, total) for n, total, _ in progress] == [(1, 2), (2, 2)]
    assert backend.options[0]["refinement"] == {"feather_sigma": 1.2, "edge_shift": -1}
    assert backend.options[0]["composition"]["crop"] is True
    assert backend.options[0]["two_pass"] is True
    assert ("save", True, True) in backend.options
    with Image.open(tasks[0].output_path) as image:
        assert image.mode == "RGBA"
        assert image.getpixel((0, 0))[3] == 128
    with Image.open(tasks[0].mask_path) as mask:
        assert mask.mode == "L"
    assert results[0].input_dimensions == (12, 8)
    assert results[0].output_size_bytes > 0
    assert photo.exists()


def test_lossless_webp_export(photo, backend):
    task = bg.plan_tasks([photo], output_format="WEBP")[0]
    result = bg.BackgroundRemovalService(bg.BackgroundRemovalConfig(output_format="WEBP")).process(task)
    assert result.success
    with Image.open(task.output_path) as image:
        assert image.format == "WEBP"
        assert image.convert("RGBA").getpixel((0, 0)) == (255, 0, 0, 128)


def test_bad_source_does_not_abort_batch_or_initialize_model_early(photo, tmp_path, backend):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not a png")
    tasks = bg.plan_tasks([bad, photo])
    results = bg.BackgroundRemovalService().run_batch(tasks)
    assert not results[0].success
    assert results[0].error_message
    assert results[1].success
    assert backend.initializations == 1
    assert backend.calls == [photo]


def test_input_size_and_pixel_caps_checked_before_model(photo, monkeypatch, backend):
    service = bg.BackgroundRemovalService()
    task = bg.plan_tasks([photo])[0]
    monkeypatch.setattr(bg, "MAX_BYTES", 1)
    result = service.process(task)
    assert not result.success and "25 MiB" in result.error_message
    monkeypatch.setattr(bg, "MAX_BYTES", 25 * 1024 * 1024)
    monkeypatch.setattr(bg, "MAX_PIXELS", 2)
    result = service.process(task)
    assert not result.success and "120 megapixels" in result.error_message
    assert backend.initializations == 0


def test_header_format_cannot_bypass_extension_filter(photo, tmp_path, backend):
    disguised = tmp_path / "disguised.png"
    Image.new("RGB", (2, 2)).save(disguised, format="GIF")
    result = bg.BackgroundRemovalService().process(bg.plan_tasks([disguised])[0])
    assert not result.success and "Unsupported image content" in result.error_message
    assert backend.initializations == 0


@pytest.mark.parametrize(("image_format", "extension"), [
    ("TIFF", ".tiff"), ("PNG", ".png"), ("WEBP", ".webp"),
])
def test_animated_and_multipage_images_rejected_before_inference(tmp_path, backend, image_format, extension):
    source = tmp_path / f"multiple{extension}"
    first = Image.new("RGBA", (12, 8), "red")
    second = Image.new("RGBA", (12, 8), "blue")
    first.save(source, format=image_format, save_all=True, append_images=[second], duration=100, loop=0)
    with Image.open(source) as image:
        assert image.n_frames == 2
    task = bg.plan_tasks([source])[0]
    result = bg.BackgroundRemovalService().process(task)
    assert not result.success
    assert "Animated or multi-page" in result.error_message
    assert backend.initializations == 0
    assert backend.calls == []
    assert not task.output_path.exists()


def test_missing_model_failure_is_cached_for_entire_batch(photo, tmp_path, backend):
    second = tmp_path / "second.png"
    Image.new("RGB", (2, 2)).save(second)
    backend.fail_init = ValueError("Model missing: fast.onnx. Copy a verified file.")
    results = bg.BackgroundRemovalService().run_batch(bg.plan_tasks([photo, second]))
    assert len(results) == 2 and not any(result.success for result in results)
    assert all("Model missing" in result.error_message for result in results)
    assert backend.initializations == 1
    assert not backend.calls


def test_missing_dependency_is_actionable_and_cached(photo, monkeypatch):
    imports = []

    def unavailable(name):
        imports.append(name)
        raise ModuleNotFoundError("No module named onnxruntime")

    monkeypatch.setattr(bg.importlib, "import_module", unavailable)
    service = bg.BackgroundRemovalService()
    task = bg.plan_tasks([photo])[0]
    first = service.process(task)
    second = service.process(task)
    assert "requirements-background.txt" in first.error_message
    assert second.error_message == first.error_message
    assert imports == ["bgremove"]


def test_cancellation_before_start_and_between_images(photo, tmp_path, backend):
    tasks = bg.plan_tasks([photo])
    service = bg.BackgroundRemovalService()
    assert service.run_batch(tasks, cancel_check=lambda: True) == []
    assert backend.initializations == 0
    second = tmp_path / "second.png"
    Image.new("RGB", (2, 2)).save(second)
    cancelled = False

    def on_progress(*args):
        nonlocal cancelled
        cancelled = True

    results = service.run_batch(bg.plan_tasks([photo, second]), on_progress, lambda: cancelled)
    assert len(results) == 1 and results[0].success
    assert backend.calls == [photo]


def test_cancel_during_inference_publishes_no_outputs(photo, tmp_path, backend):
    cancelled = False

    def cancel():
        nonlocal cancelled
        cancelled = True

    backend.on_remove = cancel
    task = bg.plan_tasks([photo], tmp_path / "out", save_mask=True)[0]
    results = bg.BackgroundRemovalService(bg.BackgroundRemovalConfig(save_mask=True)).run_batch(
        [task], cancel_check=lambda: cancelled)
    assert len(results) == 1 and not results[0].success
    assert "cancelled" in results[0].error_message
    assert not task.output_path.exists() and not task.mask_path.exists()
    assert not list((tmp_path / "out").glob(".bgremove-*"))


def test_output_race_never_overwrites_existing_file(photo, backend):
    task = bg.plan_tasks([photo])[0]
    backend.on_remove = lambda: task.output_path.write_bytes(b"external output")
    result = bg.BackgroundRemovalService().process(task)
    assert not result.success
    assert task.output_path.read_bytes() == b"external output"
    assert not list(photo.parent.glob(".bgremove-*"))


def test_mask_publish_failure_rolls_back_only_own_output(photo, monkeypatch, backend):
    task = bg.plan_tasks([photo], save_mask=True)[0]
    real_link = bg.os.link

    def raced_link(source, target):
        if Path(target) == task.mask_path:
            task.mask_path.write_bytes(b"external mask")
        real_link(source, target)

    monkeypatch.setattr(bg.os, "link", raced_link)
    result = bg.BackgroundRemovalService(bg.BackgroundRemovalConfig(save_mask=True)).process(task)
    assert not result.success
    assert not task.output_path.exists()
    assert task.mask_path.read_bytes() == b"external mask"
    assert not list(photo.parent.glob(".bgremove-*"))


def test_all_batch_inputs_are_protected_from_manual_tasks(photo, tmp_path, backend):
    second = tmp_path / "second.png"
    Image.new("RGB", (2, 2), "blue").save(second)
    original = second.read_bytes()
    tasks = [bg.BackgroundRemovalTask(photo, second),
             bg.BackgroundRemovalTask(second, tmp_path / "valid.png")]
    results = bg.BackgroundRemovalService().run_batch(tasks)
    assert not results[0].success and "overwrite an input" in results[0].error_message
    assert results[1].success
    assert second.read_bytes() == original


def test_model_directory_precedence(tmp_path, monkeypatch):
    explicit, env, bundled = (tmp_path / name for name in ("explicit", "env", "bundle"))
    (bundled / "background_models").mkdir(parents=True)
    (bundled / "background_models" / "u2netp.onnx").touch()
    monkeypatch.setenv("BGREMOVE_MODEL_DIR", str(env))
    monkeypatch.setattr(bg.sys, "_MEIPASS", str(bundled), raising=False)
    assert bg.resolve_model_directory(explicit) == explicit
    assert bg.resolve_model_directory() == env
    monkeypatch.delenv("BGREMOVE_MODEL_DIR")
    assert bg.resolve_model_directory() == bundled / "background_models"


@pytest.mark.parametrize("model", ["balanced", "quality", "portrait"])
def test_fast_only_automatic_locations_do_not_hide_other_cached_models(photo, tmp_path, monkeypatch, backend, model):
    workspace = tmp_path / "workspace"
    local_models = workspace / "backgroundG" / "models"
    local_models.mkdir(parents=True)
    (local_models / "u2netp.onnx").touch()
    bundle = tmp_path / "bundle"
    bundled_models = bundle / "background_models"
    bundled_models.mkdir(parents=True)
    (bundled_models / "u2netp.onnx").touch()
    monkeypatch.setattr(bg, "__file__", str(workspace / "image_converter" / "core" / "background_removal.py"))
    monkeypatch.setattr(bg.sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.delenv("BGREMOVE_MODEL_DIR", raising=False)
    assert bg.resolve_model_directory(model="fast") == bundled_models
    assert bg.resolve_model_directory(model=model) is None
    result = bg.BackgroundRemovalService(bg.BackgroundRemovalConfig(model=model)).process(bg.plan_tasks([photo])[0])
    assert result.success
    assert backend.init_options["model"] == model
    assert backend.init_options["model_dir"] is None
    # Explicit directories are retained even when their model is absent.
    assert bg.resolve_model_directory(local_models, model) == local_models
    monkeypatch.setenv("BGREMOVE_MODEL_DIR", str(local_models))
    assert bg.resolve_model_directory(model=model) == local_models
