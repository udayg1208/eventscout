# CLAUDE.md — Engineering guide for the Event Discovery Agent

Guidance for working in this repo. Read `ARCHITECTURE.md` for the design.

## What this is
An AI-powered **search** app (not a chatbot) that finds professional/tech events in
India from natural-language queries. ₹0 budget: no paid APIs, no credit card.

## Golden rules
1. **Depend on the two seams, never on an implementation.**
   - `EventProvider` (event sources) — consumers use `get_provider()`.
   - `QueryParser` (NL → `SearchQuery`) — consumers use `get_query_parser()`.
   Nothing outside these factories may import a concrete provider/parser or the
   Gemini SDK.
2. **Normalize at the boundary.** Provider/model quirks (field names, missing data,
   `Bengaluru`→`Bangalore`) are resolved inside `search()` / `parse()` before an
   `Event` / `SearchQuery` leaves it. Missing data → honest `None`, never a
   fabricated default.
3. **Never fabricate events.** Gemini only does query understanding; it never
   searches the web or invents events. No results → empty result.
4. **Parsers never crash on user input.** Gemini path degrades: validate → retry
   once → deterministic fallback.
5. **Secrets only in `backend/.env`** (git-ignored). Never hardcode.
6. **Work incrementally, milestone by milestone.** Small files, separated concerns,
   type hints, Pydantic, no abstractions before they're needed.

## Layout
```
backend/
  app/
    config.py            Settings (pydantic-settings, env-only)
    main.py              FastAPI app factory
    cache.py             TTLCache (generic, injectable clock)
    city.py              normalize_city (canonical Indian city names)
    logging_config.py    setup_logging
    api/routes/          health.py, search.py, events.py, debug.py
    models/              event.py (Event, EventCategory), search.py (SearchQuery)
    parsers/             base.py (QueryParser), keyword.py, gemini.py, prompts.py,
                         __init__ (get_query_parser)
    providers/           base.py (EventProvider), composite.py, confstech.py,
                         devfolio.py, mock.py, filtering.py, dedup.py, ranking.py,
                         __init__ (get_provider)
    services/            search_service.py (SearchService, get_search_service)
  spikes/                throwaway validation scripts — NOT wired into prod
  tests/                 pytest (network-free; httpx.MockTransport for fetch paths)
  pyproject.toml         ruff config      pytest.ini   requirements*.txt
frontend/                Next.js (next milestone)
```

## Commands (run from `backend/`)
```bash
./.venv/Scripts/python.exe -m pytest -q                        # tests
./.venv/Scripts/python.exe -m ruff check app tests             # lint
./.venv/Scripts/python.exe -m ruff format app tests            # format
./.venv/Scripts/python.exe -m uvicorn app.main:app --reload    # run API
```
Windows/PowerShell: prefix a UTF-8 console with `PYTHONIOENCODING=utf-8` when a
script prints `₹` or other non-ASCII.

## Gemini gotcha (learned the hard way — see ARCHITECTURE.md “Lessons”)
Use the rolling alias **`GEMINI_MODEL="gemini-flash-lite-latest"`**. The pinned
dated IDs (`gemini-2.0-flash-lite`, `gemini-2.0-flash`) returned `free_tier limit: 0`
on the current project; the alias is served. If Gemini 429s, the app still works via
the deterministic parser — check the logs for `using deterministic fallback`.

## Status
**Backend FROZEN** (M1–M6 complete, 77 tests, lint clean). The event discovery engine
is done: NL → structured query → two live ₹0 providers (Confs.tech conferences +
Devfolio hackathons) searched in parallel → merged, city-normalized, deduped, ranked,
cached. Do not change backend architecture unless a defect is found. Next milestone:
frontend (Next.js + Tailwind) consuming `POST /search`. See the Backend Freeze Report.
