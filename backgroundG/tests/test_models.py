import builtins
import hashlib
import json
from dataclasses import asdict, replace
from email.message import Message
from io import BytesIO
from pathlib import Path
from urllib.request import Request

import pytest

from bgremove import model_install
from bgremove.model_install import pull_model
from bgremove.registry import ModelConfig, ModelError, read_registry, verify_model


@pytest.fixture
def config():
    return ModelConfig(
        name="fixture",
        file="fixture.onnx",
        sha256=hashlib.sha256(b"trusted-model").hexdigest(),
        input_size=(8, 8),
        mean=(0, 0, 0),
        std=(1, 1, 1),
        commercial_use=True,
        licence="Test fixture only",
        url="https://models.example.org/fixture.onnx",
        redirect_hosts=("cdn.example.org",),
        size_bytes=len(b"trusted-model"),
    )


class DownloadResponse(BytesIO):
    def __init__(self, data=b"trusted-model", *, url=None, length=None, status=200):
        super().__init__(data)
        self.url = url or "https://models.example.org/fixture.onnx"
        self.status = status
        self.headers = {} if length is None else {"Content-Length": str(length)}

    def geturl(self):
        return self.url


def mock_download(monkeypatch, **kwargs):
    calls = []

    def open_download(url, hosts):
        calls.append((url, hosts))
        return DownloadResponse(**kwargs)

    monkeypatch.setattr(model_install, "_open_download", open_download)
    return calls


def test_builtin_profiles_are_pinned_and_hashable():
    profiles = read_registry()
    assert set(profiles) == {"fast", "balanced", "quality", "portrait"}
    for profile in profiles.values():
        assert profile.downloadable
        assert len(profile.sha256) == 64
        assert profile.source.startswith("https://")
        assert profile.license_url.startswith("https://")
        assert profile.size_bytes > 0
        assert profile.provenance
        hash(profile)
    assert profiles["balanced"].mean == (0.5, 0.5, 0.5)
    assert profiles["fast"].normalize_max and profiles["fast"].minmax
    assert not profiles["quality"].normalize_max
    assert not profiles["quality"].minmax
    assert profiles["portrait"].output_activation == "sigmoid"


def test_registry_freezes_lists_and_reads_legacy_configs(config, tmp_path):
    fields = asdict(config)
    for key in ("url", "source", "license_url", "provenance", "size_bytes", "redirect_hosts"):
        fields.pop(key)
    path = tmp_path / "models.json"
    path.write_text(json.dumps({"legacy": fields}))
    parsed = read_registry(path)["legacy"]
    assert parsed.input_size == (8, 8)
    assert not parsed.downloadable
    assert isinstance(hash(parsed), int)


@pytest.mark.parametrize(
    "text",
    ["{", "[]", "{}", '{"fast": null}', '{"fast": {}, "fast": {}}', '{"": {}}'],
)
def test_bad_registry_is_actionable(text, tmp_path):
    path = tmp_path / "models.json"
    path.write_text(text)
    with pytest.raises(ModelError):
        read_registry(path)


def test_missing_registry_is_actionable(tmp_path):
    with pytest.raises(ModelError, match="Cannot read model registry"):
        read_registry(tmp_path / "missing.json")


@pytest.mark.parametrize(
    "changes",
    [
        {"file": "../model.onnx"},
        {"file": "..\\model.onnx"},
        {"file": "C:model.onnx"},
        {"sha256": "z" * 64},
        {"sha256": "123"},
        {"input_size": (False, 8)},
        {"input_size": (8.5, 8)},
        {"input_size": (8, 0)},
        {"mean": (0, float("nan"), 0)},
        {"mean": (0, 10**400, 0)},
        {"std": (1, float("inf"), 1)},
        {"std": (1, 0, 1)},
        {"commercial_use": "yes"},
        {"normalize_max": 1},
        {"output_index": True},
        {"precision": []},
        {"output_activation": []},
        {"size_bytes": -1},
        {"redirect_hosts": [12]},
    ],
)
def test_invalid_model_configuration_is_rejected(config, changes):
    with pytest.raises(ModelError):
        replace(config, **changes)


def test_pull_verified_and_atomic(config, tmp_path, monkeypatch):
    calls = mock_download(monkeypatch, url="https://cdn.example.org/fixture.onnx")
    target = pull_model(config, tmp_path)
    assert target.read_bytes() == b"trusted-model"
    assert verify_model(config, tmp_path) == target
    assert calls == [(config.url, frozenset({"models.example.org", "cdn.example.org"}))]
    assert list(tmp_path.iterdir()) == [target]


def test_pull_respects_existing_file_and_explicit_overwrite(config, tmp_path, monkeypatch):
    target = tmp_path / config.file
    target.write_bytes(b"user-owned")
    calls = mock_download(monkeypatch)
    with pytest.raises(FileExistsError):
        pull_model(config, tmp_path)
    assert not calls
    assert target.read_bytes() == b"user-owned"
    assert pull_model(config, tmp_path, overwrite=True).read_bytes() == b"trusted-model"


def test_concurrent_writer_is_not_overwritten(config, tmp_path, monkeypatch):
    mock_download(monkeypatch)
    link = model_install.os.link

    def publish(source, destination):
        Path(destination).write_bytes(b"concurrent-writer")
        link(source, destination)

    monkeypatch.setattr(model_install.os, "link", publish)
    with pytest.raises(FileExistsError):
        pull_model(config, tmp_path)
    assert (tmp_path / config.file).read_bytes() == b"concurrent-writer"
    assert len(list(tmp_path.iterdir())) == 1


def test_offline_blocks_before_network_import(config, tmp_path, monkeypatch):
    monkeypatch.setenv("BGREMOVE_OFFLINE", "1")
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name.startswith(("urllib", "http", "socket")):
            raise AssertionError("Offline pull imported networking")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    with pytest.raises(ModelError, match="BGREMOVE_OFFLINE"):
        pull_model(config, tmp_path / "new")
    assert not (tmp_path / "new").exists()


def test_noncommercial_requires_explicit_opt_in(config, tmp_path, monkeypatch):
    calls = mock_download(monkeypatch)
    config = replace(config, commercial_use=False)
    with pytest.raises(ModelError, match="noncommercial"):
        pull_model(config, tmp_path)
    assert not calls
    path = pull_model(config, tmp_path, allow_noncommercial=True)
    assert verify_model(config, tmp_path, allow_noncommercial=True) == path


def test_unpinned_or_local_only_profile_never_downloads(config, tmp_path, monkeypatch):
    calls = mock_download(monkeypatch)
    with pytest.raises(ModelError, match="SHA-256"):
        pull_model(replace(config, sha256=""), tmp_path)
    with pytest.raises(ModelError, match="No download URL"):
        pull_model(replace(config, url=None), tmp_path)
    assert not calls


@pytest.mark.parametrize(
    "url",
    [
        "http://models.example.org/a.onnx",
        "file:///tmp/a.onnx",
        "https://user:password@models.example.org/a.onnx",
        "https://127.0.0.1/a.onnx",
        "https://[::1]/a.onnx",
        "https://localhost/a.onnx",
        "https://models.example.org:444/a.onnx",
        "https://models.example.org/a.onnx#fragment",
    ],
)
def test_unsafe_url_rejected_before_download(config, tmp_path, monkeypatch, url):
    calls = mock_download(monkeypatch)
    with pytest.raises(ModelError, match="HTTPS|URL"):
        pull_model(replace(config, url=url), tmp_path)
    assert not calls
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "response,match",
    [
        ({"data": b"tampered-file"}, "hash mismatch"),
        ({"data": b"short"}, "size mismatch"),
        ({"data": b"trusted-model-extra"}, "size limit"),
        ({"length": 99}, "size limit"),
        ({"length": "invalid"}, "Content-Length"),
        ({"status": 206}, "HTTP 206"),
        ({"url": "http://models.example.org/a.onnx"}, "HTTPS"),
        ({"url": "https://evil.example.org/a.onnx"}, "HTTPS"),
    ],
)
def test_failed_download_never_publishes(config, tmp_path, monkeypatch, response, match):
    mock_download(monkeypatch, **response)
    with pytest.raises(ModelError, match=match):
        pull_model(config, tmp_path)
    assert not list(tmp_path.iterdir())


def test_failed_overwrite_preserves_original(config, tmp_path, monkeypatch):
    target = tmp_path / config.file
    target.write_bytes(b"original")
    mock_download(monkeypatch, data=b"tampered-file")
    with pytest.raises(ModelError, match="hash mismatch"):
        pull_model(config, tmp_path, overwrite=True)
    assert target.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [target]


def test_network_timeout_cleans_temporary_file(config, tmp_path, monkeypatch):
    def timeout(*args):
        raise TimeoutError("network stalled")

    monkeypatch.setattr(model_install, "_open_download", timeout)
    with pytest.raises(ModelError, match="network stalled"):
        pull_model(config, tmp_path)
    assert not list(tmp_path.iterdir())


def test_unknown_size_still_has_download_limit(config, tmp_path, monkeypatch):
    mock_download(monkeypatch)
    monkeypatch.setattr(model_install, "MAX_DOWNLOAD_BYTES", 8)
    with pytest.raises(ModelError, match="size limit"):
        pull_model(replace(config, size_bytes=None), tmp_path)
    assert not list(tmp_path.iterdir())


def test_slow_stream_has_total_deadline(config, tmp_path, monkeypatch):
    mock_download(monkeypatch)
    ticks = iter([0, 0, 3])
    monkeypatch.setattr(model_install.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(model_install, "DOWNLOAD_DEADLINE_SECONDS", 2)
    with pytest.raises(ModelError, match="time limit"):
        pull_model(config, tmp_path)
    assert not list(tmp_path.iterdir())


def test_redirect_handler_enforces_host_and_https(monkeypatch):
    import urllib.request

    handlers = []

    class FakeOpener:
        def open(self, request, timeout):
            assert timeout > 0
            return DownloadResponse()

    def capture(handler):
        handlers.append(handler)
        return FakeOpener()

    monkeypatch.setattr(urllib.request, "build_opener", capture)
    url = "https://models.example.org/a.onnx"
    with model_install._open_download(url, frozenset({"models.example.org", "cdn.example.org"})):
        pass
    handler = handlers[0]
    headers = Message()
    request = Request(url)
    approved = handler.redirect_request(
        request, None, 302, "Found", headers, "https://cdn.example.org/a.onnx"
    )
    assert approved.full_url == "https://cdn.example.org/a.onnx"
    for redirect in ["http://cdn.example.org/a.onnx", "https://evil.example.org/a.onnx"]:
        with pytest.raises(ModelError, match="HTTPS"):
            handler.redirect_request(request, None, 302, "Found", headers, redirect)
