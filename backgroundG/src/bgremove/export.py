import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


def export(
    image: Image.Image,
    path: str | Path,
    *,
    icc: bytes | None = None,
    exif: bytes | None = None,
    overwrite: bool = False,
) -> None:
    target = Path(path)
    fmt = {".png": "PNG", ".webp": "WEBP"}.get(target.suffix.lower())
    if fmt is None:
        raise ValueError("Output must be PNG or WebP")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=target.parent, suffix=target.suffix)
    os.close(fd)
    try:
        options: dict[str, Any] = (
            {"compress_level": 6} if fmt == "PNG" else {"lossless": True, "method": 4}
        )
        clean = Image.fromarray(np.array(image))
        clean.save(temporary, format=fmt, icc_profile=icc, exif=exif or b"", **options)
        if overwrite:
            os.replace(temporary, target)
        else:
            # Hard-link publication is atomic and fails if the destination already exists.
            os.link(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
