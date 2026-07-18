# Production Checklist

> **⚠️ Superseded — see [`PRODUCTION_DEPLOYMENT.md`](PRODUCTION_DEPLOYMENT.md)** for the
> current checklist (1,890 events / 19 providers / ~1034 tests). Kept for reference.

Work top to bottom. See `DEPLOYMENT.md` for the how-to.

## Pre-deploy
- [ ] `pytest -q` green (77 tests) and `ruff check app tests` clean in `backend/`
- [ ] `npm run build` clean in `frontend/`
- [ ] `git ls-files | grep -E '\.env$|\.env\.local$'` returns **nothing** (no secrets tracked)
- [ ] Gemini API key ready (model `gemini-flash-lite-latest`)
- [ ] Repo pushed to GitHub (`git push -u origin main`)

## Backend (Render)
- [ ] Service created from `render.yaml` (root `backend/`)
- [ ] Env vars set: `ENVIRONMENT=production`, `PYTHON_VERSION=3.11.9`,
      `GEMINI_MODEL=gemini-flash-lite-latest`, `GEMINI_API_KEY`, `CORS_ORIGINS`
- [ ] First deploy succeeded; `/health` returns `environment: production`
- [ ] Start command is single-process uvicorn (no extra workers — cache coherence)

## Frontend (Vercel)
- [ ] Project imported with **Root Directory = `frontend`**
- [ ] `NEXT_PUBLIC_API_BASE_URL` = Render backend URL (no trailing slash)
- [ ] Deploy succeeded; site loads

## Wire-up
- [ ] Render `CORS_ORIGINS` set to the exact Vercel URL; backend redeployed
- [ ] A search from the deployed frontend succeeds (no CORS error in console)

## Production verification (Step 4)
- [ ] `GET /health` → 200, `environment: production`
- [ ] `POST /search` (natural language) → `count > 0`  → **Gemini verified**
- [ ] `POST /events/search {categories:["conference"]}` → **Confs.tech verified**
- [ ] `POST /events/search {categories:["hackathon"]}` → **Devfolio verified**
- [ ] Same `/search` twice → 2nd has `cached: true`  → **caching verified**
- [ ] `GET /debug/metrics` → 404 in prod (expected). Metrics verified locally / on a
      non-prod instance.
- [ ] Frontend: search, empty state, dark mode, "Load more", Register links all work

## Post-deploy hygiene
- [ ] Note the cold-start behavior (Render free tier) for demo timing
- [ ] Confirm no secrets in logs
- [ ] Save the two URLs (backend, frontend) somewhere handy

## Local production-mode verification (already done — evidence)
- [x] `ENVIRONMENT=production uvicorn app.main:app --host 0.0.0.0 --port $PORT` boots
- [x] `/health` → `environment: production`
- [x] `/search` → Gemini + providers; repeat → `cached: true`
- [x] Confs.tech (11 conferences) + Devfolio (14 hackathons) both return
- [x] `/debug/metrics` → 404 in production (gating confirmed)
