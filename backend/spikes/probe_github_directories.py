"""Phase 3G feasibility — can curation be BOOTSTRAPPED from an existing curated directory?

Discovery isn't automatable, so scale depends on a source-URL catalog. This checks whether
GitHub hosts a curated, ingestible list (like tech-conferences/conference-data already does
for confs.tech) that we could parse into hundreds of sources. Keyless GitHub search API.
"""

from __future__ import annotations

import asyncio

import httpx

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
QUERIES = [
    "india tech communities list",
    "india developer meetups",
    "awesome india tech events",
    "tech conferences india data",
    "developer communities directory",
]


async def main() -> None:
    async with httpx.AsyncClient(timeout=25.0, follow_redirects=True, headers={"User-Agent": UA}) as client:
        seen = set()
        print("=== GitHub curated-directory candidates ===")
        for q in QUERIES:
            try:
                r = await client.get(
                    "https://api.github.com/search/repositories",
                    params={"q": q, "sort": "stars", "per_page": 6},
                    headers={"Accept": "application/vnd.github+json"},
                )
                if r.status_code != 200:
                    print(f"  [{q}] search {r.status_code}")
                    continue
                for repo in r.json().get("items", []):
                    key = repo["full_name"]
                    if key in seen:
                        continue
                    seen.add(key)
                    print(f"  ★{repo['stargazers_count']:<5} {key}: {(repo.get('description') or '')[:64]}")
            except Exception as exc:  # noqa: BLE001
                print(f"  [{q}] ERR {type(exc).__name__}")

        # Inspect the known confs.tech data repo (proves the 'curated GitHub data' pattern)
        print("\n=== tech-conferences/conference-data (the confs.tech source) — topic coverage ===")
        try:
            r = await client.get(
                "https://api.github.com/repos/tech-conferences/conference-data/contents/conferences/2026",
                headers={"Accept": "application/vnd.github+json"},
            )
            if r.status_code == 200:
                files = [f["name"] for f in r.json() if f["name"].endswith(".json")]
                print(f"  2026 topic files: {files}")
            else:
                print(f"  contents {r.status_code}")
        except Exception as exc:  # noqa: BLE001
            print(f"  ERR {type(exc).__name__}")


if __name__ == "__main__":
    asyncio.run(main())
