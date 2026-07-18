"""Semantic block extractor (Phase 10B) — cards, panels, accordions, hero & registration sections.

The catch-all for pages with no structured data: identify visually-semantic event blocks by class
name (card / event / panel / accordion / hero / timeline / announcement / news / session / listing)
and pull a title + date + link from each. Best-effort and bounded (a windowed scan, not a full DOM
parse), so it is deliberately lower-confidence than the structured extractors and is deduped by
title.
"""

from __future__ import annotations

import re

from app.universal.extractors.base import raw_from_text
from app.universal.models import ExtractionResult, ExtractionSource, Page, RawEvent
from app.universal.text_utils import find_date, strip_tags

_BLOCK_OPEN = re.compile(
    r"<(?:div|article|section|li)\b[^>]*class=[\"'][^\"']*"
    r"(?:card|event|panel|accordion|hero|timeline|announce|news|session|listing|tile|talk|schedule)"
    r"[^\"']*[\"'][^>]*>",
    re.IGNORECASE,
)
_HEADING = re.compile(
    r"<(?:h[1-6]|strong|a)\b[^>]*>(.*?)</(?:h[1-6]|strong|a)>", re.IGNORECASE | re.DOTALL
)
_WINDOW = 1200


class SemanticBlockExtractor:
    source = ExtractionSource.SEMANTIC

    def extract(self, page: Page) -> ExtractionResult:
        html = page.html
        events: list[RawEvent] = []
        seen: set[str] = set()
        for m in _BLOCK_OPEN.finditer(html):
            body = html[m.end() : m.end() + _WINDOW]
            heading = _HEADING.search(body)
            if not heading:
                continue
            title = strip_tags(heading.group(1)).strip()
            block_text = strip_tags(body)
            if len(title) < 3 or not find_date(title + " " + block_text[:400]):
                continue
            key = " ".join(title.lower().split())[:60]
            if key in seen:
                continue
            seen.add(key)
            events.append(
                raw_from_text(
                    self.source,
                    title=title,
                    title_snippet=f"semantic block heading: {title[:50]}",
                    text=block_text[:600],
                    base_url=page.url,
                    conf=0.4,
                    html=body,
                )
            )
            if len(events) >= 100:
                break
        return ExtractionResult(
            source=self.source, events=events, note=f"{len(events)} semantic blocks"
        )
