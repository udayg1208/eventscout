# Deployment Guide

Deploy the **backend to Render** and the **frontend to Vercel**, both on free tiers.
The app is a stable public API (backend frozen); this guide changes no code.

```
Browser ──▶ Vercel (Next.js frontend) ──POST /search──▶ Render (FastAPI backend)
                                                          └─ Gemini + Confs.tech + Devfolio
```

## Prerequisites
- A **GitHub** account and this repo pushed to it (Step 0).
- A **Render** account (render.com) and a **Vercel** account (vercel.com) — both free, sign in with GitHub.
- A **Gemini API key** (aistudio.google.com, free). Use model `gemini-flash-lite-latest`.

> I (the assistant) cannot create these accounts, enter your API key into their
> dashboards, or click Deploy for you — those are yours to do. Every step below is
> spelled out so it takes ~15 minutes.

---

## Step 0 — Push to GitHub
The repo is already initialized and committed locally (branch `main`, secrets excluded).

```bash
cd C:/Users/HP/Desktop/EVENT
git remote add origin https://github.com/<you>/event-discovery.git
git push -u origin main
```
Create the empty GitHub repo first (github.com → New repository, no README).

---

## Step 1 — Backend on Render

**Option A — Blueprint (recommended).** The repo has `render.yaml`.
1. Render Dashboard → **New → Blueprint** → connect this repo → **Apply**.
2. Render reads `render.yaml` and creates the `event-discovery-api` web service
   (Python, root `backend/`, start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`,
   health check `/health`).
3. When prompted, set the two `sync:false` env vars:
   - `GEMINI_API_KEY` = your key
   - `CORS_ORIGINS` = leave as a placeholder for now (e.g. `http://localhost:3000`);
     you'll set the real Vercel URL in Step 3.

**Option B — Manual.** New → Web Service → this repo →
Root Directory `backend`, Build `pip install -r requirements.txt`,
Start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, Health Check Path `/health`.
Add env vars: `PYTHON_VERSION=3.11.9`, `ENVIRONMENT=production`,
`GEMINI_MODEL=gemini-flash-lite-latest`, `GEMINI_API_KEY=<key>`, `CORS_ORIGINS=<set in Step 3>`.

Wait for the first deploy, then note the URL, e.g. `https://event-discovery-api.onrender.com`.
Verify: open `<backend-url>/health` → `{"status":"ok",...,"environment":"production"}`.

---

## Step 2 — Frontend on Vercel
1. Vercel → **Add New → Project** → import this repo.
2. **Root Directory = `frontend`** (important — the repo is a monorepo). Framework
   auto-detects as Next.js; leave build/output defaults.
3. Add an environment variable:
   - `NEXT_PUBLIC_API_BASE_URL` = your Render backend URL (no trailing slash),
     e.g. `https://event-discovery-api.onrender.com`
4. **Deploy.** Note the URL, e.g. `https://event-discovery.vercel.app`.

---

## Step 3 — Wire CORS (connect the two)
1. In Render → the API service → **Environment** → set
   `CORS_ORIGINS = https://event-discovery.vercel.app` (your exact Vercel URL, no
   trailing slash; comma-separate multiple origins).
2. Save → Render redeploys automatically.

The backend already reads `CORS_ORIGINS` from the environment (comma-separated). No
code change needed.

---

## Step 4 — Verify in production
Replace `$BE` and `$FE` with your real URLs.

```bash
BE=https://event-discovery-api.onrender.com
FE=https://event-discovery.vercel.app

# Health
curl -s $BE/health                                   # environment: production

# Gemini + both providers (natural language)
curl -s -X POST $BE/search -H 'Content-Type: application/json' \
  -d '{"query":"hackathons in Bangalore"}'           # count > 0, provider devfolio/confs.tech

# Provider: Confs.tech (conferences)
curl -s -X POST $BE/events/search -H 'Content-Type: application/json' \
  -d '{"categories":["conference"]}'                 # provider confs.tech

# Provider: Devfolio (hackathons)
curl -s -X POST $BE/events/search -H 'Content-Type: application/json' \
  -d '{"categories":["hackathon"]}'                  # provider devfolio

# Cache: run the same /search twice — second response has "cached": true

# CORS: from the browser on $FE, run a search — it must succeed (no CORS error in console)
```
Then open `$FE`, run a few searches, toggle dark mode, and check the browser console
is clean.

---

## Operational notes
- **Render free tier sleeps** after ~15 min idle; the first request then cold-starts
  (~50s). The in-memory cache resets on any restart/redeploy — expected and harmless.
- **Metrics (`/debug/metrics`) are disabled in production by design** (registered only
  when `ENVIRONMENT != production`). To inspect them, either run locally
  (`ENVIRONMENT` unset) or temporarily set `ENVIRONMENT=staging` on Render. They were
  verified locally in M4. See the checklist.
- **Gemini free tier** is rate-limited (~15 req/min). If exceeded, the backend
  automatically falls back to the deterministic parser — search still works.
- **Devfolio** uses an unofficial public endpoint; if it changes, that provider
  degrades to empty and Confs.tech still returns results.
- **Secrets** live only in the Render/Vercel dashboards and local `.env` files — never
  in git (verified: `git ls-files` shows no `.env`).

## Rollback
- Render: Service → **Events/Deploys** → roll back to a previous deploy.
- Vercel: Project → **Deployments** → promote a previous deployment.
