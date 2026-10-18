import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import model_directory


class ModelError(ValueError):
    pass


def _finite_real(value: Any) -> bool:
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


@dataclass(frozen=True)
class ModelConfig:
    name: str
    file: str
    sha256: str
    input_size: tuple[int, int]
    mean: tuple[float, float, float]
    std: tuple[float, float, float]
    output_index: int = 0
    output_activation: str = "none"
    precision: str = "fp32"
    normalize_max: bool = False
    minmax: bool = False
    licence: str = "unverified"
    commercial_use: bool = False
    url: str | None = None
    source: str = ""
    license_url: str = ""
    provenance: str = ""
    size_bytes: int | None = None
    redirect_hosts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field in ("input_size", "mean", "std", "redirect_hosts"):
            value = getattr(self, field)
            if not isinstance(value, (list, tuple)):
                raise ModelError(f"Invalid model {field}: expected a list or tuple")
            object.__setattr__(self, field, tuple(value))
        if not isinstance(self.name, str) or not self.name.strip():
            raise ModelError("Model name must be nonempty")
        if not isinstance(self.file, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]*\.onnx", self.file
        ):
            raise ModelError("Model file must be a plain .onnx filename")
        if not isinstance(self.sha256, str) or (
            self.sha256 and not re.fullmatch(r"[a-fA-F0-9]{64}", self.sha256)
        ):
            raise ModelError("Model SHA-256 must be empty or 64 hexadecimal characters")
        if len(self.input_size) != 2 or any(
            type(value) is not int or value < 1 for value in self.input_size
        ):
            raise ModelError("Invalid model dimensions")
        if (
            len(self.mean) != 3
            or len(self.std) != 3
            or any(not _finite_real(value) for value in (*self.mean, *self.std))
            or min(self.std) <= 0
        ):
            raise ModelError("Invalid normalization")
        if not isinstance(self.output_activation, str) or self.output_activation not in {
            "none",
            "sigmoid",
        }:
            raise ModelError("Invalid output activation")
        if (
            not isinstance(self.precision, str)
            or self.precision not in {"fp16", "fp32"}
            or type(self.output_index) is not int
            or self.output_index < 0
        ):
            raise ModelError("Invalid tensor configuration")
        for field in ("normalize_max", "minmax", "commercial_use"):
            if type(getattr(self, field)) is not bool:
                raise ModelError(f"Model {field} must be a boolean")
        for field in ("licence", "source", "license_url", "provenance"):
            if not isinstance(getattr(self, field), str):
                raise ModelError(f"Model {field} must be a string")
        if self.url is not None and not isinstance(self.url, str):
            raise ModelError("Model URL must be a string")
        if self.size_bytes is not None and (
            type(self.size_bytes) is not int or self.size_bytes < 1
        ):
            raise ModelError("Model size must be a positive integer")
        if any(not isinstance(host, str) or not host for host in self.redirect_hosts):
            raise ModelError("Model redirect hosts must be nonempty strings")

    @property
    def downloadable(self) -> bool:
        return bool(self.sha256 and self.url)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ModelError(f"Duplicate registry key: {key}")
        result[key] = value
    return result


def read_registry(path: Path | None = None) -> dict[str, ModelConfig]:
    location = path or Path(__file__).with_name("models.json")
    try:
        data = json.loads(location.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ModelError(f"Cannot read model registry {location}: {error}") from error
    if not isinstance(data, dict) or not data:
        raise ModelError("Model registry must be a nonempty JSON object")
    result: dict[str, ModelConfig] = {}
    for key, value in data.items():
        if not isinstance(key, str) or not key.strip() or not isinstance(value, dict):
            raise ModelError("Each model profile must be a named JSON object")
        try:
            result[key] = ModelConfig(**value)
        except (ModelError, TypeError, ValueError) as error:
            raise ModelError(f"Invalid model profile {key!r}: {error}") from error
    return result


def _check_model_policy(config: ModelConfig, allow_noncommercial: bool) -> None:
    if not config.commercial_use and not allow_noncommercial:
        raise ModelError("Model requires explicit --allow-noncommercial")
    if not config.sha256:
        raise ModelError("Register a verified SHA-256 before using this model")


def verify_model(
    config: ModelConfig, directory: Path | None = None, allow_noncommercial: bool = False
) -> Path:
    _check_model_policy(config, allow_noncommercial)
    path = (directory or model_directory()) / config.file
    if not path.is_file():
        raise ModelError(
            f"Model missing: {path}. Run 'bgremove models pull' explicitly or copy a verified file."
        )
    try:
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
    except OSError as error:
        raise ModelError(f"Cannot read model {path}: {error}") from error
    if digest != config.sha256.lower():
        raise ModelError(f"Model hash mismatch: {path}")
    return path
