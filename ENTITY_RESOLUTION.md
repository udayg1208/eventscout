# Entity Resolution

How messy raw names ("Google LLC", "Google India", "GDG Bangalore", "Google Dev Group")
collapse onto canonical entities — **deterministically, no LLM**. Code:
`backend/app/entities/resolution.py`.

## The three gates (most-precise first)

1. **Normalization** — `normalize_name`: lowercase, strip legal suffixes (LLC/Inc/Ltd/Pvt/
   Foundation/Technologies…), strip punctuation, collapse whitespace. `"Google LLC" → "google"`.

2. **Curated aliases** — a small hand-maintained table of well-known ecosystem players, checked
   two ways:
   - *exact*: normalized name is a known alias → canonical.
   - *phrase-in-name*: a known alias appears as a whole phrase inside a longer name (longest
     alias first). `"gdg bangalore" → GDG`, `"google developer group pune" → GDG`. This is what
     prevents chapter names from splitting off.
   High precision, zero false merges for the cases we enumerate.

3. **Gated fuzzy match** — rapidfuzz `token_sort_ratio` against already-seen entities **of the
   same type**, above a **conservative 0.92 threshold**. Catches spelling variants we didn't
   enumerate, without the LLM. Below threshold → a new canonical entity is registered.

Resolution is **stateful and order-deterministic**: the builder processes events sorted by
key, so the same catalog always yields the same graph.

## Verified merges

`Google LLC`, `Google India`, `Google Cloud`, `Google AI`, `Google Developers` → **one**
`organization:google`. `GDG`, `GDG Bangalore`, `Google Developer Group`, `Google Dev Group`
→ **one** `community:google-developer-groups` (with the city as a chapter, not part of the
identity).

## The core tension — false merges vs. false splits

- **False merge** (collapsing two distinct entities into one) **corrupts** the graph and is
  hard to detect after the fact — "Google" the company vs. "Google Developer Groups" the
  community are genuinely different, and over-eager rules would fuse them.
- **False split** (two nodes for one real entity) is **safe and fixable** — it just
  under-counts until an alias or a higher-recall rule is added.

**We deliberately bias toward false splits:** a high fuzzy threshold (0.92) and type-scoped
matching. The curated alias table buys precision where it matters (the known players);
everything else stays conservatively separate. Concretely, "Google Cloud" is merged into
"Google" by a *curated* alias (a deliberate decision), **not** by fuzzy matching — because
fuzzy-merging product/division names is exactly where false merges come from.

## Known limitations (brutally honest)

- **Organization recall is low** — extraction only knows a hardcoded list of orgs, so titles
  naming an unknown company yield nothing. Live: only 3 organizations from 102 events. The
  real fix is structured organizer data (Phase 5), not a bigger keyword list.
- **The curated alias table is hand-maintained** — it won't scale to thousands of orgs; it
  should become data-driven (learned from co-occurrence / provider metadata) at scale.
- **Series normalization is heuristic** — stripping year/edition/city can occasionally
  over-merge (two unrelated "Annual Summit"s) or under-merge (a renamed series). It is
  conservative, so under-merge dominates.
- **No cross-type resolution** — a person who is also a company brand, or a venue named after
  a city, aren't reconciled. Acceptable at this scale.

These are the honest costs of deterministic, no-LLM resolution over a model that lacks
structured entity fields. The architecture is right; the *inputs* get better in Phase 5.
