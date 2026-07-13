"""Focused live check: bad 1st response -> REAL Gemini recovers on retry.

Uses a relative-date query. The deterministic fallback never sets dates, so a
non-null date in the result proves the retry was served by real Gemini (not the
fallback). Only 2 API calls, staying under the 15/min free-tier limit.
"""

from __future__ import annotations

import asyncio

from app.config import get_settings
from app.parsers.gemini import GeminiQueryParser
from app.parsers.keyword import KeywordQueryParser

SETTINGS = get_settings()


class RetryOnce(GeminiQueryParser):
    def __init__(self) -> None:
        super().__init__(
            api_key=SETTINGS.gemini_api_key,
            model=SETTINGS.gemini_model,
            fallback=KeywordQueryParser(),
        )
        self.calls = 0

    async def _generate(self, prompt: str) -> str:
        self.calls += 1
        if self.calls == 1:
            return "deliberately not json {"
        return await GeminiQueryParser._generate(self, prompt)


async def main() -> None:
    demo = RetryOnce()
    result = await demo.parse("AI workshops in Bangalore tomorrow")
    print(f"generate calls: {demo.calls}")
    print(f"result: {result.model_dump(mode='json')}")
    served_by_gemini = result.date_from is not None
    print(
        "VERDICT:",
        "real Gemini recovered on retry (date set)"
        if served_by_gemini
        else "fell back to deterministic (no date) — rate-limited, retry to confirm",
    )


if __name__ == "__main__":
    asyncio.run(main())
