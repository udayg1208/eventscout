"""Phase 3G Step-1 investigation, pass 2: harvest more Bevy hosts + Indian sources."""

from __future__ import annotations

import asyncio
from datetime import date

import httpx

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
TODAY = date.today().isoformat()

BEVY = {
    "snowflake-ug": "https://usergroups.snowflake.com/api/event/",
    "hashicorp-ug": "https://www.hashicorpusergroups.com/api/event/",
    "notion.bevy": "https://notion.bevy.com/api/event/",
    "figma.bevy": "https://figma.bevy.com/api/event/",
    "databricks": "https://www.databricks.com/api/event/",
    "neo4j": "https://neo4j.com/api/event/",
    "grafana": "https://grafana.com/api/event/",
    "kong": "https://konghq.com/api/event/",
    "developer.bevy": "https://developer.bevy.com/api/event/",
    "elastic-ug": "https://community.elastic.co/api/event/",
    "redis": "https://redis.io/api/event/",
    "gitlab": "https://about.gitlab.com/api/event/",
    "twilio-signal": "https://signal.twilio.com/api/event/",
    "aws-ug-india": "https://aws-community-day.bevy.com/api/event/",
}

GENERIC = {
    "commudle-api": "https://api.commudle.com/api/v2/all_events",
    "commudle-api2": "https://www.commudle.com/api/v2/all_events",
    "devpost-hack": "https://devpost.com/api/hackathons?challenge_type[]=in-person&search=india",
    "unstop-hack": "https://unstop.com/hackathons",
    "allevents-delhi": "https://allevents.in/newdelhi/technology",
}


async def probe_bevy(client: httpx.AsyncClient, name: str, url: str) -> str:
    try:
        r = await client.get(
            url,
            params={"status": "Published", "order_by": "-start_date", "per_page": 5, "page": 1},
            headers={"Accept": "application/json"},
        )
    except Exception as exc:  # noqa: BLE001
        return f"{name:22s} ERR   {type(exc).__name__}: {str(exc)[:44]}"
    ct = r.headers.get("content-type", "")[:18]
    if r.status_code != 200 or "json" not in ct:
        return f"{name:22s} {r.status_code}   ct={ct}"
    try:
        results = r.json().get("results", [])
    except ValueError:
        return f"{name:22s} 200   non-JSON"
    india = sum(
        1
        for e in results
        if (e.get("chapter") or {}).get("country") == "IN"
        and (e.get("start_date") or "")[:10] >= TODAY
    )
    return f"{name:22s} OK    results={len(results):<3} india_upcoming={india}"


async def probe_generic(client: httpx.AsyncClient, name: str, url: str) -> str:
    try:
        r = await client.get(url, headers={"Accept": "text/html,application/json"})
    except Exception as exc:  # noqa: BLE001
        return f"{name:22s} ERR   {type(exc).__name__}: {str(exc)[:44]}"
    ct = r.headers.get("content-type", "")[:24]
    body = r.text
    sig = []
    if "application/json" in ct:
        sig.append("JSON")
    if "__NEXT_DATA__" in body:
        sig.append("NEXT_DATA")
    if "application/ld+json" in body:
        sig.append("JSON-LD")
    if '"@type":"Event"' in body or '"@type": "Event"' in body:
        sig.append("Event-schema")
    if '"hackathons"' in body or '"challenge' in body:
        sig.append("hack-json")
    return f"{name:22s} {r.status_code}   ct={ct} len={len(body)} {' '.join(sig) or '(none)'}"


async def main() -> None:
    async with httpx.AsyncClient(
        timeout=15.0, follow_redirects=True, headers={"User-Agent": UA}
    ) as client:
        print(f"today={TODAY}\n=== BEVY candidates (pass 2) ===")
        for name, url in BEVY.items():
            print(await probe_bevy(client, name, url))
        print("\n=== INDIAN / aggregator candidates ===")
        for name, url in GENERIC.items():
            print(await probe_generic(client, name, url))


if __name__ == "__main__":
    asyncio.run(main())
