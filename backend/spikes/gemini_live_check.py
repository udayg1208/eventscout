"""M3 live verification: run real queries through GeminiQueryParser.

NOT production. Requires GEMINI_API_KEY in backend/.env. Run:
    cd backend
    ./.venv/Scripts/python.exe -m spikes.gemini_live_check

Shows, for each query: the RAW Gemini response and the VALIDATED SearchQuery.
Also verifies response_schema, relative-date resolution, ambiguous input, and
that the retry + fallback paths work against the live API.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date

from app.config import get_settings
from app.models.search import SearchQuery
from app.parsers.gemini import GeminiQueryParser, _strip_code_fences
from app.parsers.keyword import KeywordQueryParser
from app.parsers.prompts import build_prompt

SETTINGS = get_settings()
TODAY = date.today()

QUERIES = [
    "Find AI workshops in Bangalore this weekend",
    "Startup networking events in Pune",
    "Hackathons happening next month",
    "Free machine learning webinars",
    "tech conferences next Saturday",
    "workshops tomorrow",
    "asdkjfh qwoeiu zzz",                 # nonsense / ambiguous
    "concerts and movies in Mumbai",      # out-of-scope subject matter
]


def _make_parser() -> GeminiQueryParser:
    return GeminiQueryParser(
        api_key=SETTINGS.gemini_api_key,
        model=SETTINGS.gemini_model,
        fallback=KeywordQueryParser(),
    )


def _show(label: str, sq: SearchQuery) -> None:
    print(f"    {label}: {json.dumps(sq.model_dump(mode='json'), ensure_ascii=False)}")


async def verify_queries(parser: GeminiQueryParser) -> None:
    print(f"=== Live query verification (today = {TODAY.isoformat()}) ===\n")
    for q in QUERIES:
        print(f"> {q!r}")
        try:
            raw = await parser._generate(build_prompt(q, TODAY))
            print(f"    RAW: {raw.strip()!r}")
            sq = SearchQuery.model_validate_json(_strip_code_fences(raw))
            _show("VALID", sq)
        except Exception as exc:  # noqa: BLE001 - diagnostic script
            print(f"    !! direct generate/validate failed: {type(exc).__name__}: {exc}")
        # Full parse() flow (includes retry/fallback safety net).
        final = await parser.parse(q)
        _show("parse()", final)
        print()


async def verify_no_schema_diag(parser: GeminiQueryParser) -> None:
    """Diagnostic: does a plain JSON call (no response_schema) also work?"""
    print("=== Diagnostic: generation WITHOUT response_schema ===")
    client = parser._client()
    resp = await client.aio.models.generate_content(
        model=parser._model,
        contents=build_prompt("AI workshops in Bangalore this weekend", TODAY),
        config={"response_mime_type": "application/json"},
    )
    print(f"    RAW (no schema): {(resp.text or '').strip()!r}\n")


async def verify_retry(parser: GeminiQueryParser) -> None:
    """First model call returns garbage; the retry hits the REAL API and recovers."""

    class RetryDemo(GeminiQueryParser):
        def __init__(self) -> None:
            super().__init__(
                api_key=parser._api_key,
                model=parser._model,
                fallback=KeywordQueryParser(),
            )
            self.calls = 0

        async def _generate(self, prompt: str) -> str:
            self.calls += 1
            if self.calls == 1:
                return "NOT VALID JSON {broken"
            return await GeminiQueryParser._generate(self, prompt)

    demo = RetryDemo()
    print("=== Retry path against live API (bad 1st response, real 2nd) ===")
    result = await demo.parse("Free machine learning webinars in Hyderabad")
    print(f"    generate calls: {demo.calls} (expected 2)")
    _show("recovered", result)
    print()


async def verify_fallback(parser: GeminiQueryParser) -> None:
    """Both model calls return garbage; must fall back to the deterministic parser."""

    class AlwaysBad(GeminiQueryParser):
        def __init__(self) -> None:
            super().__init__(
                api_key=parser._api_key,
                model=parser._model,
                fallback=KeywordQueryParser(),
            )
            self.calls = 0

        async def _generate(self, prompt: str) -> str:
            self.calls += 1
            return "still not json"

    demo = AlwaysBad()
    print("=== Fallback path (both responses invalid) ===")
    result = await demo.parse("free AI hackathon in Pune")
    print(f"    generate calls: {demo.calls} (expected 2, then fallback)")
    _show("fallback", result)
    print()


async def main() -> None:
    if not SETTINGS.gemini_api_key:
        raise SystemExit("No GEMINI_API_KEY found in backend/.env")
    parser = _make_parser()
    await verify_queries(parser)
    await verify_no_schema_diag(parser)
    await verify_retry(parser)
    await verify_fallback(parser)
    print("Live verification complete.")


if __name__ == "__main__":
    asyncio.run(main())
