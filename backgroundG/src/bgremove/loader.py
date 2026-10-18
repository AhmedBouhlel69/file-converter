import warnings
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError

from .config import MAX_BYTES, MAX_PIXELS

Image.MAX_IMAGE_PIXELS = MAX_PIXELS


class InputError(ValueError):
    pass


@dataclass
class LoadedImage:
    rgb: NDArray[np.uint8]
    icc: bytes | None
    exif: bytes | None


def load(
    source: str | Path | bytes | Image.Image,
    max_pixels: int = MAX_PIXELS,
    max_bytes: int = MAX_BYTES,
) -> LoadedImage:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            if isinstance(source, Image.Image):
                image = source
            else:
                if isinstance(source, bytes):
                    data = source
                else:
                    with Path(source).open("rb") as stream:
                        data = stream.read(max_bytes + 1)
                if len(data) > max_bytes:
                    raise InputError("Input exceeds byte limit")
                image = Image.open(BytesIO(data))
                if image.format not in {"JPEG", "PNG", "WEBP", "BMP", "TIFF"}:
                    raise InputError("Unsupported image format")
            if image.width * image.height > max_pixels:
                raise InputError("Input exceeds pixel limit")
            image = ImageOps.exif_transpose(image)
            icc = image.info.get("icc_profile")
            exif_data = image.getexif()
            exif_data.pop(274, None)
            exif = exif_data.tobytes() if exif_data else None
            if image.mode == "CMYK" and icc:
                image = ImageCms.profileToProfile(
                    image,
                    ImageCms.ImageCmsProfile(BytesIO(icc)),
                    ImageCms.createProfile("sRGB"),
                    outputMode="RGB",
                )
                icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()  # type: ignore[no-untyped-call]
            elif image.mode.startswith("I;16") or image.mode == "I":
                image = Image.fromarray((np.asarray(image).clip(0, 65535) / 257).astype("uint8"))
            return LoadedImage(np.array(image.convert("RGB"), dtype=np.uint8), icc, exif)
    except (
        OSError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        ValueError,
    ) as exc:
        raise InputError(f"Cannot load input: {exc}") from exc
