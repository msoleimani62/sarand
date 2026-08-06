"""Structured logging setup for sarand."""

from __future__ import annotations

import logging
import sys
from typing import Optional

_LOGGER_NAME = "sarand"


def setup_logging(*, verbose: bool = False, debug: bool = False) -> None:
    """Configure the root sarand logger.

    Args:
        verbose: Enable INFO level messages for normal users.
        debug: Enable DEBUG level (implies verbose).
    """
    if debug:
        level = logging.DEBUG
    elif verbose:
        level = logging.INFO
    else:
        level = logging.WARNING

    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(level)

    # Avoid duplicate handlers on repeated calls
    # جلوگیری از هندلرهای تکراری در فراخوانی‌های مکرر
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a child logger under the sarand namespace."""
    if name:
        return logging.getLogger(f"{_LOGGER_NAME}.{name}")
    return logging.getLogger(_LOGGER_NAME)
