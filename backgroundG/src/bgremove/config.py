import os
from pathlib import Path

from platformdirs import user_cache_dir

MAX_PIXELS = 120_000_000
MAX_BYTES = 25 * 1024 * 1024


def model_directory() -> Path:
    return Path(os.environ.get("BGREMOVE_MODEL_DIR", user_cache_dir("bgremove")))
