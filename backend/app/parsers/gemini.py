"""GeminiQueryParser — natural language understanding behind the QueryParser seam.

Flow (never raises for user input):
  1. Empty input        -> empty SearchQuery (no API call).
  2. Call Gemini        -> validate JSON against SearchQuery.
  3. If invalid         -> retry ONCE with a corrective prompt (previous output + error).
  4. If still invalid   -> delegate to the deterministic fallback parser.

Gemini is fully isolated: the SDK is imported lazily inside `_generate`, so this
module (and its tests) load without the package or an API key. `_generate` is the
single seam tests override to script model responses.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import NamedTuple

from pydantic import ValidationError

from app.models.search import SearchQuery
from app.parsers.base import QueryParser
from app.parsers.keyword import KeywordQueryParser
from app.parsers.prompts import build_corrective_prompt, build_prompt

logger = logging.getLogger(__name__)


class _Attempt(NamedTuple):
    query: SearchQuery | None  # validated result, or None on failure
    raw: str  # raw model text (for the corrective prompt)
    error: str  # validation/API error message (for the corrective prompt)


class GeminiQueryParser(QueryParser):
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        fallback: QueryParser | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._fallback = fallback or KeywordQueryParser()
        self._client_obj = None  # lazily created; see _client()
        # Lightweight observability counters (read by SearchService.metrics()).
        # Additive only — not part of the QueryParser contract.
        self.gemini_calls = 0  # Gemini API attempts (incl. retries)
        self.fallback_count = 0  # times parse() fell back to the deterministic parser

    async def parse(self, text: str) -> SearchQuery:
        if not text.strip():
            logger.info("empty query -> empty SearchQuery (no model call)")
            return SearchQuery()

        today = date.today()

        first = await self._generate_and_validate(build_prompt(text, today))
        if first.query is not None:
            return first.query

        logger.info("Gemini output invalid (%s); retrying with correction", first.error)
        corrective = build_corrective_prompt(text, first.raw, first.error, today)
        second = await self._generate_and_validate(corrective)
        if second.query is not None:
            return second.query

        logger.warning("Gemini failed twice for %r; using deterministic fallback", text)
        self.fallback_count += 1
        return await self._fallback.parse(text)

    async def _generate_and_validate(self, prompt: str) -> _Attempt:
        self.gemini_calls += 1
        try:
            raw = await self._generate(prompt)
        except Exception as exc:  # API/network error -> treat as a failed attempt
            logger.warning("Gemini call error: %s", exc)
            return _Attempt(None, "", f"model call failed: {exc}")

        cleaned = _strip_code_fences(raw)
        try:
            return _Attempt(SearchQuery.model_validate_json(cleaned), cleaned, "")
        except (ValidationError, ValueError, TypeError) as exc:
            return _Attempt(None, cleaned, str(exc))

    async def _generate(self, prompt: str) -> str:
        """Call Gemini and return raw response text.

        The only method that touches the SDK. Overridden in tests. Requests JSON
        output and passes the SearchQuery schema so Gemini emits structured data.
        """
        client = self._client()
        response = await client.aio.models.generate_content(
            model=self._model,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": SearchQuery,
            },
        )
        return response.text or ""

    def _client(self):
        if self._client_obj is None:
            from google import genai  # lazy: keeps module import SDK-free

            self._client_obj = genai.Client(api_key=self._api_key)
        return self._client_obj


def _strip_code_fences(raw: str) -> str:
    """Remove ```json ... ``` fences if a model wraps its JSON despite instructions."""
    text = raw.strip()
    if text.startswith("```"):
        text = text[3:]  # drop opening ```
        if text[:4].casefold() == "json":  # drop optional language tag
            text = text[4:]
        if text.endswith("```"):
            text = text[:-3]  # drop closing ```
    return text.strip()
