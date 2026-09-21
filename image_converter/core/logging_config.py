"""
Structured logging configuration for Universal File Converter.
Provides configurable console and rotating file logging for diagnostics and debugging.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
import sys
from pathlib import Path
from typing import Optional

LOGGER_NAME = "universal_converter"
PACKAGE_LOGGER_NAME = "image_converter"

DEFAULT_LOG_DIR = Path(os.environ.get("APPDATA", Path.home())) / "UniversalFileConverter" / "logs"
DEFAULT_LOG_FILE = DEFAULT_LOG_DIR / "converter.log"

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DEBUG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s"


def setup_logger(
    verbose: bool = False,
    log_file: Optional[str | Path] = None,
    enable_default_file: bool = True,
) -> logging.Logger:
    """
    Configure the universal_converter and image_converter root loggers.
    - verbose: Enables DEBUG logging level.
    - log_file: If provided, appends full diagnostic log entries to this file.
    - enable_default_file: If True and log_file is None, writes to DEFAULT_LOG_FILE in appdata.
    """
    level = logging.DEBUG if verbose else logging.INFO
    formatter = logging.Formatter(_DEBUG_FORMAT if verbose else _LOG_FORMAT)

    target_file = log_file
    if target_file is None and enable_default_file:
        target_file = DEFAULT_LOG_FILE

    # Configure both LOGGER_NAME and PACKAGE_LOGGER_NAME
    loggers = [logging.getLogger(LOGGER_NAME), logging.getLogger(PACKAGE_LOGGER_NAME)]

    # Shared console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    # Shared file handler
    file_handler = None
    if target_file:
        file_path = Path(target_file).resolve()
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                str(file_path),
                maxBytes=5 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(logging.Formatter(_DEBUG_FORMAT))
        except Exception as e:
            sys.stderr.write(f"Failed to initialize rotating file logger at {file_path}: {e}\n")

    for log in loggers:
        log.setLevel(level)
        if log.hasHandlers():
            log.handlers.clear()
        log.addHandler(console_handler)
        if file_handler:
            log.addHandler(file_handler)

    primary_logger = logging.getLogger(LOGGER_NAME)
    if file_handler and target_file:
        primary_logger.debug(f"Rotating file logging initialized at: {target_file}")

    return primary_logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Retrieve the universal_converter application logger or child logger."""
    if name:
        return logging.getLogger(f"{LOGGER_NAME}.{name}")
    return logging.getLogger(LOGGER_NAME)

