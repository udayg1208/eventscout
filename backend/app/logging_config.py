"""Centralized logging setup.

Kept intentionally simple for now (stdlib logging). If structured/JSON logging
is needed for production observability later, this is the single place to change.
"""

from __future__ import annotations

import logging

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def setup_logging(level: str = "INFO") -> None:
    """Configure root logging once, idempotently."""
    resolved = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=resolved, format=_LOG_FORMAT, force=True)
