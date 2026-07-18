"""Quantify the one newly-found accessible source: Eventbrite India tech discovery (JSON-LD)."""

from __future__ import annotations

import asyncio
import json
import re

import httpx

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
LD = re.compile(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', re.DOTALL)
CITIES = ["bengaluru", "delhi", "mumbai", "hyderabad", "pune", "chennai"]


def events(html: str) -> list[dict]:
    out = []
    for b in LD.findall(html):
        try:
            data = json.loads(b)
        except ValueError:
            continue
        items = data if isinstance(data, list) else [data]
        for it in items:
            if isinstance(it, dict) and it.get("@type") == "Event":
                out.append(it)
    return out


async def main() -> None:
    async with httpx.AsyncClient(follow_redirects=True, headers={"User-Agent": UA}, timeout=25.0) as client:
        total, all_titles = 0, []
        for c in CITIES:
            try:
                r = await client.get(f"https://www.eventbrite.com/d/india--{c}/technology--events/")
                evs = events(r.text) if r.status_code == 200 else []
            except Exception as exc:  # noqa: BLE001
                print(f"  {c:12s} ERR {type(exc).__name__}")
                continue
            total += len(evs)
            all_titles += [e.get("name", "") for e in evs]
            print(f"  {c:12s} {r.status_code} JSON-LD events={len(evs)}")
        print(f"\nTOTAL across {len(CITIES)} cities (gross, pre-dedup): {total}")
        print("sample titles (quality check — tech vs mixed):")
        for t in all_titles[:14]:
            print(f"  - {t[:70]}")


if __name__ == "__main__":
    asyncio.run(main())
