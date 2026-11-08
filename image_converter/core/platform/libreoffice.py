"""LibreOffice as a fallback converter when Microsoft Office is not available.

Word, ODT, RTF, PowerPoint and Excel to PDF (and Word/ODT/RTF to each other)
need an office suite to lay out pages faithfully. On machines without Microsoft
Office, a free LibreOffice install produces the same kinds of output.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# LibreOffice --convert-to targets; Word output needs an explicit filter.
_FILTERS = {
    "PDF": "pdf",
    "DOCX": "docx:MS Word 2007 XML",
    "ODT": "odt",
    "RTF": "rtf",
}
TIMEOUT_SECONDS = 180


def find_soffice() -> Optional[str]:
    """Locate the LibreOffice command-line program, or return None."""
    configured = os.environ.get("LIBREOFFICE_PATH")
    if configured and Path(configured).is_file():
        return configured
    for name in ("soffice", "libreoffice"):
        found = shutil.which(name)
        if found:
            return found
    candidates = []
    if os.name == "nt":
        for root in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
            candidates.append(Path(root) / "LibreOffice" / "program" / "soffice.exe")
    elif sys.platform == "darwin":
        candidates.append(Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"))
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def is_available() -> bool:
    return find_soffice() is not None


def convert(input_path: str | Path, output_path: str | Path, target: str) -> Path:
    """Convert with LibreOffice and move the result atomically to ``output_path``.

    Raises RuntimeError when LibreOffice is missing or fails.
    """
    soffice = find_soffice()
    if soffice is None:
        raise RuntimeError("LibreOffice is not installed.")
    target = target.upper()
    if target not in _FILTERS:
        raise RuntimeError(f"LibreOffice fallback does not support {target}.")
    in_p = Path(input_path).resolve()
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ufc-lo-") as work:
        work_dir = Path(work)
        # A private profile lets this run while the user has LibreOffice open.
        profile = (work_dir / "profile").as_uri()
        command = [
            soffice,
            "--headless",
            "--norestore",
            "--nolockcheck",
            f"-env:UserInstallation={profile}",
            "--convert-to",
            _FILTERS[target],
            "--outdir",
            str(work_dir),
            str(in_p),
        ]
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            completed = subprocess.run(
                command, capture_output=True, text=True, timeout=TIMEOUT_SECONDS, **kwargs
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"LibreOffice took longer than {TIMEOUT_SECONDS} s converting '{in_p.name}'.") from exc
        produced = work_dir / f"{in_p.stem}.{target.lower()}"
        if completed.returncode != 0 or not produced.is_file() or produced.stat().st_size == 0:
            detail = (completed.stderr or completed.stdout or "").strip().splitlines()
            raise RuntimeError(
                f"LibreOffice could not convert '{in_p.name}' to {target}"
                + (f": {detail[-1]}" if detail else ".")
            )
        temp = out_p.with_name(f".tmp_lo_{os.getpid()}_{time.time_ns()}{out_p.suffix}")
        try:
            shutil.copyfile(produced, temp)
            os.replace(temp, out_p)
        finally:
            if temp.exists():
                temp.unlink()
    return out_p


def fallback_or_raise(input_path: str | Path, output_path: str | Path, target: str, office_message: str) -> Path:
    """Try LibreOffice; if it is not installed, raise the original Office message with a hint."""
    if not is_available():
        raise RuntimeError(
            f"{office_message} Alternatively, install the free LibreOffice (libreoffice.org) "
            "and this conversion will use it automatically."
        )
    logger.info("Microsoft Office unavailable; converting %s to %s with LibreOffice", Path(input_path).name, target)
    return convert(input_path, output_path, target)
