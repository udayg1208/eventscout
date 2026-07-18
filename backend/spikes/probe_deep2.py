"""Ecosystem gap analysis — probe the under-explored ecosystems for concurrent + 90d volume."""

from __future__ import annotations

import asyncio
import re

import httpx

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"


def sig(r) -> str:
    if isinstance(r, Exception):
        return f"ERR {type(r).__name__}"
    b = r.text
    s = [f"{r.status_code}", f"{len(b)//1000}KB"]
    for k, lbl in [("__NEXT_DATA__", "NEXT"), ("application/ld+json", "LD"), ('"@type":"Event"', "Ev"),
                   ("BEGIN:VEVENT", "ICS"), ("<urlset", "SMAP"), ("results", "results")]:
        if k in b:
            s.append(lbl)
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
        print("=== MORE BEVY HOSTS (company dev communities w/ possible India chapters) ===")
        bevy = {
            "womentechmakers": "wtm.community.dev", "google-cloud": "cloudcommunity.dev",
            "mlh": "mlh.community.dev", "postman": "community-postman.bevy.com",
            "datastax": "datastax.bevy.com", "couchbase": "couchbase.bevy.com",
            "influxdata": "influxdata.bevy.com", "redis": "redis.community.dev",
            "elastic": "elastic.bevy.com", "vmware": "vmware.bevy.com",
            "nvidia": "nvidia.bevy.com", "intel": "intel.bevy.com",
            "sap": "community.sap.com", "oracle": "developer.oracle.com",
            "docker": "dockercommunity.bevy.com",
        }
        for name, host in bevy.items():
            r = await get(client, f"https://{host}/api/event/",
                          params={"status": "Published", "per_page": 3, "page": 1},
                          headers={"Accept": "application/json"})
            if not isinstance(r, Exception) and r.status_code == 200 and "results" in r.text:
                try:
                    res = r.json().get("results", [])
                    india = sum(1 for e in res if (e.get("chapter") or {}).get("country") == "IN")
                    print(f"  {name:16s} OK results={len(res)} india_in_sample={india}")
                except ValueError:
                    print(f"  {name:16s} 200 non-JSON")
            else:
                print(f"  {name:16s} {sig(r)}")

        print("\n=== IEEE vTools (India has ~1000 student branches) ===")
        for name, url in {
            "vtools-home": "https://events.vtools.ieee.org/",
            "vtools-api": "https://events.vtools.ieee.org/api/public/events",
            "vtools-search": "https://events.vtools.ieee.org/m/events?country=IN",
            "vtools-rss": "https://events.vtools.ieee.org/rss",
        }.items():
            print(f"  {name:16s} {sig(await get(client, url))}")

        print("\n=== Meetup Pro networks (chapter enumeration) ===")
        for name, url in {
            "aws-ug-pro": "https://www.meetup.com/pro/aws-user-group",
            "aws-ug-pro2": "https://www.meetup.com/pro/awsugs",
            "gcp-pro": "https://www.meetup.com/pro/google-cloud",
            "womenwhocode-pro": "https://www.meetup.com/pro/women-who-code",
        }.items():
            r = await get(client, url)
            slugs = len(set(re.findall(r'"urlname":"([^"]+)"', r.text))) if not isinstance(r, Exception) else 0
            print(f"  {name:16s} {sig(r)} urlnames~{slugs}")

        print("\n=== India platforms (Commudle / Kommunity / Townscript) ===")
        for name, url in {
            "commudle-sitemap": "https://www.commudle.com/sitemap.xml",
            "commudle-events": "https://www.commudle.com/events",
            "kommunity-in": "https://kommunity.com/discover?country=india",
            "kommunity-tech": "https://kommunity.com/explore?category=technology",
            "townscript-tech": "https://www.townscript.com/discover/all/technology",
        }.items():
            r = await get(client, url)
            ev = 0
            if not isinstance(r, Exception):
                ev = r.text.count('"@type":"Event"') + r.text.count('"@type": "Event"')
            print(f"  {name:16s} {sig(r)} ld_events~{ev}")


if __name__ == "__main__":
    asyncio.run(main())
