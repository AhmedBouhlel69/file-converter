import logging
import os
from pathlib import Path
from threading import Lock
from typing import Any

import numpy as np
import onnxruntime as ort
import psutil
from numpy.typing import NDArray

from .registry import ModelConfig, ModelError
from .resource_policy import DEFAULT_CPU_THREADS, LARGE_MODEL_BYTES, MIN_LARGE_CPU_FREE_BYTES

_PROVIDERS = {
    "cuda": "CUDAExecutionProvider",
    "coreml": "CoreMLExecutionProvider",
    "dml": "DmlExecutionProvider",
    "cpu": "CPUExecutionProvider",
}
_CACHE: dict[tuple[str, str, int, ModelConfig], "Engine"] = {}
_CACHE_LOCK = Lock()
_GPU_LOCK = Lock()


class Engine:
    def __init__(self, path: Path, config: ModelConfig, device: str, threads: int) -> None:
        available = ort.get_available_providers()
        wanted = list(_PROVIDERS.values()) if device == "auto" else [_PROVIDERS[device]]
        providers = [p for p in wanted if p in available and p != "CPUExecutionProvider"]
        providers.append("CPUExecutionProvider")
        if (
            providers[0] == "CPUExecutionProvider"
            and config.size_bytes is not None
            and config.size_bytes >= LARGE_MODEL_BYTES
        ):
            # The registered BiRefNet profiles exhausted this 16 GB machine
            # with 5–6.5 GiB available during guarded warmup. This preflight
            # runs after get_engine releases any idle previous-model cache.
            available_bytes = psutil.virtual_memory().available
            if available_bytes < MIN_LARGE_CPU_FREE_BYTES:
                raise ModelError(
                    "This large model needs at least 8 GiB of free RAM for CPU processing "
                    f"({available_bytes / 1024**3:.1f} GiB available). "
                    "Close other memory-heavy apps, or choose Fast or Balanced."
                )
        options = ort.SessionOptions()
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        # Desktop jobs should sleep while idle instead of burning cycles waiting
        # for the next image. Explicit thread requests remain supported.
        options.add_session_config_entry("session.intra_op.allow_spinning", "0")
        options.add_session_config_entry("session.inter_op.allow_spinning", "0")
        if providers[0] == "CPUExecutionProvider":
            # Avoid retaining the peak activation arena between desktop images.
            # Keep tensor lifetime reuse and graph optimizations enabled.
            options.enable_cpu_mem_arena = False
            options.enable_mem_pattern = False
        if "DmlExecutionProvider" in providers:
            options.enable_mem_pattern = False
        try:
            self.session = ort.InferenceSession(str(path), options, providers=providers)
        except Exception as exc:
            raise ModelError(f"Cannot load ONNX model {path.name}: {exc}") from exc
        inputs = self.session.get_inputs()
        if len(inputs) != 1:
            raise ModelError("Model must have exactly one NCHW input tensor")
        tensor = inputs[0]
        expected = (1, 3, config.input_size[1], config.input_size[0])
        dtype = "tensor(float16)" if config.precision == "fp16" else "tensor(float)"
        if (
            tensor.type != dtype
            or len(tensor.shape) != 4
            or any(
                isinstance(actual, int) and actual != wanted
                for actual, wanted in zip(tensor.shape, expected, strict=True)
            )
        ):
            raise ModelError("Model input shape or precision does not match its registry entry")
        outputs = self.session.get_outputs()
        if config.output_index >= len(outputs):
            raise ModelError("Model output index does not exist")
        self.provider = self.session.get_providers()[0]
        self.lock = Lock() if self.provider == "CPUExecutionProvider" else _GPU_LOCK
        self.input_name = self.session.get_inputs()[0].name
        self.output_index = config.output_index
        self.output_name = outputs[config.output_index].name
        logging.getLogger(__name__).info("Active provider: %s", self.provider)

    def run(self, tensor: NDArray[np.float32] | NDArray[np.float16]) -> Any:
        with self.lock:
            try:
                # U2Net exposes auxiliary masks used during training. Request
                # only the registered final mask instead of materializing all.
                return self.session.run([self.output_name], {self.input_name: tensor})[0]
            except Exception as exc:
                raise RuntimeError(f"ONNX inference failed: {exc}") from exc


def get_engine(
    path: Path, config: ModelConfig, device: str = "auto", strict: bool = False, threads: int = 0
) -> Engine:
    if device not in {"auto", *_PROVIDERS}:
        raise ValueError(f"Unknown device: {device}")
    if threads < 0:
        raise ValueError("Threads must be nonnegative")
    if strict and device != "auto" and _PROVIDERS[device] not in ort.get_available_providers():
        raise ValueError(f"Requested device {device} is unavailable")
    key = (str(path.resolve()), device, threads, config)
    with _CACHE_LOCK:
        if key not in _CACHE:
            # Retain only the selected model. Drop idle cache ownership before
            # loading its replacement: BiRefNet sessions can consume several GB.
            # An engine already in use remains alive through its caller's local
            # reference, so switching never closes another active inference.
            _CACHE.clear()
            _CACHE[key] = Engine(
                path, config, device, threads or min(DEFAULT_CPU_THREADS, os.cpu_count() or 1)
            )
        engine = _CACHE[key]
    if device != "auto" and engine.provider != _PROVIDERS[device]:
        if strict:
            raise ValueError(f"Requested {device}, received {engine.provider}")
        logging.getLogger(__name__).warning("Requested %s; using %s", device, engine.provider)
    return engine


def release_engine_cache() -> int:
    """Release cached session ownership after a batch and return the count.

    Sessions held by an active caller remain valid until that caller releases
    them. This does not interrupt inference or forcibly close shared sessions.
    """
    with _CACHE_LOCK:
        count = len(_CACHE)
        _CACHE.clear()
    return count
