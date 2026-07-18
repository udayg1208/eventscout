# Browser Rendering Layer — Phase 11D

**Goal:** discover events that exist only *after* JavaScript executes — the class of sources the
raw-HTML providers (11A–C) proved unreachable, capping the catalog at ~1,850.

**Result:** a real headless-browser fetch layer is built, wired, and measured. It unlocked **3 domains
that returned zero events to raw-HTML fetching** and added **67 tech events discoverable ONLY because
browser rendering exists** (0 duplicates). Catalog: **1,823 → 1,890.**

The browser **only replaces the fetch step** — extraction is the existing Universal Event Engine (10B),
unchanged; validation, dedup, and the catalog are reused as-is.

## What was built

Two files, one new package (`app/rendering/`), one new provider — no extraction rewrite:

### `browser.py` — `BrowserRenderer` (the JS-executing fetch)
Drives a **real headless Chrome** via Playwright, reusing the *system Chrome* (`channel="chrome"` — no
150 MB Chromium download). Per the requirements it:
- **respects robots.txt** (`urllib.robotparser`, per-origin, cached);
- **rate-limits** per domain (min-interval);
- **caches** rendered results (TTL);
- **captures the final rendered DOM** (`page.content()` after `domcontentloaded` + a hydration settle —
  not `networkidle`, which hangs on live-socket SPAs);
- **captures network JSON responses + GraphQL payloads** (a `response` listener records every
  `application/json` body the page fetched at runtime);
- survives per-page nav failures (grabs whatever rendered).

### `provider.py` — `BrowserRenderedProvider(EventProvider)`
For each JS-heavy target: render → **feed the DOM *plus* the captured runtime JSON/GraphQL** (injected
as embedded `<script type="application/json">` blocks so the engine's *existing* embedded-JSON extractor
reads XHR-only events) → `UniversalEventEngine.extract(url, html)` → map `UniversalEvent`s onto the
catalogue `Event` model. The engine call is wrapped defensively so its one crashing code path
(a textual-extractor `IndexError` on certain pages) can't abort an ingestion cycle. A **tech-relevance
gate** drops the non-tech noise that general aggregators (10times/Townscript) carry.

Wired into the registry as provider `rendered` (daily refresh, 600 s timeout). Reuses: **Universal Event
Engine, ingestion validation, cross-provider dedup, the catalog.**

## Feasibility proof (measured, not assumed)

| Gate | Result |
|---|---|
| Headless Chrome launches in this env | ✅ system Chrome, `--no-sandbox`, headless |
| Renders an Angular SPA | ✅ Commudle → 316 KB DOM of real content (raw HTML = empty shell) |
| Universal Engine extracts from rendered DOM | ✅ Commudle 30 · 10times 34 · Townscript 11 events (raw HTML = 0) |
| Captures runtime XHR/GraphQL | ✅ `api.commudle.com/.../all_hackathons`, `townscript.com/listings/.../pagedata` |

## Success metrics (measured)

**The headline number — events discoverable ONLY because browser rendering exists: `67`**
(0 of them duplicate an existing catalog event — these domains were never in the catalog).

| Metric | Value |
|---|---|
| New **domains** unlocked | **3** — `10times.com` (50), `commudle.com` (15), `townscript.com` (2) |
| New **rendered pages** per cycle | 12 (Commudle events/hackathons, 10times × 8 city+topic scopes, Townscript × 2) |
| **Events discovered** (raw → validated → tech-gated) | 249 rendered → 83 upcoming/unique → **67 tech** |
| **Duplicate rate** | 66% collapsed *within* rendering (10times lists an expo across every city page); **0% cross-provider** dupes |
| New **organizers** | 67 events from communities/organizers on 3 platforms never before indexed |
| New **categories mix** | conference 33 · workshop 12 · ai 12 · meetup 8 · startup 1 · hackathon 1 |
| New **cities** in rendered set | Chennai 8 · Hyderabad 7 · Mumbai 6 · Delhi 6 · Bangalore 4 · Pune 2 · Dehradun 1 |
| New **technologies** surfaced | AI/data/security/NLP/computational-intelligence events (e.g. "DataHack Summit", "Securing the Agentic Era", IEEE Computational Intelligence) |
| **Catalog total** | 1,823 → **1,890** |

Sample browser-only events now searchable: *AI Community Day* (Commudle), *PyDelhi Security BOF*
(Commudle), *DataHack Summit* (10times, Bangalore), *Securing the Agentic Era* (10times), *Hack-Nation
India 6th Edition* (Commudle).

## Honest assessment

- **It is a capability unlock, not a volume flood.** 67 net-new is modest in absolute terms — because
  the raw-HTML providers already captured most of the *high-signal* upcoming India-tech events, and the
  JS-gated sources are (a) heavily self-duplicative (10times repeats each expo across city pages → 249
  collapsed to 83) and (b) noisy (10times/Townscript aggregate non-tech events, filtered by the
  tech-gate: 16 dropped, e.g. "Free Chat Astrologer"). The *architecture* is the deliverable: EventScout
  can now read the entire class of JS-rendered sources it previously couldn't.
- **Quality gated honestly.** The tech-gate has recall limits (it keys on tech terms); it recovered
  IEEE/CISO/computational events after a first pass wrongly dropped them, and a few borderline ones
  (drones, nanotech) are still excluded. No event was fabricated — every one is a live rendered page.
- **Konfhub** still crashes the frozen engine's textual extractor; it's skipped defensively (not
  modified — per "do not rewrite extraction").
- **Cost:** a render cycle is ~80 s for 12 pages (one browser, reused). It's a daily job, robots- and
  rate-limit-respecting.

## Scaling this (the lever is now data, not capability)

Growth from here is adding **target URLs**, not new code:
- more 10times city × category scopes, more Commudle pages, Townscript categories;
- **modern university / conference / corporate event portals** (React/Next/Vue) — now readable;
- Konfhub/Kommunity once their pages are added (with the defensive wrapper already in place).
Each new rendered page feeds the same Universal Engine → catalog path.

---

**Status:** Browser Rendering layer complete — headless Chrome replaces the fetch step, the Universal
Event Engine (unchanged) does extraction, and validation/dedup/catalog are reused. **67 events
discoverable only via rendering** (measured, 0 duplicates), **3 new domains unlocked**, catalog
**1,823 → 1,890**. Additive; backend suite **1034 green**; the live app serves 1,890.
