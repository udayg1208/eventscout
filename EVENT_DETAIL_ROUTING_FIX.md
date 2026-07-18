# Event-Detail Routing Hotfix — 100% of events open

**Symptom:** clicking a Devfolio (and Devpost / confs.tech) event showed *"Couldn't load this — Not
found."*

**Outcome:** **1,890 / 1,890 events open successfully. 0 routing failures.** Fixed as a class-of-bug
with no provider-specific hacks and no `#` special-casing — event identifiers are now transported as
opaque, URL-safe tokens end to end.

## Root cause

1. **Why `#` exists in keys.** `event_key()` (`backend/app/storage/models.py:34`) uses `host + path`
   as the identity — but when an event URL is **host-only** (a bare landing page, no per-event path) it
   can't, so it falls back to `host#<digest>`. Devfolio URLs are `https://<slug>.devfolio.co/` (path is
   just `/`), so **every Devfolio key is `…devfolio.co#<digest>`.** (Correct behaviour — not the bug.)
2. **The bug: a double-encode from an encode/decode asymmetry.** The frontend put the raw key into the
   URL **path** via a Next.js catch-all `[...key]`:
   - `keyToPath(key)` encoded `#` → `%23` for the link href (correct).
   - `pathToKey(segments)` just `join("/")`-ed — it **never `decodeURIComponent`-ed** (its comment
     wrongly assumed the router had). So the reconstructed key kept a **literal `%23`** instead of `#`.
   - `getEvent(key)` → `keyToPath` encoded the `%` of `%23` → `%25`, producing **`%2523`**
     (double-encoded).
   - Backend `GET /platform/events/{key:path}` decoded once → `…%23…`, which ≠ the stored `…#…` → **404**.

   Measured proof: correct `%23` → HTTP 200; the buggy `%2523` → HTTP 404 `{"detail":"event not found"}`.

3. **Why only some providers.** `#` is the only character `keyToPath` encodes in real keys, and it
   appears only in **host-only-URL** keys. Affected: **Devfolio 17, Devpost 8, confs.tech 3** (28 events).
   Everything else uses path-bearing URLs (Meetup, Unstop, GDG, Hasgeek, Lu.ma, Salesforce, Atlassian,
   Snowflake, CNCF, FOSS United, Eventbrite, rendered) → no `#` → worked.

## Reserved-character analysis (all edge cases)

Putting a raw catalog key into a URL path is **fundamentally fragile** — not just for `#`:

| Char | Hazard in a raw URL path |
|---|---|
| `#` | starts a fragment (the observed bug) |
| `?` | starts a query string |
| `&` `=` | query-param separators |
| `%` | percent-encoding lead; a lone `%` **throws** in `decodeURIComponent` |
| `+` | decoded to space by some servers |
| space | must be `%20`; raw space breaks the URL |
| `:` `;` `@` `,` | reserved/sub-delims — ambiguous in segments |
| unicode | must be percent-encoded UTF-8 |
| `/` | path-separator ambiguity with the catch-all |
| double-encoding | the exact failure here |

Real keys **already** contain `#` and `%` (e.g. a Meetup key `meetup.com/%ef%b8%8f…` with an encoded
emoji), and the new `rendered` provider extracts events from **arbitrary** pages, so future keys can
contain any of the above. Any raw-key-in-path scheme is a time bomb.

## The fix — opaque base64url tokens (future-proof, no special-casing)

Every URL — the detail **route** and the API **path** — now carries an **opaque base64url token**
(`[A-Za-z0-9_-]` only). No URL-reserved character can ever appear, so it round-trips **any** key
losslessly. The raw `key` remains the internal identity (DB lookup, saved list, recommendations,
analytics); the token is derived from it on demand → **no database migration, no stored ids.**

- **Frontend route:** `/events/<token>` → decode → real key. A single opaque segment (no catch-all
  ambiguity). Legacy raw-key URLs still resolve (backwards compatible — and the fallback even repairs the
  old `#` double-encode).
- **API:** `GET /platform/events/by-id/<token>` (+ `/similar`) → decode → key → existing lookup. The
  raw-key `{key:path}` routes are kept for backwards compatibility.

The frontend `encodeEventKey` and backend `key_from_token` produce/consume **byte-identical** base64url.

## Files modified

**Frontend**
- `utils/eventKey.ts` — **replaced** `keyToPath`/`pathToKey` with `encodeEventKey` / `decodeEventKey`
  (base64url of UTF-8) / `resolveEventKey` (token, or legacy-path fallback).
- `components/EventCard.tsx`, `components/EventList.tsx` — links use `encodeEventKey`.
- `app/events/[...key]/page.tsx` — resolves via `resolveEventKey`.
- `services/platform.ts` — `eventPath` → `/platform/events/by-id/${encodeEventKey(key)}`.

**Backend**
- `app/api/routes/platform.py` — added `key_from_token` + `GET /events/by-id/{token}` and
  `…/by-id/{token}/similar` (declared **before** the `{key:path}` routes for precedence); kept the
  `{key:path}` routes for backwards compatibility.

**Tests**
- `tests/test_platform_api.py` — added `test_event_details_by_id_token` (round-trips `#`, `%`, slashes,
  every reserved char, unicode).

Untouched by design (they use the raw key in JSON/JS, never in a URL — already safe): `useLocalStorage`
(saved/favorites), the recommendations POST body, React Query deps, view-tracking.

## Migration

**None required.** Keys stay as-is in the database; tokens are computed on the fly. Old bookmarks keep
working via the legacy-path fallback in `resolveEventKey`.

## Verification (exhaustive)

**1. Verification script — every event's detail endpoint (`backend` scratchpad `verify_events.py`):**
```
Total events:        1890
Opened successfully: 1890
Failures:            0
```
Verified across all providers: devfolio 17, devpost 8, confs.tech 4, meetup 564, eventbrite 758,
unstop 299, gdg 20, luma 63, hasgeek 9, rendered 67, salesforce 30, atlassian 17, fossunited 16,
snowflake 6, cncf 1, + Meetup-ICS feeds — all 200, all `event.key` matches.

**2. Playwright real-browser sweep — 218 detail pages across 12 providers** (including all 28
previously-broken `#` events): **0 "Couldn't load", 0 404, 0 real failures.** (One "title-missing" flag
was a false positive — the DB title has a double space `FREE  AI…` that HTML collapses; that page
returns 200 and renders.)

**3. Live browser** — the exact previously-broken Devfolio event *Build with Gemma*
(`…devfolio.co#f10151254cacd266`) now fully renders (title, date, Register/Save/Share, description, AI
Understanding) with **0 console errors**.

**4. Backend suite:** 1034 passed (incl. the new token round-trip test); the lone failure is the known
pre-existing `test_scheduler` async-timing flake (passes in isolation). **Frontend `tsc --noEmit`:** clean.

**5. Codebase swept** for fragile key logic — `keyToPath`/`pathToKey` fully removed; every event URL now
flows through `encodeEventKey`/`resolveEventKey`.

## Success criteria

| Criterion | Status |
|---|---|
| Every event card opens | ✅ 1890/1890 |
| Zero "Couldn't load this" | ✅ |
| Zero 404 from event keys | ✅ |
| Works for every provider (incl. Devfolio/Devpost/confs.tech + rendered + future) | ✅ |
| No provider-specific hacks / no `#` special-case | ✅ base64url handles all keys |
| Production-grade permanent solution | ✅ opaque token, no reserved-char surface |

## Remaining risks

- **`btoa`/`atob`** are used isomorphically (Node ≥18 + browser). Present in this Next.js 15 / Node 24
  setup; if a runtime ever lacked them, swap to `Buffer`/`TextEncoder` on the server. Low risk.
- The catch-all route folder is still named `[...key]`; it accepts the single-segment token and legacy
  paths. Could be renamed `[token]` for clarity (cosmetic).
- One Playwright page logged a console error — a **benign Next.js dev-mode React StrictMode** artifact
  (`net::ERR_ABORTED` from the double-invoked effect aborting its first fetch); it occurs on working
  pages too and disappears in a production build. Not a routing error.
