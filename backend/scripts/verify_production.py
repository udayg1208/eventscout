"""Full production verification — run AFTER the Vercel + Render deploy is live.

Usage:
    python scripts/verify_production.py <FRONTEND_URL> <BACKEND_URL>
    # e.g. python scripts/verify_production.py https://eventscout.vercel.app https://eventscout-api.onrender.com

Checks (fails loudly, no fabrication):
  1. Every feature surface (homepage, browse, search, trending, for-you, categories,
     cities, organizers, recommendations, dashboard, analytics).
  2. >=500 random event detail pages across ALL providers via base64url token — 0 failures.
  3. Production hardening: HTTPS, security headers, compression, CORS, no localhost refs.
  4. Performance: homepage / search / browse / API latency.
"""
from __future__ import annotations

import base64
import json
import random
import statistics
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import quote

if len(sys.argv) != 3:
    print(__doc__)
    sys.exit(2)
FE = sys.argv[1].rstrip("/")
BE = sys.argv[2].rstrip("/")
ORIGIN = FE

passed = failed = 0
def check(name, cond, detail=""):
    global passed, failed
    ok = bool(cond); passed += ok; failed += (not ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}{(' — ' + detail) if detail else ''}")

def req(url, method="GET", body=None, timeout=60, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Origin": ORIGIN}
    if data: h["Content-Type"] = "application/json"
    if headers: h.update(headers)
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    t0 = time.perf_counter()
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return resp.status, dict(resp.headers), resp.read(), (time.perf_counter() - t0) * 1000

def tok(k): return base64.urlsafe_b64encode(k.encode()).rstrip(b"=").decode()

print("=" * 72); print(f"PRODUCTION VERIFICATION\n  FE={FE}\n  BE={BE}"); print("=" * 72)

# ---- 1. HTTPS + reachability -------------------------------------------------
print("\n1) HTTPS + backend reachability")
check("FE is HTTPS", FE.startswith("https://"))
check("BE is HTTPS", BE.startswith("https://"))
st, hd, body, ms = req(f"{BE}/health")
h = json.loads(body); check("BE /health", st == 200 and h.get("status") == "ok", f"{h.get('environment')} {ms:.0f}ms")
st, hd, body, ms = req(f"{BE}/platform/analytics")
an = json.loads(body); total = an["total_events"]
check("catalog intact (>=1890)", total >= 1890, f"{total} events / {an['providers']} providers")

# ---- 2. Feature surfaces (backend data + frontend pages) ---------------------
print("\n2) Feature surfaces")
st, _, body, ms = req(f"{BE}/platform/homepage?limit=8"); sec = json.loads(body)["sections"]
check("homepage sections", st == 200 and len(sec) >= 10, f"{len(sec)} sections {ms:.0f}ms")
for feed in ["trending", "newest", "free", "online", "registration-closing", "popular"]:
    st, _, body, ms = req(f"{BE}/platform/discover/{feed}?limit=12")
    check(f"discover/{feed}", st == 200 and len(json.loads(body)) > 0, f"{ms:.0f}ms")
for dim, val in [("category", "hackathon"), ("category", "ai"), ("city", "Bangalore"),
                 ("topic", "Artificial Intelligence"), ("online", "true")]:
    st, _, body, ms = req(f"{BE}/platform/browse/{dim}/{quote(val)}?limit=48")
    d = json.loads(body); check(f"browse/{dim}/{val}", st == 200 and "total_count" in d,
                                f"total={d['total_count']} {ms:.0f}ms")
st, _, body, ms = req(f"{BE}/platform/search", "POST", {"query": "AI hackathon in Bangalore", "limit": 5})
check("search (Gemini NL)", st == 200, f"count={json.loads(body)['count']} {ms:.0f}ms")
st, _, body, _ = req(f"{BE}/platform/directory"); check("directory (organizers/cities)", st == 200)
# recommendations ("For You") — seed with a real key
st, _, body, _ = req(f"{BE}/platform/discover/newest?limit=1"); seed = json.loads(body)[0]["key"]
st, _, body, _ = req(f"{BE}/platform/recommendations", "POST", {"saved": [seed], "limit": 5})
check("recommendations (For You)", st == 200 and len(json.loads(body)) > 0)

# frontend page shells
for p in ["/", "/hackathons", "/conferences", "/meetups", "/workshops", "/trending",
          "/recommendations", "/saved", "/dashboard", "/browse", "/categories",
          "/cities", "/organizers", "/search?q=ai", "/ai-events"]:
    try:
        st, _, _, ms = req(f"{FE}{p}"); check(f"FE {p}", st == 200, f"{ms:.0f}ms")
    except Exception as e:
        check(f"FE {p}", False, str(e))

# ---- 3. >=500 random event detail pages across providers --------------------
print("\n3) Event-detail routing sweep (>=500 across all providers)")
keys, by_prov = {}, {}
for dim in ["category/ai", "category/hackathon", "category/conference", "category/meetup",
            "category/workshop", "city/Bangalore", "city/Mumbai", "city/Delhi", "online/true"]:
    off = 0
    while True:
        st, _, body, _ = req(f"{BE}/platform/browse/{dim}?offset={off}&limit=200")
        d = json.loads(body)
        for e in d["events"]:
            keys[e["key"]] = e.get("provider", "?")
        if not d["has_more"] or off > 2000:
            break
        off += 200
allk = list(keys.items()); random.seed(7); random.shuffle(allk)
sample = allk[:max(500, min(len(allk), 500))]
det_ok = det_fail = 0; fails = []
for k, prov in sample:
    try:
        st, _, body, _ = req(f"{BE}/platform/events/by-id/{tok(k)}")
        d = json.loads(body)
        if st == 200 and d["event"]["key"] == k:
            det_ok += 1; by_prov[prov] = by_prov.get(prov, 0) + 1
        else:
            det_fail += 1; fails.append((k, st))
    except Exception as e:
        det_fail += 1; fails.append((k, str(e)[:40]))
check(f"{len(sample)} event details open (0 failures required)", det_fail == 0,
      f"{det_ok} ok, {det_fail} failed")
print(f"    providers covered: {json.dumps(by_prov, sort_keys=True)}")
if fails:
    print("    FAILURES:", fails[:10])

# ---- 4. Production hardening -------------------------------------------------
print("\n4) Production hardening")
st, hd, body, _ = req(f"{FE}/")
hl = {k.lower(): v for k, v in hd.items()}
for hdr in ["x-frame-options", "x-content-type-options", "referrer-policy",
            "strict-transport-security"]:
    check(f"header {hdr}", hdr in hl, hl.get(hdr, "MISSING"))
# compression
st, hd, body, _ = req(f"{FE}/", headers={"Accept-Encoding": "gzip, br"})
enc = {k.lower(): v for k, v in hd.items()}.get("content-encoding", "")
check("compression (gzip/br)", enc in ("gzip", "br"), enc or "none")
# CORS from FE origin
st, hd, body, _ = req(f"{BE}/platform/homepage?limit=2")
acao = {k.lower(): v for k, v in hd.items()}.get("access-control-allow-origin", "")
check("CORS allows FE origin", acao in (FE, "*"), acao or "MISSING")
# no localhost in served JS bundle
html = req(f"{FE}/")[2].decode("utf-8", "ignore")
import re
m = re.search(r"/_next/static/chunks/[0-9]+-[a-f0-9]+\.js", html)
chunk_has_localhost = False
if m:
    js = req(f"{FE}{m.group(0)}")[2].decode("utf-8", "ignore")
    chunk_has_localhost = ("127.0.0.1:8000" in js or "localhost:8000" in js) and BE not in js
check("client bundle calls prod BE (no stray localhost)", (BE.replace("https://", "") in html or (m and BE.replace("https://","") in js)) and not chunk_has_localhost, BE)

# ---- 5. Performance ----------------------------------------------------------
print("\n5) Performance (median of 6)")
def bench(name, fn, n=6):
    xs = sorted(fn() for _ in range(n))
    print(f"  {name:26s} p50={statistics.median(xs):7.1f}ms  min={xs[0]:7.1f}ms")
bench("API /health", lambda: req(f"{BE}/health")[3])
bench("API homepage", lambda: req(f"{BE}/platform/homepage?limit=8")[3])
bench("API browse", lambda: req(f"{BE}/platform/browse/category/ai?limit=48")[3])
bench("API search", lambda: req(f"{BE}/platform/search", "POST", {"query": "ai", "limit": 10})[3])
bench("FE homepage (HTML)", lambda: req(f"{FE}/")[3])

print("\n" + "=" * 72)
print(f"RESULT: {passed} passed, {failed} failed | event-detail sweep: {det_ok}/{len(sample)}")
print("=" * 72)
sys.exit(1 if failed else 0)
