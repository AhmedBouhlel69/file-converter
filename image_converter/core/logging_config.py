"""
Structured logging configuration for Universal File Converter.
Provides configurable console and file logging for diagnostics and debugging.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

LOGGER_NAME = "universal_converter"

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DEBUG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s"


def setup_logger(
    verbose: bool = False,
    log_file: Optional[str | Path] = None,
) -> logging.Logger:
    """
    Configure the root universal_converter logger.
    - verbose: Enables DEBUG logging level.
    - log_file: If provided, appends full diagnostic log entries to this file.
    """
    logger = logging.getLogger(LOGGER_NAME)
    level = logging.DEBUG if verbose else logging.INFO
    logger.setLevel(level)

    # Clear existing handlers to prevent duplicates
    if logger.hasHandlers():
        logger.handlers.clear()

    formatter = logging.Formatter(_DEBUG_FORMAT if verbose else _LOG_FORMAT)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Optional file handler
    if log_file:
        file_path = Path(log_file).resolve()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(file_path), encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(_DEBUG_FORMAT))
        logger.addHandler(file_handler)
        logger.debug(f"File logging initialized at: {file_path}")

    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Retrieve the universal_converter application logger or child logger."""
    if name:
        return logging.getLogger(f"{LOGGER_NAME}.{name}")
    return logging.getLogger(LOGGER_NAME)
