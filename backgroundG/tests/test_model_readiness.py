"""Readiness verifies small local fixtures without constructing ONNX sessions."""

import hashlib
import json
from dataclasses import asdict
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from bgremove import readiness
from bgremove.cli import app
from bgremove.registry import ModelConfig


@pytest.fixture
def local_models(tmp_path, monkeypatch):
    state = SimpleNamespace(available=8 * 1024**3, total=16 * 1024**3)
    configs = {}
    for profile, payload in (("fast", b"tiny"), ("quality", b"large-fixture")):
        path = tmp_path / f"{profile}.onnx"
        path.write_bytes(payload)
        configs[profile] = ModelConfig(
            name=f"{profile}-fixture",
            file=path.name,
            sha256=hashlib.sha256(payload).hexdigest(),
            input_size=(8, 8),
            mean=(0, 0, 0),
            std=(1, 1, 1),
            commercial_use=True,
            licence="Test fixture only",
            size_bytes=len(payload),
        )
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({key: asdict(value) for key, value in configs.items()}))
    state.registry, state.directory = registry, tmp_path
    # Exercise the exact large/small decision with byte-sized test fixtures.
    monkeypatch.setattr(readiness, "LARGE_MODEL_BYTES", 10)
    monkeypatch.setattr(readiness.psutil, "virtual_memory", lambda: state)
    monkeypatch.setattr(readiness.ort, "get_available_providers", lambda: ["CPUExecutionProvider"])

    def forbidden(*args, **kwargs):
        raise AssertionError("Readiness must never create an ONNX session")

    monkeypatch.setattr(readiness.ort, "InferenceSession", forbidden)
    return state


def check(state, profile=None, **kwargs):
    return readiness.check_models(profile, state.registry, state.directory, **kwargs)


def test_verified_models_at_memory_boundary_are_ready_without_inference(local_models):
    report = check(local_models)
    assert report["schema_version"] == 1
    assert report["inference_tested"] is False
    assert report["device"] == "cpu"
    assert report["exit_code"] == 0
    assert report["available_memory_bytes"] == 8 * 1024**3
    assert report["policy"]["min_large_cpu_free_bytes"] == 8 * 1024**3
    assert all(
        item["installed"] and item["verified"] and item["cpu_ready"] for item in report["profiles"]
    )
    assert report["profiles"][0]["required_free_memory_bytes"] == 0
    assert report["profiles"][1]["required_free_memory_bytes"] == 8 * 1024**3
    assert all("not been tested" in item["reason"] for item in report["profiles"])


def test_verified_large_model_is_ram_blocked_but_small_model_remains_ready(local_models):
    local_models.available -= 1
    report = check(local_models)
    small, large = report["profiles"]
    assert small["status"] == "ready"
    assert large["status"] == "resource_blocked"
    assert large["verified"] and large["installed"] and not large["cpu_ready"]
    assert "8 GiB" in large["reason"]
    assert report["exit_code"] == readiness.readiness_exit_code(report) == 5


def test_missing_artifact_is_reported_and_takes_precedence_over_ram_block(local_models):
    (local_models.directory / "fast.onnx").unlink()
    local_models.available -= 1
    report = check(local_models)
    missing = report["profiles"][0]
    assert missing["status"] == "missing"
    assert not missing["installed"] and not missing["verified"] and not missing["cpu_ready"]
    assert missing["actual_size_bytes"] is None
    assert "models pull fast" in missing["reason"]
    assert report["profiles"][1]["status"] == "resource_blocked"
    assert report["exit_code"] == 3


@pytest.mark.parametrize(
    "payload,reason", [(b"oops", "hash mismatch"), (b"too-long", "size mismatch")]
)
def test_corrupt_artifacts_cannot_be_ready(local_models, payload, reason):
    (local_models.directory / "fast.onnx").write_bytes(payload)
    report = check(local_models, "fast")
    item = report["profiles"][0]
    assert item["status"] == "corrupt"
    assert item["installed"] and not item["verified"] and not item["cpu_ready"]
    assert reason in item["reason"]
    assert report["exit_code"] == 3


def test_license_policy_requires_explicit_opt_in(local_models):
    data = json.loads(local_models.registry.read_text())
    data["fast"]["commercial_use"] = False
    local_models.registry.write_text(json.dumps(data))
    denied = check(local_models, "fast")
    assert denied["exit_code"] == 3
    assert denied["profiles"][0]["status"] == "invalid"
    assert "--allow-noncommercial" in denied["profiles"][0]["reason"]
    assert check(local_models, "fast", allow_noncommercial=True)["exit_code"] == 0


def test_unregistered_hash_is_not_accepted(local_models):
    data = json.loads(local_models.registry.read_text())
    data["fast"]["sha256"] = ""
    local_models.registry.write_text(json.dumps(data))
    report = check(local_models, "fast")
    assert report["exit_code"] == 3
    assert "Register a verified SHA-256" in report["profiles"][0]["reason"]


def test_unavailable_cpu_provider_blocks_verified_artifact(local_models, monkeypatch):
    monkeypatch.setattr(
        readiness.ort, "get_available_providers", lambda: ["AzureExecutionProvider"]
    )
    report = check(local_models, "fast")
    item = report["profiles"][0]
    assert report["cpu_provider_available"] is False
    assert item["verified"] and not item["cpu_ready"]
    assert item["status"] == "provider_unavailable"
    assert report["exit_code"] == 3


def test_unreadable_model_is_reported(local_models, monkeypatch):
    def denied(*args, **kwargs):
        raise PermissionError("fixture access denied")

    monkeypatch.setattr(readiness, "verify_model", denied)
    report = check(local_models, "fast")
    assert report["profiles"][0]["status"] == "invalid"
    assert "access denied" in report["profiles"][0]["reason"]
    assert report["exit_code"] == 3


def test_unknown_selection_is_an_argument_error(local_models):
    with pytest.raises(ValueError, match="Unknown model profile"):
        check(local_models, "unknown")


def cli_args(state):
    return ["--registry", str(state.registry), "--model-dir", str(state.directory)]


def test_cli_json_is_parseable_with_resource_exit_code(local_models):
    local_models.available -= 1
    result = CliRunner().invoke(app, ["models", "check", *cli_args(local_models), "--json"])
    assert result.exit_code == 5, result.output
    report = json.loads(result.stdout)
    assert report["inference_tested"] is False
    assert [item["status"] for item in report["profiles"]] == ["ready", "resource_blocked"]


def test_cli_human_output_explains_readiness_and_selected_profile(local_models):
    result = CliRunner().invoke(app, ["models", "check", "fast", *cli_args(local_models)])
    assert result.exit_code == 0, result.output
    assert "No inference performed" in result.output
    assert "does not guarantee inference" in result.output
    assert "fast: ready" in result.output
    assert "quality:" not in result.output


def test_cli_missing_model_has_json_and_artifact_exit_code(local_models):
    (local_models.directory / "fast.onnx").unlink()
    result = CliRunner().invoke(app, ["models", "check", "fast", *cli_args(local_models), "--json"])
    assert result.exit_code == 3, result.output
    assert json.loads(result.stdout)["profiles"][0]["status"] == "missing"


def test_cli_unknown_profile_and_invalid_registry_have_existing_error_codes(local_models):
    runner = CliRunner()
    unknown = runner.invoke(app, ["models", "check", "unknown", *cli_args(local_models)])
    assert unknown.exit_code == 2
    assert "Unknown model profile" in unknown.output
    local_models.registry.write_text("{")
    invalid = runner.invoke(app, ["models", "check", *cli_args(local_models)])
    assert invalid.exit_code == 3
    assert "Cannot read model registry" in invalid.output
