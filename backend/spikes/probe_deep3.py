"""Ecosystem gap analysis — final unprobed candidates: India hackathon/edtech orgs, Eventbrite,
regional conf sites, GitHub event repos. Close the exhaustiveness gap."""

from __future__ import annotations

import asyncio

import httpx

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"


def sig(r) -> str:
    if isinstance(r, Exception):
        return f"ERR {type(r).__name__}"
    b = r.text
    s = [f"{r.status_code}", f"{len(b)//1000}KB"]
    ev = b.count('"@type":"Event"') + b.count('"@type": "Event"')
    for k, lbl in [("__NEXT_DATA__", "NEXT"), ("application/ld+json", "LD"),
                   ("BEGIN:VEVENT", "ICS"), ("<rss", "RSS"), ("<feed", "ATOM")]:
        if k in b:
            s.append(lbl)
    if ev:
        s.append(f"Ev={ev}")
    if b.lstrip()[:1] in "{[" and "json" in r.headers.get("content-type", ""):
        s.append("JSON")
    return " ".join(s)


async def get(client, url, **kw):
    try:
        return await client.get(url, timeout=25.0, **kw)
    except Exception as exc:  # noqa: BLE001
        return exc


async def main() -> None:
    async with httpx.AsyncClient(follow_redirects=True, headers={"User-Agent": UA}) as client:
        candidates = {
            # India hackathon / edtech organizers
            "hack2skill": "https://hack2skill.com/allhackathons",
            "hack2skill-api": "https://api.hack2skill.com/v1/user/events",
            "devnovate": "https://devnovate.co/",
            "reskilll": "https://reskilll.com/allevents",
            "gfg-events": "https://www.geeksforgeeks.org/events/",
            "hackerearth-chal": "https://www.hackerearth.com/challenges/",
            "dev-community": "https://dev.to/search?q=india%20event",
            # Eventbrite org JSON-LD (search API gone; org pages still have JSON-LD)
            "eventbrite-blr": "https://www.eventbrite.com/d/india--bengaluru/technology--events/",
            "eventbrite-org": "https://www.eventbrite.com/o/hasgeek-17999142623",
            # regional conf sites
            "pycon-india": "https://in.pycon.org/2025/",
            "fossasia": "https://eventyay.com/",
            # newsletters / RSS
            "reddit-devsindia": "https://www.reddit.com/r/developersIndia/.rss",
            "lobsters": "https://lobste.rs/",
        }
        for name, url in candidates.items():
            r = await get(client, url, headers={"Accept": "text/html,application/json,application/xml"})
            print(f"  {name:20s} {sig(r)}")

        # GitHub: India tech event data repos (curated, ingestible?)
        print("\n=== GitHub event-data repos ===")
        r = await get(client, "https://api.github.com/search/code",
                      params={"q": "india tech events extension:ics OR extension:yaml filename:events"},
                      headers={"Accept": "application/vnd.github+json"})
        if not isinstance(r, Exception):
            print(f"  github code search: {r.status_code} ({sig(r)})")


if __name__ == "__main__":
    asyncio.run(main())
