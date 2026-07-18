"""Phase 3G redesign — feasibility investigation across SOURCE TYPES (not single sites).

Goal: prove/disprove whether generic source-type families (Meetup groups, ICS calendars,
RSS, JSON-LD pages, GitHub directories) can collectively reach thousands of India tech
events at ₹0. Read-only probes; reports the mechanism signal + a rough yield per type.
"""

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


async def get(client, url, **kw):
    try:
        return await client.get(url, **kw)
    except Exception as exc:  # noqa: BLE001
        return exc


def sig(r) -> str:
    if isinstance(r, Exception):
        return f"ERR {type(r).__name__}: {str(r)[:44]}"
    body = r.text
    parts = [f"{r.status_code}", f"len={len(body)}"]
    if "BEGIN:VEVENT" in body:
        parts.append(f"ICS_VEVENTS={body.count('BEGIN:VEVENT')}")
    if "__NEXT_DATA__" in body:
        parts.append("NEXT_DATA")
    if "application/ld+json" in body:
        n = sum(1 for b in LD.findall(body) if '"Event"' in b)
        parts.append(f"JSONLD_Event_blocks~{n}")
    if body.lstrip().startswith(("{", "[")) and "json" in r.headers.get("content-type", ""):
        parts.append("JSON")
    return " ".join(parts)


async def main() -> None:
    async with httpx.AsyncClient(
        timeout=20.0, follow_redirects=True, headers={"User-Agent": UA}
    ) as client:
        print("=== MEETUP (each group = a small provider; hundreds of India tech groups) ===")
        meetup = {
            "meetup-REST-api": "https://api.meetup.com/pydelhi/events",
            "meetup-ical-pydelhi": "https://www.meetup.com/pydelhi/events/ical/",
            "meetup-ical-bangpypers": "https://www.meetup.com/bangpypers/events/ical/",
            "meetup-page-pydelhi": "https://www.meetup.com/pydelhi/events/",
            "meetup-gql": "https://www.meetup.com/gql",
        }
        for name, url in meetup.items():
            print(f"  {name:26s} {sig(await get(client, url))}")

        print("\n=== ICS CALENDARS (one generic parser handles all; scalable family) ===")
        ics = {
            "python.org-ics": "https://www.python.org/events/python-events/ical/",
            "indiafoss-luma-ics": "https://lu.ma/indiafoss.ics",
            "google-cal-sample": "https://calendar.google.com/calendar/ical/en.indian%23holiday%40group.v.calendar.google.com/public/basic.ics",
        }
        for name, url in ics.items():
            print(f"  {name:26s} {sig(await get(client, url))}")

        print("\n=== RSS / newsletters ===")
        rss = {
            "python.org-rss": "https://www.python.org/events/python-events/rss/",
            "reddit-devsindia-rss": "https://www.reddit.com/r/developersIndia/.rss",
        }
        for name, url in rss.items():
            r = await get(client, url)
            extra = "" if isinstance(r, Exception) else f" items~{r.text.count('<item') + r.text.count('<entry')}"
            print(f"  {name:26s} {sig(r)}{extra}")

        print("\n=== JSON-LD community/conf pages (generic crawler over a URL list) ===")
        jsonld = {
            "rootconf(hasgeek)": "https://hasgeek.com/rootconf/",
            "kubernetes-community": "https://kubernetes.io/community/",
            "python-events-india": "https://www.python.org/events/",
        }
        for name, url in jsonld.items():
            print(f"  {name:26s} {sig(await get(client, url))}")

        print("\n=== GitHub community-maintained directories (keyless search API) ===")
        r = await get(
            client,
            "https://api.github.com/search/repositories",
            params={"q": "tech events india OR developer meetups india", "per_page": 8},
            headers={"Accept": "application/vnd.github+json"},
        )
        if not isinstance(r, Exception) and r.status_code == 200:
            for repo in r.json().get("items", [])[:8]:
                print(f"  ★{repo['stargazers_count']:<5} {repo['full_name']}: {(repo.get('description') or '')[:60]}")
        else:
            print(f"  github search: {sig(r)}")


if __name__ == "__main__":
    asyncio.run(main())
