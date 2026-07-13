# AI-Powered Event Discovery Agent for India

Discover professional & tech events across India using natural language.

> "Find AI workshops in Bangalore this weekend" → structured search → real events.

This is an **AI-powered search application**, not a chatbot. Gemini is used only to
understand the query; it never searches the web and never invents events.

## Architecture

```
User → Next.js frontend → FastAPI backend → Gemini (query understanding)
     → structured SearchQuery → Event provider → normalized Events → cache → response
```

## Tech stack

| Layer     | Choice                         |
|-----------|--------------------------------|
| Frontend  | Next.js + Tailwind CSS         |
| Backend   | FastAPI (Python)               |
| AI        | Google Gemini (Flash-Lite)     |
| Storage   | In-memory cache (no DB yet)    |
| Deploy    | Vercel (FE) + Render (BE)      |

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the design and [`CLAUDE.md`](CLAUDE.md)
for engineering conventions.

## Project structure

```
EVENT/
├── backend/      FastAPI service (models, providers, parsers, tests, spikes)
└── frontend/     Next.js app (added in a later milestone)
```

## Status

**Backend frozen — feature complete** (M1–M6, 77 tests, lint clean). Natural language →
structured query → two live ₹0 providers (Confs.tech conferences + Devfolio hackathons)
searched in parallel → merged, city-normalized, deduped, ranked, and cached. Next
milestone: the frontend (Next.js + Tailwind).

### API

| Method | Path             | Purpose                                            |
|--------|------------------|----------------------------------------------------|
| GET    | `/health`        | Liveness / identity                                |
| POST   | `/search`        | Natural-language search → ranked events            |
| POST   | `/events/search` | Structured `SearchQuery` search (no AI)            |
| GET    | `/debug/metrics` | Pipeline metrics (non-production only)             |

## Running the backend (local)

```bash
cd backend
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt      # runtime + test deps
cp .env.example .env                      # then add your Gemini key (optional)
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/health — you should see a healthy JSON response.
Run the tests with `pytest -q` from `backend/`.

### Gemini configuration

Query understanding uses Google Gemini (free tier, no credit card). Put your key in
`backend/.env`:

```
GEMINI_API_KEY="AIza..."
GEMINI_MODEL="gemini-flash-lite-latest"   # rolling Flash-Lite alias (see note below)
```

Without a key the app runs fully on a deterministic keyword parser. If Gemini is
unavailable or rate-limited, it automatically falls back to that parser — the app
never fails on a query.

> **Model note:** use the `gemini-flash-lite-latest` alias. Some pinned dated IDs
> (e.g. `gemini-2.0-flash-lite`) can carry zero free-tier quota on a given project;
> the alias is served. See `ARCHITECTURE.md` → *Lessons learned*.
