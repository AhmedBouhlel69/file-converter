"""Resource defaults preserve masks and avoid unnecessary inference/output copies."""
from dataclasses import replace

import cv2
import numpy as np
import onnx
from onnx import TensorProto, helper
import onnxruntime as ort
import pytest

from bgremove import engine
from bgremove.preprocess import preprocess
from bgremove.registry import ModelConfig, read_registry


def test_session_load_does_not_infer_and_fetches_only_selected_output(tmp_path, monkeypatch):
    path = tmp_path / "multi-output.onnx"
    graph = helper.make_graph(
        [helper.make_node("Identity", ["input"], ["features"]),
         helper.make_node("ReduceMean", ["input"], ["mask"], axes=[1], keepdims=1)],
        "two-real-outputs",
        [helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, 3, 4, 8])],
        [helper.make_tensor_value_info("features", TensorProto.FLOAT, [1, 3, 4, 8]),
         helper.make_tensor_value_info("mask", TensorProto.FLOAT, [1, 1, 4, 8])],
    )
    network = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    network.ir_version = 9
    onnx.save(network, path)
    original = ort.InferenceSession
    requested = []
    observed_options = []

    def record_session(path, options, providers):
        observed_options.append(options)
        session = original(path, options, providers=providers)
        run = session.run

        def record_run(outputs, feeds):
            requested.append(outputs)
            return run(outputs, feeds)

        session.run = record_run
        return session

    monkeypatch.setattr(engine.ort, "InferenceSession", record_session)
    config = ModelConfig("test", path.name, "", (8, 4), (0, 0, 0), (1, 1, 1), output_index=1)
    active = engine.Engine(path, config, "cpu", 2)
    assert requested == []  # Creating a session must not allocate inference activations.
    tensor = np.arange(96, dtype=np.float32).reshape(1, 3, 4, 8)
    output = active.run(tensor)
    assert requested == [["mask"]]
    np.testing.assert_array_equal(output, np.mean(tensor, axis=1, keepdims=True))
    options = observed_options[0]
    assert options.intra_op_num_threads == 2
    assert options.inter_op_num_threads == 1
    assert options.execution_mode == ort.ExecutionMode.ORT_SEQUENTIAL
    assert not options.enable_cpu_mem_arena
    assert not options.enable_mem_pattern
    assert options.enable_mem_reuse
    assert options.graph_optimization_level == ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    for kind in ("intra", "inter"):
        assert options.get_session_config_entry(f"session.{kind}_op.allow_spinning") == "0"


@pytest.mark.parametrize("profile", ["fast", "balanced", "quality", "portrait"])
@pytest.mark.parametrize("precision", ["fp32", "fp16"])
@pytest.mark.parametrize("pixels", ["random", "black", "constant"])
def test_preprocess_preserves_registered_normalization(profile, precision, pixels):
    config = replace(read_registry()[profile], precision=precision)
    if pixels == "random":
        rgb = np.random.default_rng(1729).integers(0, 256, (31, 47, 3), dtype=np.uint8)
    else:
        rgb = np.full((31, 47, 3), 0 if pixels == "black" else 87, dtype=np.uint8)
    original = rgb.copy()
    # The release normalization formula is the quality contract: exact values,
    # registered dimensions and layout must survive the buffer-reuse change.
    x = cv2.resize(rgb, config.input_size, interpolation=cv2.INTER_LINEAR).astype(np.float32)
    divisor = max(float(np.max(x)), 1.0) if config.normalize_max else 255.0
    normalized = (x / divisor - np.array(config.mean, dtype=np.float32)) / np.array(
        config.std, dtype=np.float32
    )
    expected = np.ascontiguousarray(
        normalized.transpose(2, 0, 1)[None],
        dtype=np.float16 if precision == "fp16" else np.float32,
    )
    actual = preprocess(rgb, config)
    assert actual.flags.c_contiguous
    np.testing.assert_array_equal(actual, expected)
    np.testing.assert_array_equal(rgb, original)
