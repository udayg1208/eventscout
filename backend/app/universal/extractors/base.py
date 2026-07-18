"""Extractor protocol + shared field enrichment (Phase 10B).

Every extractor is isolated: it takes a `Page` and returns an `ExtractionResult` of `RawEvent`s,
knowing nothing about the others. `enrich_from_text` is the shared, provenance-bearing helper that
derives the "soft" fields (date, location, technologies, mode, type, fee, registration) from a text
block — used by the textual/semantic extractors so each stays small.
"""

from __future__ import annotations

from typing import Protocol

from app.universal.models import ExtractedField, ExtractionResult, Page, RawEvent
from app.universal.provenance import inferred, known
from app.universal.text_utils import (
    detect_event_type,
    detect_fee,
    detect_location,
    detect_mode,
    detect_technologies,
    find_date,
    find_registration_url,
)


class Extractor(Protocol):
    source: object  # an ExtractionSource

    def extract(self, page: Page) -> ExtractionResult: ...


def enrich_from_text(
    fields: dict[str, ExtractedField],
    text: str,
    *,
    base_url: str = "",
    conf: float = 0.5,
    html: str = "",
) -> None:
    """Fill derived fields from `text` (and optional raw `html` for links) — never overwrites."""

    def put(name: str, ef: ExtractedField) -> None:
        if name not in fields or not fields[name].is_known:
            fields[name] = ef

    if "start_date" not in fields:
        d = find_date(text)
        if d:
            put(
                "start_date",
                known(d[0], snippet=d[1], reason="date pattern in text", confidence=conf),
            )

    city, state, country, loc_snip = detect_location(text)
    if city:
        put("city", known(city, snippet=loc_snip, reason="known city name", confidence=conf))
    if state:
        put(
            "state",
            inferred(state, snippet=loc_snip, reason="Indian state name", confidence=conf * 0.9),
        )
    if country:
        put(
            "country",
            inferred(
                country,
                snippet=loc_snip or country,
                reason="country/city implies country",
                confidence=conf * 0.9,
            ),
        )

    techs = detect_technologies(text)
    if techs:
        put(
            "technologies",
            known(
                techs, snippet=", ".join(techs)[:120], reason="tech taxonomy match", confidence=conf
            ),
        )

    mode = detect_mode(text)
    if mode:
        put(
            "mode",
            known(mode[0], snippet=mode[1], reason="online/offline keyword", confidence=conf * 0.9),
        )

    etype = detect_event_type(text)
    if etype:
        put(
            "event_type",
            known(etype[0], snippet=etype[1], reason="event-type keyword", confidence=conf),
        )

    fee = detect_fee(text)
    if fee:
        put(
            "fee", known(fee[0], snippet=fee[1], reason="fee/price pattern", confidence=conf * 0.85)
        )

    if html:
        reg = find_registration_url(html, base_url)
        if reg:
            put(
                "registration_url",
                known(reg[0], snippet=reg[1], reason="registration link", confidence=conf),
            )


def raw_from_text(
    source,
    *,
    title: str,
    title_snippet: str,
    text: str,
    base_url: str = "",
    conf: float = 0.5,
    html: str = "",
) -> RawEvent:
    """Build a RawEvent from a title + a surrounding text block."""
    fields: dict[str, ExtractedField] = {
        "title": known(title.strip(), snippet=title_snippet, reason="block title", confidence=conf)
    }
    enrich_from_text(fields, text, base_url=base_url, conf=conf, html=html)
    return RawEvent(source=source, fields=fields)
