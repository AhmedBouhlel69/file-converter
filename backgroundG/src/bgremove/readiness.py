"""Check local model artifacts and CPU startup policy without loading sessions.

Exit codes: 0 means all selected profiles pass these checks; 3 means at least
one artifact/provider is unusable; 5 means verified profiles are RAM-blocked.
Artifact/provider failures take precedence over RAM blocks. Invalid registry
or profile arguments raise errors for the CLI's existing error handling.
Readiness never proves successful inference or reserves the reported memory.
"""

from pathlib import Path
from typing import Any

import onnxruntime as ort
import psutil

from .config import model_directory
from .registry import ModelConfig, ModelError, read_registry, verify_model
from .resource_policy import LARGE_MODEL_BYTES, MIN_LARGE_CPU_FREE_BYTES


def _check_artifact(
    profile: str, config: ModelConfig, directory: Path, allow_noncommercial: bool
) -> dict[str, Any]:
    path = directory / config.file
    entry: dict[str, Any] = {
        "profile": profile,
        "name": config.name,
        "path": str(path),
        "installed": False,
        "verified": False,
        "cpu_ready": False,
        "status": "missing",
        "expected_size_bytes": config.size_bytes,
        "actual_size_bytes": None,
        "required_free_memory_bytes": (
            MIN_LARGE_CPU_FREE_BYTES
            if config.size_bytes is not None and config.size_bytes >= LARGE_MODEL_BYTES
            else 0
        ),
        "reason": "",
    }
    try:
        entry["installed"] = path.is_file()
        if not entry["installed"]:
            entry["reason"] = (
                f"Model missing: {path}. Run 'bgremove models pull {profile}' explicitly "
                "or copy the registered verified file."
            )
            return entry
        entry["actual_size_bytes"] = path.stat().st_size
        if config.size_bytes is not None and entry["actual_size_bytes"] != config.size_bytes:
            entry["status"] = "corrupt"
            entry["reason"] = (
                f"Model size mismatch: expected {config.size_bytes} bytes, "
                f"found {entry['actual_size_bytes']}."
            )
            return entry
        verify_model(config, directory, allow_noncommercial)
    except (ModelError, OSError) as exc:
        entry["status"] = (
            "corrupt" if str(exc).startswith("Model hash mismatch:") else "invalid"
        )
        entry["reason"] = str(exc)
        return entry
    entry["verified"] = True
    return entry


def readiness_exit_code(report: dict[str, Any]) -> int:
    """Return stable readiness status, prioritizing unusable artifacts/providers."""
    statuses = {entry["status"] for entry in report["profiles"]}
    if statuses - {"ready", "resource_blocked"}:
        return 3
    return 5 if "resource_blocked" in statuses else 0


def check_models(
    profile: str | None = None,
    registry: Path | None = None,
    model_dir: Path | None = None,
    allow_noncommercial: bool = False,
) -> dict[str, Any]:
    """Verify selected local files and report CPU startup readiness as JSON data.

    No downloads, output images, ONNX sessions or warmup runs are performed.
    A small profile's zero required bytes means no additional startup threshold
    is configured; it does not mean the model uses zero memory.
    """
    configs = read_registry(registry)
    if profile is not None and profile not in configs:
        raise ValueError(f"Unknown model profile: {profile}")
    directory = (model_dir or model_directory()).expanduser().resolve()
    entries = [
        _check_artifact(name, config, directory, allow_noncommercial)
        for name, config in configs.items()
        if profile is None or name == profile
    ]
    # Hashing can take time. Sample memory after verification so the report
    # describes the latest available headroom, without claiming to reserve it.
    memory = psutil.virtual_memory()
    providers = ort.get_available_providers()
    cpu_available = "CPUExecutionProvider" in providers
    for entry in entries:
        if not entry["verified"]:
            continue
        if not cpu_available:
            entry["status"] = "provider_unavailable"
            entry["reason"] = "CPUExecutionProvider is unavailable in the installed ONNX runtime."
        elif memory.available < entry["required_free_memory_bytes"]:
            entry["status"] = "resource_blocked"
            entry["reason"] = (
                "This large model needs at least 8 GiB of free RAM for CPU processing "
                f"({memory.available / 1024**3:.1f} GiB available). "
                "Close other memory-heavy apps, or choose Fast or Balanced."
            )
        else:
            entry["status"] = "ready"
            entry["cpu_ready"] = True
            entry["reason"] = (
                "Verified local artifact and CPU startup policy checks passed. "
                "Inference has not been tested."
            )
    report: dict[str, Any] = {
        "schema_version": 1,
        "check": "cpu_startup_readiness",
        "device": "cpu",
        "inference_tested": False,
        "available_providers": providers,
        "cpu_provider_available": cpu_available,
        "available_memory_bytes": memory.available,
        "total_memory_bytes": memory.total,
        "policy": {
            "large_model_bytes": LARGE_MODEL_BYTES,
            "min_large_cpu_free_bytes": MIN_LARGE_CPU_FREE_BYTES,
            "scope": "Startup check only; no memory reservation or inference guarantee.",
        },
        "profiles": entries,
    }
    report["exit_code"] = readiness_exit_code(report)
    return report
