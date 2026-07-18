"""Phase 3G Step-1 investigation probe (NOT a test, NOT wired into prod).

Checks which candidate providers are reachable + what they expose, so evaluation is
driven by real data, never assumption. Bevy candidates are hit with the shared Bevy API
path; others are fetched raw and sniffed for structured data. Read-only GETs.
"""

from __future__ import annotations

import asyncio
from datetime import date

import httpx

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
TODAY = date.today().isoformat()

# Candidate Bevy-platform hosts (each viable one becomes a ~6-line provider).
BEVY = {
    "gdg (CONTROL)": "https://gdg.community.dev/api/event/",
    "cncf (CONTROL)": "https://community2.cncf.io/api/event/",
    "atlassian-ACE": "https://ace.atlassian.com/api/event/",
    "salesforce-trailblazer": "https://trailblazercommunitygroups.com/api/event/",
    "womenwhocode": "https://www.womenwhocode.com/api/event/",
    "mongodb": "https://community.mongodb.com/api/event/",
    "twilio-champions": "https://twiliochampions.bevy.com/api/event/",
    "aws-community": "https://community.aws/api/event/",
    "postman": "https://community.postman.com/api/event/",
    "uipath": "https://events.uipath.com/api/event/",
    "bevy-demo": "https://www.bevy.com/api/event/",
}

# Other candidate sources (sniff for JSON / __NEXT_DATA__ / JSON-LD).
GENERIC = {
    "commudle-api-events": "https://www.commudle.com/api/v2/events",
    "commudle-home": "https://www.commudle.com/",
    "allevents-blr-tech": "https://allevents.in/bangalore/technology",
    "10times-india-tech": "https://10times.com/india/technology",
    "meetup-find": "https://www.meetup.com/find/?keywords=technology&location=in--Bangalore",
}


async def probe_bevy(client: httpx.AsyncClient, name: str, url: str) -> str:
    try:
        r = await client.get(
            url,
            params={"status": "Published", "order_by": "-start_date", "per_page": 5, "page": 1},
            headers={"Accept": "application/json"},
        )
    except Exception as exc:  # noqa: BLE001 - probe: report any failure
        return f"{name:26s} ERR   {type(exc).__name__}: {str(exc)[:50]}"
    ct = r.headers.get("content-type", "")[:20]
    if r.status_code != 200 or "json" not in ct:
        return f"{name:26s} {r.status_code}   ct={ct} len={len(r.content)}"
    try:
        results = r.json().get("results", [])
    except ValueError:
        return f"{name:26s} 200   non-JSON body"
    india = sum(
        1
        for e in results
        if (e.get("chapter") or {}).get("country") == "IN"
        and (e.get("start_date") or "")[:10] >= TODAY
    )
    sample = results[0].get("title", "")[:34] if results else ""
    return f"{name:26s} OK    results={len(results):<3} india_upcoming={india} | {sample}"


async def probe_generic(client: httpx.AsyncClient, name: str, url: str) -> str:
    try:
        r = await client.get(url, headers={"Accept": "text/html,application/json"})
    except Exception as exc:  # noqa: BLE001
        return f"{name:26s} ERR   {type(exc).__name__}: {str(exc)[:50]}"
    ct = r.headers.get("content-type", "")[:24]
    body = r.text
    signals = []
    if "application/json" in ct:
        signals.append("JSON")
    if "__NEXT_DATA__" in body:
        signals.append("NEXT_DATA")
    if "application/ld+json" in body:
        signals.append("JSON-LD")
    if '"@type":"Event"' in body or '"@type": "Event"' in body:
        signals.append("Event-schema")
    return f"{name:26s} {r.status_code}   ct={ct} len={len(body)} {' '.join(signals) or '(no structured signal)'}"


async def main() -> None:
    async with httpx.AsyncClient(
        timeout=15.0, follow_redirects=True, headers={"User-Agent": UA}
    ) as client:
        print(f"today={TODAY}\n=== BEVY candidates ===")
        for name, url in BEVY.items():
            print(await probe_bevy(client, name, url))
        print("\n=== OTHER candidates ===")
        for name, url in GENERIC.items():
            print(await probe_generic(client, name, url))


if __name__ == "__main__":
    asyncio.run(main())
