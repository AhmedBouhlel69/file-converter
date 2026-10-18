import logging
import os
from pathlib import Path
from threading import Lock
from typing import Any

import numpy as np
import onnxruntime as ort
from numpy.typing import NDArray

from .registry import ModelConfig, ModelError

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
        options = ort.SessionOptions()
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        if "DmlExecutionProvider" in providers:
            options.enable_mem_pattern = False
        if "DmlExecutionProvider" in providers:
            options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
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
        if config.output_index >= len(self.session.get_outputs()):
            raise ModelError("Model output index does not exist")
        self.provider = self.session.get_providers()[0]
        self.lock = Lock() if self.provider == "CPUExecutionProvider" else _GPU_LOCK
        self.input_name = self.session.get_inputs()[0].name
        self.output_index = config.output_index
        dummy = np.zeros(
            (1, 3, config.input_size[1], config.input_size[0]),
            dtype=np.float16 if config.precision == "fp16" else np.float32,
        )
        for _ in range(2):
            self.run(dummy)
        logging.getLogger(__name__).info("Active provider: %s", self.provider)

    def run(self, tensor: NDArray[np.float32] | NDArray[np.float16]) -> Any:
        with self.lock:
            try:
                return self.session.run(None, {self.input_name: tensor})[self.output_index]
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
            _CACHE[key] = Engine(
                path, config, device, threads or max(1, (os.cpu_count() or 2) // 2)
            )
        engine = _CACHE[key]
    if device != "auto" and engine.provider != _PROVIDERS[device]:
        if strict:
            raise ValueError(f"Requested {device}, received {engine.provider}")
        logging.getLogger(__name__).warning("Requested %s; using %s", device, engine.provider)
    return engine
