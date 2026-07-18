"""Ecosystem gap analysis — measure the TRUE India volume of Bevy communities (uncapped),
to test whether the production providers (5-page cap) undercount, and to size the 90-day window.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

import httpx

UA = "Mozilla/5.0 (compatible; EventScout research)"
TODAY = date.today()
D30, D60, D90 = (TODAY + timedelta(days=n) for n in (30, 60, 90))

HOSTS = {
    "GDG": "gdg.community.dev",
    "CNCF": "community2.cncf.io",
    "Atlassian": "ace.atlassian.com",
    "Salesforce": "trailblazercommunitygroups.com",
    "Snowflake": "usergroups.snowflake.com",
}


async def india_volume(client: httpx.AsyncClient, name: str, host: str) -> None:
    """Descending pages, UNCAPPED (up to 25×500), collect all India upcoming."""
    india: list[dict] = []
    chapters: set[str] = set()
    pages = 0
    for page in range(1, 26):
        try:
            r = await client.get(
                f"https://{host}/api/event/",
                params={"status": "Published", "order_by": "-start_date", "per_page": 500, "page": page},
                headers={"Accept": "application/json"},
                timeout=25.0,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"{name}: ERR {type(exc).__name__}")
            return
        if r.status_code != 200:
            break
        results = r.json().get("results", [])
        if not results:
            break
        pages = page
        for e in results:
            ch = e.get("chapter") or {}
            start = (e.get("start_date") or "")[:10]
            if ch.get("country") == "IN" and start >= TODAY.isoformat():
                india.append(e)
                chapters.add(ch.get("title") or ch.get("name") or ch.get("city") or "?")
        oldest = (results[-1].get("start_date") or "")[:10]
        if oldest and oldest < TODAY.isoformat():
            break

    def upto(d):
        return sum(1 for e in india if (e.get("start_date") or "")[:10] <= d.isoformat())

    campus = [
        c for c in chapters
        if c and any(k in c.lower() for k in ("campus", "college", "university", "institute", "on campus", " it "))
    ]
    print(
        f"{name:11s} host={host}: TOTAL India upcoming={len(india)} "
        f"(≤30d={upto(D30)} ≤60d={upto(D60)} ≤90d={upto(D90)}) "
        f"chapters={len(chapters)} campus-like={len(campus)} pages_scanned={pages}"
    )
    if campus[:4]:
        print(f"            campus e.g.: {campus[:4]}")


async def main() -> None:
    print(f"today={TODAY} — production BevyProvider caps at 5 pages; this is UNCAPPED.\n")
    async with httpx.AsyncClient(follow_redirects=True, headers={"User-Agent": UA}) as client:
        for name, host in HOSTS.items():
            await india_volume(client, name, host)


if __name__ == "__main__":
    asyncio.run(main())
