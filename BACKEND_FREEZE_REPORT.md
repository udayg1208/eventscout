# Backend Freeze Report

**Date:** 2026-07-14 · **Status:** ✅ FROZEN · **Scope:** M1–M6 backend, quality/consistency only (no features, no architecture changes).

## Summary
The event discovery engine is feature-complete: natural language → structured query →
two live ₹0 providers (Confs.tech conferences + Devfolio hackathons) searched in
parallel → merged, city-normalized, deduped, ranked, and cached, behind the two frozen
seams (`QueryParser`, `EventProvider`). This pass reviewed the whole backend for
production readiness and made quality-only improvements.

## Verification (all green)
| Check | Result |
|---|---|
| Regression suite | **77 passed** (network-free; `httpx.MockTransport` for fetch paths) |
| Lint (`ruff check app tests`) | All checks passed |
| Format (`ruff format --check`) | 42 files already formatted |
| Stray `print` / `TODO` / `FIXME` in `app/` | none |
| Public API surface | 4 endpoints, all typed responses |

## Changes made in this pass (quality only)
- **Tooling:** added `ruff` (config in `pyproject.toml`, line length 100, `spikes/`
  excluded); pinned in `requirements-dev.txt`.
- **Dead code removed:** `TTLCache.clear()` and `TTLCache.__len__` (never called); an
  unused `r2` binding in a test.
- **Formatting:** `ruff format` applied to all 42 files.
- **Modernization (lint-driven, behavior-preserving):** `EventCategory(str, Enum)` →
  `StrEnum`; `timezone.utc` → `datetime.UTC`; `typing.Callable` →
  `collections.abc.Callable`; removed a redundant quoted annotation.

## Review findings

**Dead code (2):** removed as above. No other unreachable code found.

**Duplication:** production code is DRY — provider filtering is shared
(`filtering.matches`), as are `dedup`, `ranking`, `city`, and `TTLCache`. The
Confs.tech/Devfolio fetch loops are *similar but not identical* (different endpoints and
record shapes); a shared base class would be an architecture change and is intentionally
avoided.

**Naming:** factories are consistent (`get_provider`, `get_query_parser`,
`get_search_service`, `get_settings`); provider constants consistent (`PROVIDER_NAME`,
`_CACHE_KEY`, `_DATA_TTL_SECONDS`). `normalize_entry` (Confs.tech) vs
`normalize_hackathon` (Devfolio) are intentionally domain-specific and kept.

**Folder organization:** clean and unchanged — `app/{api,models,parsers,providers,
services}` plus cross-cutting `cache.py`, `city.py`, `config.py`, `logging_config.py`,
`main.py`. `spikes/` and `tests/` separated.

**Public API:**
| Method | Path | Response |
|---|---|---|
| GET | `/health` | `HealthResponse` |
| POST | `/search` | `SearchResponse` (NL) |
| POST | `/events/search` | `SearchResponse` (structured) |
| GET | `/debug/metrics` | `MetricsSnapshot` (non-production only) |

**Docs:** `README.md`, `CLAUDE.md`, `ARCHITECTURE.md` synchronized to the frozen state
(flow diagram, orchestration layer, full provider set, endpoints, tooling, milestones).

## Known accepted items (documented, not defects)
1. **City-alias map duplicated** between `app/city.py` and the parser's own map — kept
   separate to avoid modifying the M3-frozen parser; two distinct responsibilities
   (text extraction vs value normalization).
2. **Devfolio API is unofficial** — mitigated structurally: a failing provider degrades
   to `[]` and the composite still returns the other source.
3. **`is_free=True` for Devfolio** — a source property (hackathons are free to enter),
   not a fabricated value; documented at the boundary.
4. **`TestClient` deprecation warning** (`httpx`/`starlette`) — test-only, harmless;
   revisit when the ecosystem settles.
5. **Post-freeze hardening (for the deploy phase, not defects):** cache size-cap/
   eviction, request-coalescing to avoid a cold-cache stampede, and per-provider
   timeouts. All low-risk at current scale.

## Freeze declaration
The backend is **frozen**. Its architecture and public interfaces
(`QueryParser`, `EventProvider`, `SearchService`, the HTTP API, and the `Event` /
`SearchQuery` models) will not change unless a **defect** is discovered. Next work is
the frontend.
