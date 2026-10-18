"""Explicit model downloads. Inference never imports this module's network helpers."""

import hashlib
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any, BinaryIO, cast

from .registry import ModelConfig, ModelError, _check_model_policy

MAX_DOWNLOAD_BYTES = 2 * 1024 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 30
DOWNLOAD_DEADLINE_SECONDS = 30 * 60
CHUNK_BYTES = 1024 * 1024


def _check_url(url: str, allowed_hosts: frozenset[str] | None = None) -> str:
    from urllib.parse import urlsplit

    try:
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        port = parsed.port
    except ValueError as error:
        raise ModelError("Invalid model download URL") from error
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or parsed.fragment
        or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}", host)
        or (allowed_hosts is not None and host not in allowed_hosts)
    ):
        raise ModelError("Model download requires HTTPS on an explicitly allowed host")
    return host


def _open_download(url: str, hosts: frozenset[str]) -> Any:
    # Deliberately lazy: BGREMOVE_OFFLINE is checked before importing networking code.
    import urllib.request

    class RestrictedRedirect(urllib.request.HTTPRedirectHandler):
        max_redirections = 5

        def redirect_request(
            self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
        ) -> Any:
            _check_url(newurl, hosts)
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    opener = urllib.request.build_opener(RestrictedRedirect())
    request = urllib.request.Request(url, headers={"User-Agent": "local-bgremove/0.2"})
    return opener.open(request, timeout=DOWNLOAD_TIMEOUT_SECONDS)


def _download(config: ModelConfig, stream: BinaryIO) -> None:
    assert config.url is not None
    host = _check_url(config.url)
    hosts = frozenset((host, *config.redirect_hosts))
    for redirect_host in config.redirect_hosts:
        _check_url(f"https://{redirect_host}/")
    maximum = min(config.size_bytes or MAX_DOWNLOAD_BYTES, MAX_DOWNLOAD_BYTES)
    deadline = time.monotonic() + DOWNLOAD_DEADLINE_SECONDS
    digest = hashlib.sha256()
    downloaded = 0
    with _open_download(config.url, hosts) as response:
        _check_url(response.geturl(), hosts)
        if response.status != 200:
            raise ModelError(f"Model download returned HTTP {response.status}")
        advertised = response.headers.get("Content-Length")
        if advertised is not None:
            try:
                length = int(advertised)
            except ValueError as error:
                raise ModelError("Invalid model download Content-Length") from error
            if length < 1 or length > maximum:
                raise ModelError("Model download exceeds the expected size limit")
        while True:
            if time.monotonic() > deadline:
                raise ModelError("Model download exceeded its time limit")
            # read1 returns after one buffered/network read, so slow streams cannot hide
            # indefinitely inside a multi-read operation between deadline checks.
            block = response.read1(CHUNK_BYTES)
            if not block:
                break
            downloaded += len(block)
            if downloaded > maximum:
                raise ModelError("Model download exceeds the expected size limit")
            digest.update(block)
            stream.write(block)
    if config.size_bytes is not None and downloaded != config.size_bytes:
        raise ModelError("Model download size mismatch")
    if digest.hexdigest() != config.sha256.lower():
        raise ModelError("Model download hash mismatch; file was not installed")


def pull_model(
    config: ModelConfig,
    directory: Path,
    allow_noncommercial: bool = False,
    overwrite: bool = False,
) -> Path:
    """Download one pinned artifact, verify it, and atomically publish it locally."""
    if os.environ.get("BGREMOVE_OFFLINE") == "1":
        raise ModelError("Model download disabled by BGREMOVE_OFFLINE=1")
    _check_model_policy(config, allow_noncommercial)
    if not config.url:
        raise ModelError("No download URL registered for this model")
    _check_url(config.url)
    directory = Path(directory)
    target = directory / config.file
    if (target.exists() or target.is_symlink()) and not overwrite:
        raise FileExistsError(f"Model already exists: {target}")
    temporary: Path | None = None
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=directory, prefix=f".{config.file}.", suffix=".part", delete=False
        ) as stream:
            temporary = Path(stream.name)
            _download(config, cast(BinaryIO, stream))
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            os.replace(temporary, target)
        else:
            # Hard-link publication is atomic and cannot clobber a concurrently created file.
            os.link(temporary, target)
        return target
    except FileExistsError:
        raise
    except (OSError, ValueError) as error:
        if isinstance(error, ModelError):
            raise
        raise ModelError(f"Cannot install model {config.name}: {error}") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
