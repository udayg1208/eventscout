"""M3 tests: natural language -> validated SearchQuery.

Covers the required scenarios: successful parsing, malformed model output, the
retry path, the deterministic fallback, empty input, and ambiguous queries. Plus
schema-violation and API-error degradation, and the deterministic parser itself.

Gemini is never contacted: ScriptedGemini overrides `_generate` with a queue of
canned responses (strings return as model text; Exceptions are raised).
"""

from __future__ import annotations

import asyncio

import pytest

from app.models.event import EventCategory
from app.models.search import SearchQuery
from app.parsers.gemini import GeminiQueryParser
from app.parsers.keyword import KeywordQueryParser

VALID_JSON = (
    '{"keywords": ["machine learning"], "city": "Bangalore", '
    '"categories": ["workshop"], "date_from": null, "date_to": null, '
    '"free_only": false}'
)
EMPTY_JSON = (
    '{"keywords": [], "city": null, "categories": [], '
    '"date_from": null, "date_to": null, "free_only": false}'
)
BAD_CATEGORY_JSON = '{"categories": ["concert"]}'  # not in EventCategory
BAD_DATE_RANGE_JSON = '{"date_from": "2026-09-01", "date_to": "2026-08-01"}'


class ScriptedGemini(GeminiQueryParser):
    """GeminiQueryParser with `_generate` replaced by a scripted response queue."""

    def __init__(self, script, fallback=None):
        super().__init__(api_key="test-key", model="test-model", fallback=fallback)
        self._script = list(script)
        self.calls = 0

    async def _generate(self, prompt: str) -> str:
        self.calls += 1
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def run(coro):
    return asyncio.run(coro)


# --------------------------- Gemini parser paths ---------------------------


def test_successful_parsing():
    parser = ScriptedGemini([VALID_JSON])
    query = run(parser.parse("AI workshops in Bangalore"))
    assert parser.calls == 1
    assert query.city == "Bangalore"
    assert query.categories == [EventCategory.WORKSHOP]
    assert query.keywords == ["machine learning"]


def test_retry_path_recovers_after_one_bad_response():
    parser = ScriptedGemini(["this is not json", VALID_JSON])
    query = run(parser.parse("AI workshops in Bangalore"))
    assert parser.calls == 2  # retried exactly once
    assert query.city == "Bangalore"


def test_malformed_output_twice_falls_back_to_deterministic():
    parser = ScriptedGemini(["garbage", "still garbage"], fallback=KeywordQueryParser())
    query = run(parser.parse("free AI meetup in Pune"))
    assert parser.calls == 2
    # Result is the deterministic parse of the text.
    assert query.city == "Pune"
    assert query.free_only is True
    assert EventCategory.AI in query.categories
    assert EventCategory.MEETUP in query.categories


def test_schema_violation_is_rejected_then_falls_back():
    # "concert" is not a valid EventCategory -> ValidationError on both attempts.
    parser = ScriptedGemini([BAD_CATEGORY_JSON, BAD_CATEGORY_JSON])
    query = run(parser.parse("hackathons in Hyderabad"))
    assert parser.calls == 2
    assert isinstance(query, SearchQuery)
    assert query.city == "Hyderabad"  # from fallback


def test_model_date_range_validator_is_enforced():
    # Our SearchQuery validator (date_from <= date_to) must reject bad Gemini output.
    parser = ScriptedGemini([BAD_DATE_RANGE_JSON, BAD_DATE_RANGE_JSON])
    query = run(parser.parse("conferences next month"))
    assert parser.calls == 2  # both rejected -> fell back
    assert isinstance(query, SearchQuery)


def test_api_error_degrades_to_fallback():
    parser = ScriptedGemini([RuntimeError("503"), RuntimeError("503 again")])
    query = run(parser.parse("startup events in Mumbai"))
    assert parser.calls == 2
    assert query.city == "Mumbai"
    assert EventCategory.STARTUP in query.categories


def test_empty_input_short_circuits_without_calling_gemini():
    parser = ScriptedGemini([VALID_JSON])
    for text in ("", "   ", "\n\t"):
        query = run(parser.parse(text))
        assert query == SearchQuery()
    assert parser.calls == 0  # Gemini never called


def test_ambiguous_query_returns_valid_empty_query():
    parser = ScriptedGemini([EMPTY_JSON])
    query = run(parser.parse("what's happening"))
    assert parser.calls == 1
    assert query == SearchQuery()


def test_code_fenced_json_is_still_parsed():
    fenced = f"```json\n{VALID_JSON}\n```"
    parser = ScriptedGemini([fenced])
    query = run(parser.parse("AI workshops in Bangalore"))
    assert parser.calls == 1
    assert query.city == "Bangalore"


# --------------------------- Deterministic parser ---------------------------


def test_keyword_parser_extracts_and_normalizes():
    parser = KeywordQueryParser()
    query = run(parser.parse("free machine learning webinars in Bengaluru"))
    assert query.city == "Bangalore"  # alias normalized
    assert query.free_only is True
    assert EventCategory.WEBINAR in query.categories
    assert EventCategory.AI in query.categories  # "machine learning"
    assert "machine" in query.keywords and "learning" in query.keywords


def test_keyword_parser_ambiguous_is_valid_and_empty():
    parser = KeywordQueryParser()
    query = run(parser.parse("events near me"))
    assert isinstance(query, SearchQuery)
    assert query.city is None
    assert query.categories == []


def test_keyword_parser_empty_input():
    parser = KeywordQueryParser()
    assert run(parser.parse("")) == SearchQuery()


@pytest.mark.parametrize(
    "text, city",
    [
        ("meetups in gurugram", "Gurgaon"),
        ("conf in new delhi", "Delhi"),
        ("hackathon in bombay", "Mumbai"),
    ],
)
def test_keyword_parser_city_aliases(text, city):
    parser = KeywordQueryParser()
    assert run(parser.parse(text)).city == city


# --------------------------- observability counters ---------------------------


def test_gemini_counters_on_success():
    parser = ScriptedGemini([VALID_JSON])
    run(parser.parse("AI workshops in Bangalore"))
    assert parser.gemini_calls == 1
    assert parser.fallback_count == 0


def test_gemini_counters_on_retry_then_fallback():
    parser = ScriptedGemini(["bad", "bad"], fallback=KeywordQueryParser())
    run(parser.parse("free AI meetup in Pune"))
    assert parser.gemini_calls == 2  # two API attempts
    assert parser.fallback_count == 1  # then fell back


def test_gemini_counters_not_incremented_on_empty_input():
    parser = ScriptedGemini([VALID_JSON])
    run(parser.parse("   "))
    assert parser.gemini_calls == 0
    assert parser.fallback_count == 0
