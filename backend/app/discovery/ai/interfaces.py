"""Future AI-provider seams (Phase 6G / D4) — INTERFACES ONLY, no model calls.

D4 uses `MockAIExtractor` exclusively (constraint: no Gemini/OpenAI integration). These classes fix
where a real model plugs in: each is an `AIExtractor` whose `extract()` raises NotImplementedError.
A later phase implements the HTTP/SDK call using `prompts.py` and a strict JSON response schema,
`temperature=0` for determinism, and the same never-fabricate contract — **without changing the
pipeline, validator, confidence engine, or store**. Nothing here makes a network request.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.discovery.ai.extractor import AIExtractor, ExtractionInput
from app.discovery.ai.models import AIExtraction


@dataclass(frozen=True)
class AIExtractorConfig:
    """Config a real extractor needs (supplied via env/secrets, never hardcoded)."""

    model: str = "gemini-flash-lite-latest"  # matches the app's existing Gemini model choice
    api_key: str | None = None
    temperature: float = 0.0  # deterministic extraction
    max_output_tokens: int = 2048
    request_timeout_s: float = 20.0
    max_input_chars: int = 8000  # page text is truncated to a token-safe window


class GeminiAIExtractor(AIExtractor):
    """Google Gemini extractor — future adapter.

    Would send prompts.SYSTEM_PROMPT + build_extraction_prompt(...) with a strict response schema
    (Gemini `response_schema`), parse the JSON into `AIExtraction`, and drop any field whose snippet
    is not actually found in the page (anti-fabrication check). Reuses the app's existing Gemini
    plumbing/model; requires GEMINI_API_KEY.
    """

    name = "gemini"

    def __init__(self, config: AIExtractorConfig) -> None:
        self._config = config

    def extract(self, page: ExtractionInput) -> AIExtraction:  # pragma: no cover
        raise NotImplementedError("Gemini integration deferred — D4 uses MockAIExtractor only")


class OpenAIAIExtractor(AIExtractor):
    """OpenAI extractor — future adapter (JSON mode / function-calling)."""

    name = "openai"

    def __init__(self, config: AIExtractorConfig) -> None:
        self._config = config

    def extract(self, page: ExtractionInput) -> AIExtraction:  # pragma: no cover
        raise NotImplementedError("OpenAI integration deferred — D4 uses MockAIExtractor only")
