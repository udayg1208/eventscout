"""Phase 3G feasibility — quantify the Meetup-group ICS family + inspect content.

Meetup exposes a public iCalendar feed per group (calendar-subscription feature). Each
India tech group is a small provider. This probe: (1) parses one group's ICS to confirm
buildable fields, (2) samples many group slugs to estimate yield, (3) checks the
GitHub-hosted Loopin.city directory for a data source.
"""

from __future__ import annotations

import asyncio
import re

import httpx

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"


def unfold(text: str) -> str:
    return re.sub(r"\r?\n[ \t]", "", text)


def parse_vevents(ics: str) -> list[dict]:
    events = []
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", unfold(ics), re.DOTALL):
        fields = {}
        for line in block.splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                fields[key.split(";")[0]] = val.strip()
        events.append(fields)
    return events


# India tech Meetup group slugs to sample (mix of cities + stacks).
SLUGS = [
    "bangpypers", "pydelhi", "chennaipy", "hydpy", "mumpy",
    "Bangalore-Kubernetes-Meetup", "awsugblr", "Delhi-NCR-AWS-User-Group",
    "React-Bangalore", "flutter-bangalore", "Bangalore-Golang-Meetup",
    "DataScience-Bangalore", "PyData-Delhi", "rust-bangalore",
    "The-Bangalore-Nodejs-Meetup", "DevOps-Bangalore", "gophers-bangalore",
    "kubernetes-community-days-bengaluru", "aws-user-group-hyderabad", "blockchain-bangalore",
]


async def main() -> None:
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers={"User-Agent": UA}) as client:
        # (1) inspect one group's ICS content
        r = await client.get("https://www.meetup.com/bangpypers/events/ical/")
        events = parse_vevents(r.text)
        print(f"=== bangpypers ICS: {len(events)} VEVENTs ===")
        for e in events[:2]:
            print({k: e.get(k) for k in ("SUMMARY", "DTSTART", "DTEND", "LOCATION", "URL")})

        # (2) sample the group universe
        print("\n=== group-universe yield sample ===")
        total = 0
        live = 0
        async def one(slug):
            try:
                resp = await client.get(f"https://www.meetup.com/{slug}/events/ical/")
                if resp.status_code == 200:
                    return slug, len(parse_vevents(resp.text))
                return slug, -resp.status_code
            except Exception as exc:  # noqa: BLE001
                return slug, str(type(exc).__name__)
        results = await asyncio.gather(*(one(s) for s in SLUGS))
        for slug, n in results:
            mark = ""
            if isinstance(n, int) and n > 0:
                total += n
                live += 1
                mark = "  <-- events"
            print(f"  {slug:36s} {n}{mark}")
        print(f"\nsampled {len(SLUGS)} groups: {live} with upcoming events, {total} total VEVENTs")

        # (3) Loopin.city directory
        print("\n=== Loopin.city (GitHub community directory) ===")
        for url in ("https://loopin.city/", "https://www.loopin.city/api/events", "https://api.loopin.city/events"):
            try:
                resp = await client.get(url, headers={"Accept": "text/html,application/json"})
                ct = resp.headers.get("content-type", "")[:20]
                body = resp.text
                sigs = [s for s in ("__NEXT_DATA__", "application/ld+json", "BEGIN:VEVENT") if s in body]
                jsonish = body.lstrip()[:1] in ("{", "[")
                print(f"  {url:40s} {resp.status_code} ct={ct} len={len(body)} {'JSON' if jsonish else ''} {' '.join(sigs)}")
            except Exception as exc:  # noqa: BLE001
                print(f"  {url:40s} ERR {type(exc).__name__}")


if __name__ == "__main__":
    asyncio.run(main())
