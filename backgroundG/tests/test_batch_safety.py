from collections.abc import Callable, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Self

import pytest

from bgremove import batch
from bgremove.batch import BatchItem, BatchOptions, BatchResult, plan_batch, run_batch


def _touch(path: Path, data: bytes = b"original") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _symlink(link: Path, target: Path, *, directory: bool = False) -> None:
    try:
        link.symlink_to(target, target_is_directory=directory)
    except OSError as error:
        pytest.skip(f"Creating symlinks is unavailable: {error}")


class FakeResult:
    def __init__(self, after_image: Callable[[], None] | None = None) -> None:
        self.after_image = after_image

    def save(self, path: Path, **kwargs: Any) -> None:
        _touch(path, b"image")
        if self.after_image is not None:
            self.after_image()

    def save_mask(self, path: Path, **kwargs: Any) -> None:
        _touch(path, b"mask")


class FakeRemover:
    def __init__(
        self,
        during_remove: Callable[[], None] | None = None,
        after_image: Callable[[], None] | None = None,
    ) -> None:
        self.during_remove = during_remove
        self.result = FakeResult(after_image)

    def remove(self, source: Path, **kwargs: Any) -> FakeResult:
        if self.during_remove is not None:
            self.during_remove()
        return self.result

    def warmup(self) -> SimpleNamespace:
        return SimpleNamespace(provider="CPUExecutionProvider")


def test_output_ancestor_of_input_does_not_exclude_inputs(tmp_path: Path) -> None:
    source = tmp_path / "input"
    first = _touch(source / "photo.jpg")
    second = _touch(source / "nested/other.png")
    items = plan_batch([source], tmp_path, recursive=True)
    assert [item.source for item in items] == [second, first]
    assert {item.image for item in items} == {
        tmp_path / "photo_nobg.png",
        tmp_path / "nested/other_nobg.png",
    }


def test_recursive_output_subtree_is_excluded(tmp_path: Path) -> None:
    source = tmp_path / "input"
    photo = _touch(source / "nested/photo.jpg")
    output = source / "out"
    _touch(output / "older_nobg.png")
    _touch(output / "nested/older_mask.png")
    items = plan_batch([source], output, recursive=True)
    assert [item.source for item in items] == [photo]
    assert items[0].output_root == output.resolve()


@pytest.mark.parametrize("recursive", [False, True])
def test_same_input_output_directory_is_rejected(tmp_path: Path, recursive: bool) -> None:
    _touch(tmp_path / "photo.png")
    with pytest.raises(ValueError, match="folders must differ"):
        plan_batch([tmp_path], tmp_path, recursive=recursive)


def test_duplicate_sources_are_processed_once(tmp_path: Path) -> None:
    source = _touch(tmp_path / "source/photo.png")
    items = plan_batch([source, source, source.parent], tmp_path / "out")
    assert len(items) == 1


@pytest.mark.parametrize("overwrite,skip", [(False, False), (True, False), (False, True)])
def test_later_source_cannot_be_overwritten_under_any_option(
    tmp_path: Path, overwrite: bool, skip: bool
) -> None:
    source = _touch(tmp_path / "photo.jpg")
    protected = _touch(tmp_path / "out/photo_nobg.png", b"protected")
    with pytest.raises(ValueError, match="overwrite an input"):
        plan_batch([source, protected], tmp_path / "out", overwrite=overwrite, skip_existing=skip)
    assert protected.read_bytes() == b"protected"


def test_resume_keeps_collision_detection_for_skipped_outputs(tmp_path: Path) -> None:
    first = _touch(tmp_path / "a/photo.jpg")
    second = _touch(tmp_path / "b/photo.png")
    output = tmp_path / "out"
    _touch(output / "photo_nobg.png")
    with pytest.raises(ValueError, match="collision"):
        plan_batch([first, second], output, skip_existing=True)


def test_partial_resume_only_plans_missing_mask(tmp_path: Path) -> None:
    source = _touch(tmp_path / "photo.jpg")
    output = tmp_path / "out"
    _touch(output / "photo_nobg.png", b"completed")
    item = plan_batch([source], output, save_mask=True, skip_existing=True)[0]
    assert item.image is None
    assert item.mask == output / "photo_mask.png"
    assert (output / "photo_nobg.png").read_bytes() == b"completed"


@pytest.mark.parametrize("skip_existing", [False, True])
def test_existing_output_directory_is_not_a_completed_file(
    tmp_path: Path, skip_existing: bool
) -> None:
    source = _touch(tmp_path / "photo.jpg")
    (tmp_path / "out/photo_nobg.png").mkdir(parents=True)
    with pytest.raises(ValueError, match="not a regular file"):
        plan_batch([source], tmp_path / "out", skip_existing=skip_existing)


def test_output_root_must_be_a_directory(tmp_path: Path) -> None:
    source = _touch(tmp_path / "photo.jpg")
    output = _touch(tmp_path / "out")
    with pytest.raises(ValueError, match="not a folder"):
        plan_batch([source], output)


def test_input_symlink_cannot_escape_selected_directory(tmp_path: Path) -> None:
    source = tmp_path / "input"
    source.mkdir()
    outside = _touch(tmp_path / "private/photo.png")
    _symlink(source / "photo.png", outside)
    with pytest.raises(ValueError, match="Input symlink escapes"):
        plan_batch([source], tmp_path / "out")


def test_output_parent_symlink_cannot_escape_root(tmp_path: Path) -> None:
    source = _touch(tmp_path / "input/nested/photo.png")
    output = tmp_path / "out"
    output.mkdir()
    outside = tmp_path / "private"
    outside.mkdir()
    _symlink(output / "nested", outside, directory=True)
    with pytest.raises(ValueError, match="escapes output directory"):
        plan_batch([source.parent.parent], output, recursive=True, overwrite=True)


def test_broken_output_symlink_is_rejected_in_resume(tmp_path: Path) -> None:
    source = _touch(tmp_path / "photo.png")
    output = tmp_path / "out"
    output.mkdir()
    _symlink(output / "photo_nobg.png", output / "missing.png")
    with pytest.raises(ValueError, match="symlinks are not supported"):
        plan_batch([source], output, skip_existing=True)


def test_runtime_output_directory_swap_is_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _touch(tmp_path / "input/photo.png")
    output = tmp_path / "out"
    output.mkdir()
    outside = tmp_path / "private"
    protected = _touch(outside / "photo_nobg.png", b"protected")
    items = plan_batch([source], output, overwrite=True)
    redirected = False
    original_resolve = Path.resolve

    def resolve(path: Path, strict: bool = False) -> Path:
        if redirected and path.is_relative_to(output):
            return original_resolve(outside / path.relative_to(output), strict=strict)
        return original_resolve(path, strict=strict)

    def swap() -> None:
        nonlocal redirected
        redirected = True

    # Simulate the resolution change without requiring Windows symlink privileges.
    monkeypatch.setattr(Path, "resolve", resolve)
    monkeypatch.setattr(batch, "Remover", lambda **config: FakeRemover(swap))
    results = run_batch(items, {"device": "cpu"}, BatchOptions(overwrite=True))
    assert results[0].status == "failed"
    assert "escapes output directory" in (results[0].error or "")
    assert protected.read_bytes() == b"protected"


def test_mask_target_is_rechecked_after_image_is_saved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _touch(tmp_path / "input/photo.png")
    output = tmp_path / "out"
    protected = _touch(output / "other.png", b"protected")
    items = plan_batch([source, protected], output, save_mask=True)
    redirected = False
    original_resolve = Path.resolve

    def resolve(path: Path, strict: bool = False) -> Path:
        if redirected and path == output / "photo_mask.png":
            return original_resolve(protected, strict=strict)
        return original_resolve(path, strict=strict)

    def swap_mask() -> None:
        nonlocal redirected
        redirected = True

    monkeypatch.setattr(Path, "resolve", resolve)
    # Exercise one item while retaining the complete source set supplied to workers.
    result = batch._process(
        FakeRemover(after_image=swap_mask),  # type: ignore[arg-type]
        items[0],
        BatchOptions(overwrite=True),
        frozenset(item.source.resolve() for item in items),
    )
    assert result.status == "failed"
    assert "overwrite an input" in (result.error or "")
    assert protected.read_bytes() == b"protected"
    assert (output / "photo_nobg.png").read_bytes() == b"image"


@pytest.mark.parametrize("jobs", [True, False, 0, -1, 1.5, "2", 5])
def test_invalid_job_counts_are_rejected(jobs: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(batch, "physical_cores", lambda: 4)
    with pytest.raises(ValueError, match="Jobs must"):
        run_batch([], {}, BatchOptions(), jobs=jobs)


@pytest.mark.parametrize("threads", [True, False, -1, 1.5, "2", None])
def test_invalid_thread_counts_are_rejected(threads: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(batch, "physical_cores", lambda: 4)
    with pytest.raises(ValueError, match="Threads must"):
        run_batch([], {"threads": threads}, BatchOptions())


@pytest.mark.parametrize("jobs,threads", [(1, 5), (2, 3), (4, 2)])
def test_worker_thread_budget_is_enforced(
    jobs: int, threads: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(batch, "physical_cores", lambda: 4)
    with pytest.raises(ValueError, match="Jobs times threads"):
        run_batch([], {"threads": threads}, BatchOptions(), jobs=jobs)


def test_fully_resumed_batch_does_not_initialize_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _touch(tmp_path / "photo.png")
    _touch(tmp_path / "out/photo_nobg.png")
    items = plan_batch([source], tmp_path / "out", skip_existing=True)

    def forbidden(**config: Any) -> None:
        raise AssertionError("Skipped images should not initialize a model")

    monkeypatch.setattr(batch, "Remover", forbidden)
    assert [result.status for result in run_batch(items, {}, BatchOptions())] == ["skipped"]


def test_manual_batch_items_cannot_overwrite_an_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _touch(tmp_path / "photo.png", b"protected")
    with pytest.raises(ValueError, match="overwrite an input"):
        run_batch([BatchItem(source, source, None)], {}, BatchOptions(overwrite=True))
    assert source.read_bytes() == b"protected"


def test_parallel_gpu_is_rejected_before_creating_process_pool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _touch(tmp_path / "photo.png")
    items = plan_batch([source], tmp_path / "out")
    monkeypatch.setattr(batch, "physical_cores", lambda: 4)
    gpu = FakeRemover()
    monkeypatch.setattr(gpu, "warmup", lambda: SimpleNamespace(provider="CUDAExecutionProvider"))
    monkeypatch.setattr(batch, "Remover", lambda **config: gpu)

    def forbidden_pool(**kwargs: Any) -> None:
        raise AssertionError("GPU inference must not enter a process pool")

    monkeypatch.setattr(batch, "ProcessPoolExecutor", forbidden_pool)
    with pytest.raises(ValueError, match="parallel workers require CPU"):
        run_batch(items, {"device": "auto"}, BatchOptions(), jobs=2)


def test_cpu_pool_uses_spawn_and_receives_cpu_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _touch(tmp_path / "photo.png")
    items = plan_batch([source], tmp_path / "out")
    monkeypatch.setattr(batch, "physical_cores", lambda: 4)
    monkeypatch.setattr(batch, "Remover", lambda **config: FakeRemover())
    received: dict[str, Any] = {}

    class FakePool:
        def __init__(self, **kwargs: Any) -> None:
            received.update(kwargs)

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def map(self, worker: Any, work: list[BatchItem]) -> Iterator[BatchResult]:
            return iter(BatchResult(str(item.source), "saved") for item in work)

    monkeypatch.setattr(batch, "ProcessPoolExecutor", FakePool)
    config = {"device": "auto", "threads": 0}
    result = run_batch(items, config, BatchOptions(), jobs=2)
    assert result[0].status == "saved"
    assert config == {"device": "auto", "threads": 0}
    assert received["mp_context"].get_start_method() == "spawn"
    worker_config, _, worker_sources = received["initargs"]
    assert worker_config["device"] == "cpu"
    assert worker_config["threads"] == 2
    assert worker_sources == frozenset({source.resolve()})
