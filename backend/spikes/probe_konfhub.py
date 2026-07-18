"""P0.3 implementation inspection — KonfHub data shape (needed to write the provider)."""

from __future__ import annotations

import asyncio
import json
import re

import httpx

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
LD = re.compile(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', re.DOTALL)
NEXT = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)


def walk_events(obj):
    if isinstance(obj, dict):
        if obj.get("@type") == "Event":
            yield obj
        for v in obj.values():
            yield from walk_events(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_events(v)


async def main() -> None:
    async with httpx.AsyncClient(timeout=25.0, follow_redirects=True, headers={"User-Agent": UA}) as client:
        # candidate API endpoints
        for name, url in {
            "api-events": "https://api.konfhub.com/event/all",
            "api-list": "https://api.konfhub.com/events",
            "konfhub-api": "https://konfhub.com/api/events",
        }.items():
            try:
                r = await client.get(url, headers={"Accept": "application/json"})
                print(f"  {name:14s} {r.status_code} ct={r.headers.get('content-type','')[:20]} len={len(r.text)}")
            except Exception as exc:  # noqa: BLE001
                print(f"  {name:14s} ERR {type(exc).__name__}")

        r = await client.get("https://konfhub.com/")
        # JSON-LD events
        ld_events = []
        for block in LD.findall(r.text):
            try:
                ld_events.extend(walk_events(json.loads(block)))
            except ValueError:
                continue
        print(f"\nhomepage JSON-LD Event nodes: {len(ld_events)}")
        for e in ld_events[:3]:
            loc = e.get("location") or {}
            print(json.dumps({
                "name": e.get("name"), "startDate": e.get("startDate"), "endDate": e.get("endDate"),
                "url": e.get("url"), "mode": e.get("eventAttendanceMode"),
                "location": (loc.get("name") if isinstance(loc, dict) else loc),
                "offers": e.get("offers"),
            }, default=str)[:360])

        # NEXT_DATA events
        m = NEXT.search(r.text)
        if m:
            try:
                data = json.loads(m.group(1))
                pp = (data.get("props") or {}).get("pageProps") or {}
                print(f"\nNEXT_DATA pageProps keys: {list(pp)[:12]}")
                # find any list of dicts that look like events
                def find_lists(o, path=""):
                    if isinstance(o, dict):
                        for k, v in o.items():
                            yield from find_lists(v, f"{path}.{k}")
                    elif isinstance(o, list) and o and isinstance(o[0], dict):
                        keys = set(o[0])
                        if keys & {"event_name", "name", "title", "start_date", "start_time"}:
                            yield path, len(o), sorted(keys)[:12]
                for path, n, keys in list(find_lists(pp))[:6]:
                    print(f"  list @ {path}: {n} items, keys={keys}")
            except ValueError:
                print("NEXT_DATA parse failed")


if __name__ == "__main__":
    asyncio.run(main())
