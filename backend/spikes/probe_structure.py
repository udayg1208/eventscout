"""Phase 3G Step-1: inspect the data shape of allevents.in (JSON-LD) + Devpost (JSON)."""

from __future__ import annotations

import asyncio
import json
import re

import httpx

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
LD = re.compile(
    r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', re.DOTALL | re.IGNORECASE
)


def walk(obj):
    """Yield every dict with @type Event from an arbitrary JSON-LD structure."""
    if isinstance(obj, dict):
        t = obj.get("@type")
        if t == "Event" or (isinstance(t, list) and "Event" in t):
            yield obj
        for v in obj.values():
            yield from walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v)


async def allevents(client: httpx.AsyncClient) -> None:
    r = await client.get("https://allevents.in/bangalore/technology")
    events = []
    for block in LD.findall(r.text):
        try:
            events.extend(walk(json.loads(block)))
        except ValueError:
            continue
    print(f"allevents.in/bangalore/technology: {len(events)} JSON-LD Event nodes")
    for e in events[:3]:
        loc = e.get("location") or {}
        addr = loc.get("address") if isinstance(loc, dict) else loc
        print(
            json.dumps(
                {
                    "name": e.get("name"),
                    "startDate": e.get("startDate"),
                    "endDate": e.get("endDate"),
                    "url": e.get("url"),
                    "mode": e.get("eventAttendanceMode"),
                    "location_name": (loc.get("name") if isinstance(loc, dict) else None),
                    "address": addr,
                    "offers": e.get("offers"),
                },
                default=str,
            )[:400]
        )


async def devpost(client: httpx.AsyncClient) -> None:
    r = await client.get(
        "https://devpost.com/api/hackathons",
        params={"search": "india", "order_by": "deadline"},
        headers={"Accept": "application/json"},
    )
    data = r.json()
    hacks = data.get("hackathons", [])
    print(f"\ndevpost api/hackathons?search=india: keys={list(data)[:6]} count={len(hacks)}")
    for h in hacks[:3]:
        print(
            json.dumps(
                {
                    "title": h.get("title"),
                    "url": h.get("url"),
                    "location": h.get("displayed_location"),
                    "submission_period": h.get("submission_period_dates"),
                    "themes": [t.get("name") for t in h.get("themes", [])][:4],
                    "open_state": h.get("open_state"),
                    "prize": h.get("prize_amount"),
                },
                default=str,
            )[:400]
        )


async def main() -> None:
    async with httpx.AsyncClient(
        timeout=20.0, follow_redirects=True, headers={"User-Agent": UA}
    ) as client:
        await allevents(client)
        await devpost(client)


if __name__ == "__main__":
    asyncio.run(main())
