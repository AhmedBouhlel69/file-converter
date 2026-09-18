"""
Unit tests for structured logging and diagnostic file outputs.
"""

from pathlib import Path
import logging
import pytest

from image_converter.core.logging_config import setup_logger, get_logger


def test_logger_creation_and_file_logging(tmp_path: Path):
    log_file = tmp_path / "converter.log"
    logger = setup_logger(verbose=True, log_file=log_file)

    test_msg = "Universal File Converter Log Event Test 12345"
    logger.info(test_msg)

    # Flush handlers
    for h in logger.handlers:
        h.flush()

    assert log_file.is_file()
    log_text = log_file.read_text(encoding="utf-8")
    assert test_msg in log_text


def test_get_logger_hierarchy():
    sub_logger = get_logger("engine")
    assert sub_logger.name == "universal_converter.engine"
