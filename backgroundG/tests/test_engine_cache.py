"""Bounded model ownership without allocating real ONNX sessions."""

import gc
from pathlib import Path
import weakref

import pytest

from bgremove import engine
from bgremove.registry import read_registry


@pytest.fixture
def fake_engines(monkeypatch):
    created = []
    before_create = []
    fail = set()

    class FakeEngine:
        provider = "CPUExecutionProvider"

        def __init__(self, path, config, device, threads):
            for callback in before_create:
                callback()
            if path.name in fail:
                raise RuntimeError("Cannot initialize model")
            self.path = path
            self.threads = threads
            created.append(weakref.ref(self))

        def run(self, value):
            return value

    monkeypatch.setattr(engine, "_CACHE", {})
    monkeypatch.setattr(engine, "Engine", FakeEngine)
    return created, before_create, fail


def test_repeated_images_reuse_selected_engine(fake_engines):
    config = read_registry()["fast"]
    first = engine.get_engine(Path("fast.onnx"), config, "cpu", threads=2)
    second = engine.get_engine(Path("fast.onnx"), config, "cpu", threads=2)
    assert first is second
    assert len(fake_engines[0]) == 1
    assert len(engine._CACHE) == 1


def test_switch_releases_idle_session_before_allocating_next(fake_engines):
    configs = read_registry()
    previous = engine.get_engine(Path("fast.onnx"), configs["fast"], "cpu", threads=2)
    previous_ref = weakref.ref(previous)
    del previous

    def assert_previous_released():
        gc.collect()
        assert previous_ref() is None
        assert not engine._CACHE

    fake_engines[1].append(assert_previous_released)
    current = engine.get_engine(Path("balanced.onnx"), configs["balanced"], "cpu", threads=2)
    assert list(engine._CACHE.values()) == [current]


def test_switch_keeps_an_externally_active_engine_valid(fake_engines):
    configs = read_registry()
    active = engine.get_engine(Path("fast.onnx"), configs["fast"], "cpu", threads=2)
    for name in ("balanced", "quality", "portrait"):
        current = engine.get_engine(Path(name + ".onnx"), configs[name], "cpu", threads=2)
        assert list(engine._CACHE.values()) == [current]
        assert active.run("still running") == "still running"
    assert len(fake_engines[0]) == 4


def test_failed_replacement_does_not_retain_old_or_partial_engine(fake_engines):
    configs = read_registry()
    old = engine.get_engine(Path("fast.onnx"), configs["fast"], "cpu", threads=2)
    old_ref = weakref.ref(old)
    del old
    fake_engines[2].add("balanced.onnx")
    with pytest.raises(RuntimeError, match="Cannot initialize model"):
        engine.get_engine(Path("balanced.onnx"), configs["balanced"], "cpu", threads=2)
    gc.collect()
    assert old_ref() is None
    assert not engine._CACHE


def test_missing_strict_provider_does_not_discard_ready_session(fake_engines, monkeypatch):
    config = read_registry()["fast"]
    current = engine.get_engine(Path("fast.onnx"), config, "cpu", threads=2)
    monkeypatch.setattr(engine.ort, "get_available_providers", lambda: ["CPUExecutionProvider"])
    with pytest.raises(ValueError, match="unavailable"):
        engine.get_engine(Path("gpu.onnx"), config, "cuda", strict=True)
    assert list(engine._CACHE.values()) == [current]


def test_release_drops_idle_ownership_and_is_idempotent(fake_engines):
    active = engine.get_engine(Path("fast.onnx"), read_registry()["fast"], "cpu", threads=2)
    previous_ref = weakref.ref(active)
    del active
    assert engine.release_engine_cache() == 1
    gc.collect()
    assert previous_ref() is None
    assert engine.release_engine_cache() == 0


def test_release_keeps_externally_active_engine_valid(fake_engines):
    active = engine.get_engine(Path("fast.onnx"), read_registry()["fast"], "cpu", threads=2)
    assert engine.release_engine_cache() == 1
    assert active.run("unfinished image") == "unfinished image"
    replacement = engine.get_engine(Path("fast.onnx"), read_registry()["fast"], "cpu", threads=2)
    assert replacement is not active


@pytest.mark.parametrize("cores, expected", [(12, 2), (1, 1), (None, 1)])
def test_default_thread_budget_does_not_claim_all_cores(fake_engines, monkeypatch, cores, expected):
    monkeypatch.setattr(engine.os, "cpu_count", lambda: cores)
    active = engine.get_engine(Path("fast.onnx"), read_registry()["fast"], "cpu")
    assert active.threads == expected


def test_explicit_thread_budget_is_preserved(fake_engines):
    active = engine.get_engine(Path("fast.onnx"), read_registry()["fast"], "cpu", threads=4)
    assert active.threads == 4
