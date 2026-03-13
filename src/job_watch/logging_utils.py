"""Logging helpers."""

from __future__ import annotations

import logging

from rich.logging import RichHandler


def get_logger(verbose: bool = False) -> logging.Logger:
    """Return a configured logger."""

    logger = logging.getLogger("job-watch")
    if not logger.handlers:
        handler = RichHandler(markup=False, rich_tracebacks=True, show_path=False)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.propagate = False
    return logger
