import hashlib
import json

import onnx
import pytest
from onnx import TensorProto, helper


@pytest.fixture
def model(tmp_path):
    graph = helper.make_graph(
        [helper.make_node("ReduceMean", ["input"], ["output"], axes=[1], keepdims=1)],
        "test-only",
        [helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, 3, 8, 8])],
        [helper.make_tensor_value_info("output", TensorProto.FLOAT, [1, 1, 8, 8])],
    )
    network = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    network.ir_version = 9
    path = tmp_path / "test.onnx"
    onnx.save(network, path)
    config = {
        "name": "synthetic",
        "file": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "input_size": [8, 8],
        "mean": [0, 0, 0],
        "std": [1, 1, 1],
        "commercial_use": True,
        "licence": "test fixture",
    }
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"balanced": config}))
    return registry, tmp_path
