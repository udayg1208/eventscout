"""Phase 3G feasibility — the decisive test: can we DISCOVER the source universe at scale?

Mechanism (ICS/RSS parsing) is proven; the open question is whether we can programmatically
enumerate hundreds of active India tech Meetup groups (+ other communities). This probes
Meetup's find/search for group urlnames across (topic × city), dedupes, then samples the
discovered groups' ICS feeds to estimate the real upcoming-event yield.
"""

from __future__ import annotations

import asyncio
import re

import httpx

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
URLNAME = re.compile(r'"urlname":"([^"]+)"')
VEVENT = re.compile(r"BEGIN:VEVENT")

TOPICS = ["python", "javascript", "devops", "kubernetes", "data-science", "aws", "react", "golang"]
CITIES = ["Bangalore", "Delhi", "Mumbai", "Hyderabad", "Pune", "Chennai"]


async def find_groups(client, topic, city) -> set[str]:
    try:
        r = await client.get(
            "https://www.meetup.com/find/",
            params={"keywords": topic, "location": f"in--{city}", "source": "GROUPS"},
        )
        if r.status_code == 200:
            return set(URLNAME.findall(r.text))
    except Exception:  # noqa: BLE001
        pass
    return set()


async def ical_count(client, slug) -> int:
    try:
        r = await client.get(f"https://www.meetup.com/{slug}/events/ical/")
        if r.status_code == 200:
            return len(VEVENT.findall(r.text))
    except Exception:  # noqa: BLE001
        pass
    return -1


async def main() -> None:
    async with httpx.AsyncClient(timeout=25.0, follow_redirects=True, headers={"User-Agent": UA}) as client:
        print("=== DISCOVERY: Meetup find (topic × city) → group urlnames ===")
        discovered: set[str] = set()
        # sample a subset of the grid to bound network time
        combos = [(t, c) for t in TOPICS[:5] for c in CITIES[:4]]
        for topic, city in combos:
            slugs = await find_groups(client, topic, city)
            discovered |= slugs
            print(f"  {topic:12s} {city:10s} groups_found={len(slugs)}  running_total={len(discovered)}")

        print(f"\nDISTINCT groups discovered from {len(combos)} searches: {len(discovered)}")
        print("  sample:", sorted(discovered)[:15])

        # sample real yield from discovered groups
        sample = sorted(discovered)[:25]
        print(f"\n=== YIELD: ICS event counts for {len(sample)} discovered groups ===")
        counts = await asyncio.gather(*(ical_count(client, s) for s in sample))
        live = [(s, n) for s, n in zip(sample, counts) if n > 0]
        total = sum(n for _, n in live)
        for slug, n in zip(sample, counts):
            if n > 0:
                print(f"  {slug:40s} {n}")
        groups_ok = sum(1 for n in counts if n >= 0)
        print(
            f"\nsampled {len(sample)}: {groups_ok} reachable, {len(live)} with upcoming events, "
            f"{total} VEVENTs -> avg {total / max(len(sample), 1):.1f} events/group"
        )
        if discovered:
            proj = total / max(len(sample), 1) * len(discovered)
            print(f"PROJECTION: {len(discovered)} discovered groups × avg -> ~{proj:.0f} upcoming events (from THIS search subset)")


if __name__ == "__main__":
    asyncio.run(main())
