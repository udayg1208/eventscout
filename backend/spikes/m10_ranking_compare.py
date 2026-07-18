"""Ranking before/after + component breakdown on the live dataset (not a test)."""

from __future__ import annotations

import asyncio
import logging
from datetime import date

logging.disable(logging.CRITICAL)

from app.city import normalize_city  # noqa: E402
from app.models.event import EventCategory  # noqa: E402
from app.models.search import SearchQuery  # noqa: E402
from app.providers import get_provider  # noqa: E402
from app.providers.ranking import WEIGHTS, completeness, component_scores  # noqa: E402

TODAY = date.today()


def old_score(e, q) -> float:
    """The pre-Phase-2 scorer: 0.50 relevance (kw+city+cat) / 0.35 date / 0.15 completeness."""
    considered, matched = 0, 0.0
    if q.keywords:
        considered += 1
        hay = f"{e.title} {e.description or ''}".casefold()
        bh = sum(1 for k in q.keywords if k.casefold() in hay)
        th = sum(1 for k in q.keywords if k.casefold() in e.title.casefold())
        matched += min(1.0, (bh + th) / (2 * len(q.keywords)))
    if q.city:
        considered += 1
        if e.city and normalize_city(e.city).casefold() == normalize_city(q.city).casefold():
            matched += 1.0
    if q.categories:
        considered += 1
        if e.category in q.categories:
            matched += 1.0
    rel = matched / considered if considered else 0.0
    days = (e.start_date - TODAY).days
    dp = 0.0 if days < 0 else 1.0 / (1.0 + days / 30.0)
    return 0.5 * rel + 0.35 * dp + 0.15 * (completeness(e) / 6)


def old_rank(events, q):
    return sorted(events, key=lambda e: (-old_score(e, q), e.start_date, e.title))


QUERIES = {
    "all upcoming (browse)": SearchQuery(),
    "events in Bangalore": SearchQuery(city="Bangalore"),
    "AI events in Bangalore": SearchQuery(categories=[EventCategory.AI], city="Bangalore"),
}


async def main() -> None:
    prov = get_provider()
    for label, q in QUERIES.items():
        events = await prov.search(q)  # already NEW-ranked
        old = old_rank(list(events), q)
        moved = sum(1 for i, e in enumerate(events[:6]) if i >= len(old) or old[i].url != e.url)
        print(f"\n### {label}  ({len(events)} results, {moved}/6 top positions changed)")
        for i, (o, n) in enumerate(zip(old[:6], events[:6], strict=False), 1):
            flag = "" if o.url == n.url else "  <-- changed"
            print(f"  {i}. OLD: {o.title[:30]:30} [{o.provider[:9]:9}]   NEW: {n.title[:30]:30} [{n.provider[:9]:9}]{flag}")

    q = SearchQuery(categories=[EventCategory.AI], city="Bangalore")
    events = await prov.search(q)
    if events:
        e = events[0]
        print(f"\n### Breakdown — top result: {e.title[:44]} [{e.provider}, {e.city}]")
        total = 0.0
        for name, val in component_scores(e, q, TODAY).items():
            contrib = WEIGHTS[name] * val
            total += contrib
            print(f"  {name:13} {val:.3f} x {WEIGHTS[name]:.2f} = {contrib:.3f}")
        print(f"  {'TOTAL':13} {'':13} = {total:.3f}")


if __name__ == "__main__":
    asyncio.run(main())
