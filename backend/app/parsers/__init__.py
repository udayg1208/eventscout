"""Query parser registry.

`get_query_parser()` is the single place the active parser is chosen. If a Gemini
key is configured, use GeminiQueryParser (with the deterministic parser as its
fallback); otherwise the app runs fully on the deterministic parser. No caller ever
references a concrete parser.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.config import get_settings
from app.parsers.base import QueryParser
from app.parsers.gemini import GeminiQueryParser
from app.parsers.keyword import KeywordQueryParser

logger = logging.getLogger(__name__)

__all__ = ["QueryParser", "GeminiQueryParser", "KeywordQueryParser", "get_query_parser"]


@lru_cache
def get_query_parser() -> QueryParser:
    """Return the active query parser based on configuration."""
    settings = get_settings()
    if settings.gemini_api_key:
        logger.info("Using GeminiQueryParser (model=%s)", settings.gemini_model)
        return GeminiQueryParser(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            fallback=KeywordQueryParser(),
        )
    logger.info("No GEMINI_API_KEY set; using deterministic KeywordQueryParser")
    return KeywordQueryParser()
