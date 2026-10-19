"""Large CPU profiles fail clearly before allocating an ONNX session."""

from types import SimpleNamespace
from pathlib import Path

import numpy as np
import pytest

from bgremove import engine
from bgremove.registry import ModelError, read_registry


@pytest.fixture
def cpu_session(monkeypatch):
    state = SimpleNamespace(available=engine.MIN_LARGE_CPU_FREE_BYTES, sessions=0, runs=0)
    configs = read_registry()
    selected = configs["quality"]
    state.config = selected

    class Session:
        def __init__(self, path, options, providers):
            state.sessions += 1

        def get_inputs(self):
            w, h = state.config.input_size
            return [SimpleNamespace(type="tensor(float)", shape=[1, 3, h, w], name="input")]

        def get_outputs(self):
            return [SimpleNamespace(name="mask")]

        def get_providers(self):
            return ["CPUExecutionProvider"]

        def run(self, names, inputs):
            state.runs += 1
            return [np.zeros((1, 1, 1, 1), dtype=np.float32)]

    monkeypatch.setattr(engine.psutil, "virtual_memory", lambda: SimpleNamespace(available=state.available))
    monkeypatch.setattr(engine.ort, "get_available_providers", lambda: ["CPUExecutionProvider"])
    monkeypatch.setattr(engine.ort, "InferenceSession", Session)
    monkeypatch.setattr(engine, "_CACHE", {})
    return state


@pytest.mark.parametrize("profile", ["quality", "portrait"])
def test_large_profile_rejects_insufficient_free_memory_before_session(cpu_session, profile):
    cpu_session.available = engine.MIN_LARGE_CPU_FREE_BYTES - 1
    config = read_registry()[profile]
    with pytest.raises(ModelError, match="8 GiB.*Fast or Balanced"):
        engine.Engine(Path(profile + ".onnx"), config, "cpu", 2)
    assert cpu_session.sessions == 0
    assert cpu_session.runs == 0


@pytest.mark.parametrize("profile", ["fast", "balanced"])
def test_small_profiles_keep_existing_behavior(cpu_session, profile):
    cpu_session.available = 512 * 1024**2
    cpu_session.config = read_registry()[profile]
    engine.Engine(Path(profile + ".onnx"), cpu_session.config, "cpu", 2)
    assert cpu_session.sessions == 1
    assert cpu_session.runs == 0


def test_large_profile_can_initialize_at_headroom_boundary(cpu_session):
    engine.Engine(Path("quality.onnx"), cpu_session.config, "cpu", 2)
    assert cpu_session.sessions == 1
    assert cpu_session.runs == 0


def test_idle_cache_is_released_before_memory_preflight(cpu_session):
    cpu_session.available = 1024**3

    class IdleEngine:
        def __del__(self):
            cpu_session.available = engine.MIN_LARGE_CPU_FREE_BYTES

    engine._CACHE[("old", "cpu", 2, read_registry()["fast"])] = IdleEngine()
    current = engine.get_engine(Path("quality.onnx"), cpu_session.config, "cpu", threads=2)
    assert list(engine._CACHE.values()) == [current]
    assert cpu_session.sessions == 1
