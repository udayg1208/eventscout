"""Phase 3G research — mine curated India-tech-community directories for real source URLs,
then probe-confirm the Meetup ICS feeds + Bevy hosts. Feeds SOURCE_CATALOG.md. Read-only.
"""

from __future__ import annotations

import asyncio
import re
from collections import Counter

import httpx

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
URL_RE = re.compile(r'https?://[^\s\)\]<>"|]+')
VEVENT = re.compile(r"BEGIN:VEVENT")

DIRECTORIES = [
    "https://raw.githubusercontent.com/omrajsharma/tech-communities/master/README.md",
    "https://raw.githubusercontent.com/omrajsharma/tech-communities/main/README.md",
    "https://raw.githubusercontent.com/uditwapt/Tech-Communities/main/README.md",
    "https://raw.githubusercontent.com/uditwapt/Tech-Communities/master/README.md",
    "https://raw.githubusercontent.com/GDG-India/awesome-gdg-gde/main/README.md",
    "https://raw.githubusercontent.com/GDG-India/awesome-gdg-gde/master/README.md",
]


def meetup_slug(url: str) -> str | None:
    m = re.search(r"meetup\.com/([A-Za-z0-9\-]+)", url)
    if m and m.group(1) not in {"find", "topics", "cities", "pro", "en-US", "help", "blog"}:
        return m.group(1)
    return None


async def main() -> None:
    async with httpx.AsyncClient(timeout=25.0, follow_redirects=True, headers={"User-Agent": UA}) as client:
        urls: set[str] = set()
        for d in DIRECTORIES:
            try:
                r = await client.get(d)
                if r.status_code == 200:
                    found = URL_RE.findall(r.text)
                    urls |= set(found)
                    print(f"  fetched {d.split('/')[4]}/{d.split('/')[6]}: {len(found)} urls ({len(r.text)}B)")
            except Exception as exc:  # noqa: BLE001
                print(f"  {d}: ERR {type(exc).__name__}")

        meetup_slugs = sorted({s for u in urls if (s := meetup_slug(u))})
        bevy = sorted({u for u in urls if any(k in u for k in ("community.dev", "bevy.com", "community.cncf", "trailblazer", "usergroups."))})
        domains = Counter(re.sub(r"https?://(www\.)?", "", u).split("/")[0] for u in urls)

        print(f"\nEXTRACTED: {len(urls)} urls | {len(meetup_slugs)} meetup slugs | {len(bevy)} bevy-ish")
        print(f"MEETUP slugs ({len(meetup_slugs)}): {meetup_slugs[:60]}")
        print(f"BEVY-ish: {bevy[:20]}")
        print(f"top domains: {domains.most_common(25)}")

        # probe-confirm the discovered Meetup slugs (ICS reachability + event count)
        sample = meetup_slugs[:70]
        print(f"\n=== probing {len(sample)} discovered Meetup ICS feeds ===")

        async def probe(slug: str):
            try:
                r = await client.get(f"https://www.meetup.com/{slug}/events/ical/")
                return slug, (len(VEVENT.findall(r.text)) if r.status_code == 200 else -r.status_code)
            except Exception:  # noqa: BLE001
                return slug, None

        results = await asyncio.gather(*(probe(s) for s in sample))
        reachable = [(s, n) for s, n in results if isinstance(n, int) and n >= 0]
        with_events = [(s, n) for s, n in reachable if n > 0]
        total_ev = sum(n for _, n in with_events)
        for s, n in sorted(with_events, key=lambda x: -x[1]):
            print(f"  {s:40s} {n}")
        print(
            f"\nof {len(sample)} probed: {len(reachable)} reachable(200), "
            f"{len(with_events)} with upcoming events, {total_ev} VEVENTs"
        )


if __name__ == "__main__":
    asyncio.run(main())
