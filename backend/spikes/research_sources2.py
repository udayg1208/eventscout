"""Phase 3G research pass 2 — ground the catalog: informed Meetup batch + India platforms + Lu.ma."""

from __future__ import annotations

import asyncio
import re

import httpx

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
VEVENT = re.compile(r"BEGIN:VEVENT")

# Informed India tech Meetup slugs (real communities across cities × stacks).
SLUGS = [
    "bangpypers", "pydelhi", "chennaipy", "PythonPune", "hyderabad-python-meetup-group",
    "bangalorejs", "delhijs", "ReactJS-Bangalore", "angular-india", "vuejs-bangalore",
    "aws-user-group-bengaluru", "awsugblr", "AWS-UG-Delhi", "aws-user-group-hyderabad",
    "azure-developer-community-bangalore", "Bangalore-Kubernetes-Meetup", "docker-bangalore",
    "DevOps-Bangalore", "devopsdays-india", "cloud-native-hyderabad",
    "DataScience-Bangalore", "blr-ai-ml", "Deep-Learning-Bangalore", "PyData-Mumbai",
    "Blrdroid", "flutter-bangalore", "Kotlin-Bangalore", "Bangalore-Golang-Meetup",
    "gophers-bangalore", "RustMumbai", "rust-india",
    "Bangalore-Salesforce-Developer-Group", "wordpress-bangalore", "GraphQL-Bangalore",
    "blockchain-bangalore", "TensorFlow-Bangalore", "women-who-code-bangalore",
    "Mumbai-Tech-Meetup", "hasgeek", "The-Fifth-Elephant", "javascript-meetup-bangalore",
]

PLATFORMS = {
    "commudle-v1": "https://www.commudle.com/api/v1/events",
    "commudle-sitemap": "https://www.commudle.com/sitemap.xml",
    "konfhub": "https://konfhub.com/",
    "konfhub-explore": "https://konfhub.com/explore",
    "townscript-tech": "https://www.townscript.com/discover/all/technology",
    "kommunity": "https://kommunity.com/",
    "meraevents-tech": "https://www.meraevents.com/allevents?catId=1",
}

LUMA_CITIES = ["bangalore", "delhi", "mumbai", "hyderabad", "pune", "chennai", "kolkata", "goa"]


def sig(r) -> str:
    if isinstance(r, Exception):
        return f"ERR {type(r).__name__}"
    body = r.text
    s = [f"{r.status_code}", f"{len(body)}B"]
    if "__NEXT_DATA__" in body:
        s.append("NEXT_DATA")
    if "application/ld+json" in body:
        s.append("JSON-LD")
    if '"@type":"Event"' in body or '"@type": "Event"' in body:
        s.append("Event-schema")
    if body.lstrip()[:1] in ("{", "[") and "json" in r.headers.get("content-type", ""):
        s.append("JSON")
    if "<urlset" in body or "<sitemapindex" in body:
        s.append(f"SITEMAP(urls~{body.count('<loc>')})")
    return " ".join(s)


async def main() -> None:
    async with httpx.AsyncClient(timeout=25.0, follow_redirects=True, headers={"User-Agent": UA}) as client:
        async def ics(slug):
            try:
                r = await client.get(f"https://www.meetup.com/{slug}/events/ical/")
                return slug, (len(VEVENT.findall(r.text)) if r.status_code == 200 else -r.status_code)
            except Exception:  # noqa: BLE001
                return slug, None

        print(f"=== Meetup ICS: {len(SLUGS)} informed slugs ===")
        res = await asyncio.gather(*(ics(s) for s in SLUGS))
        reachable = [(s, n) for s, n in res if isinstance(n, int) and n >= 0]
        with_ev = [(s, n) for s, n in reachable if n > 0]
        for s, n in sorted(reachable, key=lambda x: -x[1]):
            tag = f"  {n} events" if n > 0 else " (reachable, 0)"
            print(f"  {s:42s}{tag}")
        print(f"  → {len(reachable)}/{len(SLUGS)} reachable, {len(with_ev)} with events, "
              f"{sum(n for _, n in with_ev)} VEVENTs")

        print("\n=== India platforms ===")
        for name, url in PLATFORMS.items():
            try:
                r = await client.get(url, headers={"Accept": "text/html,application/json,application/xml"})
                print(f"  {name:22s} {sig(r)}")
            except Exception as exc:  # noqa: BLE001
                print(f"  {name:22s} ERR {type(exc).__name__}")

        print("\n=== Lu.ma India city pages (embedded event data) ===")
        for c in LUMA_CITIES:
            try:
                r = await client.get(f"https://lu.ma/{c}")
                ev = r.text.count('"event":') + r.text.count('"api_id":"evt')
                print(f"  lu.ma/{c:12s} {r.status_code} {len(r.text)}B events~{ev}")
            except Exception as exc:  # noqa: BLE001
                print(f"  lu.ma/{c:12s} ERR {type(exc).__name__}")


if __name__ == "__main__":
    asyncio.run(main())
