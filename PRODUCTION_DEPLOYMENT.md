# EventScout — Production Deployment

Authoritative deployment guide for the current catalog: **1,890 events across 19
providers** (supersedes the headline numbers in `DEPLOYMENT.md` / `PRODUCTION_CHECKLIST.md`,
which predate Phases 11A–11E). Deployment only — no feature, UI, or business-logic changes.

---

## 0. TL;DR — two ways to be public

| Option | URL lifetime | Needs your accounts? | Best for |
|---|---|---|---|
| **A. Cloudflare quick tunnel** (live now) | While this PC + tunnel run | No | Show the manager **today** |
| **B. Vercel + Render** (durable) | Permanent | Yes (GitHub + Vercel + Render) | The real hosted URL |

**Option A is running right now** — see §1. **Option B is a ~15-minute checklist you run**
because it requires signing into *your* accounts (§3). I cannot create accounts or click
Deploy on your behalf.

---

## 1. Option A — live demo URL (Cloudflare tunnel, no signup)

Two Cloudflare quick tunnels expose the locally-running prod build. Anyone on any laptop
can open the frontend URL; its browser calls the backend tunnel (CORS pinned to it).

```
Frontend (open this):  https://lucas-ship-gets-alabama.trycloudflare.com
Backend  API:          https://penalty-kirk-internet-ruling.trycloudflare.com
```

**Caveats (honest):** the URL dies when this PC sleeps / the tunnel stops, and it changes
on every relaunch. The backend uses your Gemini key, so anyone with the URL can spend
Gemini quota (random URL = unguessable, fine for a short demo). This is a **demo bridge,
not hosting** — for a permanent URL, do Option B.

### Re-create the tunnel demo (if it drops)
```bash
# 1. Backend (from backend/, venv active) — CORS must include the frontend tunnel origin
CORS_ORIGINS="<frontend-tunnel-url>,http://localhost:3000" \
  ./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 2. Two tunnels (each prints its https://<name>.trycloudflare.com URL)
cloudflared tunnel --url http://localhost:8000    # backend  -> note URL as $BE
cloudflared tunnel --url http://localhost:3000    # frontend -> give this to the manager

# 3. Frontend built with the PUBLIC backend URL baked in (NEXT_PUBLIC_* is build-time)
cd frontend && NEXT_PUBLIC_API_BASE_URL="$BE" npx next build && npx next start -p 3000
```

---

## 2. Architecture

```
                 Durable (Option B)                         Demo (Option A)
   ┌────────────────────────────────────────┐     ┌──────────────────────────────┐
   │  Manager's browser (any laptop)         │     │  Manager's browser           │
   └───────────────┬────────────────────────┘     └──────────────┬───────────────┘
                   │ HTTPS                                        │ HTTPS
        ┌──────────▼───────────┐                     ┌────────────▼─────────────┐
        │  Vercel (CDN + SSR)  │  Next.js 15         │ Cloudflare edge (Mumbai) │
        │  static + edge cache │  App Router         │  quick tunnel x2         │
        └──────────┬───────────┘                     └────────────┬─────────────┘
                   │ fetch NEXT_PUBLIC_API_BASE_URL                │ tunnels to localhost
        ┌──────────▼───────────┐                     ┌────────────▼─────────────┐
        │  Render (web svc)    │  FastAPI            │  this PC: uvicorn :8000   │
        │  single uvicorn proc │  + Uvicorn          │           next start :3000│
        │  reads catalog.db    │  (in-mem caches)    └───────────────────────────┘
        └──────────┬───────────┘
                   │ read-only
        ┌──────────▼───────────┐
        │  SQLite catalog.db   │  1,890 events, committed in repo (1.6 MB)
        │  (bundled, read-only)│  + provider_state.db
        └──────────────────────┘

  Gemini API (free tier) ← backend calls it for natural-language search;
                            falls back to a deterministic parser on rate-limit/no-key.
  No websockets. REST only. Ingestion runs offline (not at request time).
```

**Why single-process backend:** the app holds the catalog, entity graph, enrichment, and
metrics **in memory**, built once at boot. Multiple workers would each hold a divergent
copy and split the cache — so `render.yaml` pins one uvicorn process (vertical scale only).

---

## 3. Option B — durable deploy (Vercel + Render), the ~15-minute runbook

Prereqs you provide: a GitHub account, a Vercel account, a Render account, your Gemini API
key (free at aistudio.google.com — no card).

**Step 1 — push to GitHub** (the code + `catalog.db` are local and uncommitted today)
```bash
cd C:/Users/HP/Desktop/EVENT
git add -A                        # catalog.db is NOT gitignored → it ships (intended)
git commit -m "Deploy: EventScout 1890-event catalog"
git remote add origin https://github.com/<you>/eventscout.git
git push -u origin main
```
Confirm no secrets shipped: `git ls-files | grep -E '\.env$|\.env\.local$'` → **empty**.

**Step 2 — backend on Render** (blueprint already in repo: `render.yaml`)
1. Render → New → **Blueprint** → pick the repo. It reads `render.yaml` (rootDir `backend`,
   build `pip install -r requirements.txt`, start `uvicorn app.main:app --host 0.0.0.0
   --port $PORT`, health `/health`, free plan, single process).
2. Set the two secret env vars in the dashboard: `GEMINI_API_KEY` = your key, and
   `CORS_ORIGINS` = your Vercel URL (fill after Step 3, comma-separated, no trailing slash).
3. Deploy → note the URL, e.g. `https://eventscout-api.onrender.com`. Check `/health`
   returns `environment: production`.

**Step 3 — frontend on Vercel**
1. Vercel → New Project → import the repo → **Root Directory = `frontend`** (auto-detects
   Next.js; leave build/output defaults).
2. Env var: `NEXT_PUBLIC_API_BASE_URL` = the Render URL from Step 2 (no trailing slash).
3. Deploy → note the URL, e.g. `https://eventscout.vercel.app`.

**Step 4 — wire CORS**: back in Render, set `CORS_ORIGINS` to the exact Vercel URL → it
redeploys. Done. (Security headers ship automatically via `frontend/next.config.mjs`; HTTPS,
gzip/brotli, and CDN caching are automatic on both platforms.)

---

## 4. Production checklist

**Pre-deploy**
- [x] Frontend `next build` clean (verified, exit 0)
- [x] Backend boots; `/health` OK; serves 1,890 events / 19 providers
- [x] No `next/image`/remote-image config needed (card UI, no external images)
- [x] `NEXT_PUBLIC_API_BASE_URL` is env-driven (localhost only as dev fallback)
- [x] `catalog.db` + `provider_state.db` NOT gitignored → they deploy
- [x] Security headers configured (`next.config.mjs`: HSTS, X-Frame-Options, nosniff, …)
- [ ] `git ls-files | grep -E '\.env'` empty (run at push time)
- [ ] Repo pushed to GitHub

**Backend (Render)** — [ ] Blueprint deploy · [ ] `GEMINI_API_KEY` + `CORS_ORIGINS` set ·
[ ] `/health` → `production` · [ ] single uvicorn process

**Frontend (Vercel)** — [ ] Root Directory `frontend` · [ ] `NEXT_PUBLIC_API_BASE_URL` set ·
[ ] site loads

**Post-deploy verify** (the automated `verify_deploy.py` already passed 31/31 on the tunnel):
- [ ] Homepage sections load · [ ] search returns events · [ ] browse pagination walks full
  set · [ ] 25 random event details open via token · [ ] every category/city/dashboard route
  200 · [ ] no CORS error in the browser console

---

## 5. Admin / maintenance commands

```bash
# --- health & size ---
curl -s $API/health
curl -s $API/platform/analytics | python -m json.tool     # total_events, providers, topics

# --- rebuild/refresh the catalog (offline, then redeploy) ---
cd backend && ./.venv/Scripts/python.exe -m app.cli ingest   # runs due providers → catalog.db
#   browser-rendered providers need system Chrome + playwright; skip on the server.
git add backend/catalog.db && git commit -m "refresh catalog" && git push   # Render redeploys

# --- run the test suite / linter ---
cd backend && ./.venv/Scripts/python.exe -m pytest -q        # ~1034 tests
cd backend && ./.venv/Scripts/python.exe -m ruff check app tests

# --- local production-mode boot (what Render runs) ---
cd backend && ENVIRONMENT=production ./.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000

# --- rollback ---  Render: Deploys → Rollback.   Vercel: Deployments → Promote previous.
```

---

## 6. Measured performance (this run)

Raw app latency, local warm process (representative of Render once warm):

| Endpoint | p50 | notes |
|---|---|---|
| `GET /health` | ~4 ms | |
| `GET /platform/homepage` | ~77 ms | builds 15 sections |
| `GET /platform/browse/{dim}` | ~14 ms | in-memory index |
| `POST /platform/search` (Gemini) | ~930 ms | LLM call; cached repeats faster; parser fallback ~ms |

Through the Cloudflare demo tunnel add ~0.4–1.1 s (edge double-hop) — a demo artifact, not
the Vercel/Render number.

---

## 7. Known limitations

1. **Demo tunnel is ephemeral** — dies with this PC/tunnel; URL changes each launch. Durable
   URL = Option B.
2. **Render free tier sleeps** after ~15 min idle → first request cold-starts (~50 s) and
   in-memory caches reset. Harmless; time the demo accordingly (or a paid instance stays warm).
3. **Catalog is a point-in-time snapshot** (`catalog.db` in the repo). It refreshes only when
   you re-run ingestion and redeploy — the server does not ingest at request time.
4. **Browser-rendered providers** (Commudle/10times/Townscript, 67 events) need system Chrome
   + Playwright and only run during *offline* ingestion, not on Render. Their events are
   already baked into the shipped `catalog.db`.
5. **Gemini free tier** is ~15 req/min; on overflow, search falls back to the deterministic
   parser (still works, less nuanced).
6. **SQLite is read-only in production** — correct for a read-heavy catalog; there are no
   per-user writes server-side (saved/bookmarks live in the browser's localStorage).
