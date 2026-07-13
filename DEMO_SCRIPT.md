# Demo Script — AI Event Discovery Agent (~4 min)

A ready-to-record storyboard. Record with OBS / Loom / QuickTime at 1280×720+.
Prep: backend + frontend running (prod URLs, or local `:3000` + `:8000`); do one
warm-up search first so Render isn't cold and provider data is cached. Have the
browser in light mode to start.

**Total ≈ 4:00.** Timings are cumulative.

---

### Scene 1 — Hook & what it is · 0:00–0:30
- **Screen:** the app's idle home page (header, search bar, example chips).
- **Do:** slowly move the cursor across the example chips.
- **Say:** "This is an AI-powered event discovery app for India — not a chatbot, a
  search engine. You describe what you want in plain English, and it finds real
  professional and tech events from live public sources. It's built on a FastAPI
  backend and a Next.js frontend, running entirely on free tiers."

### Scene 2 — Natural-language search · 0:30–1:15
- **Do:** type `AI hackathons in Bangalore` and press Enter. Let the skeletons show.
- **Say:** "When I search, the backend sends the text to Google Gemini — but only to
  *understand* it, never to invent events. Watch the 'Understood as' row."
- **Screen:** results appear. Point to the **Understood as** chips (📍 Bangalore,
  Hackathon).
- **Say:** "Gemini turned my sentence into a structured query — city Bangalore,
  category hackathon. The backend then searched real sources and ranked the results."

### Scene 3 — The results & the cards · 1:15–2:00
- **Do:** hover a couple of cards; point to the badges.
- **Say:** "Each card is a real event. The colored chip is the category. This badge
  shows the **source** — Devfolio for hackathons, Confs.tech for conferences — so the
  data is transparent. Here's the date, the city, whether it's free, and a Register
  button that opens the real event page."
- **Do:** click **Load more** to reveal the rest.
- **Say:** "Results are ranked by relevance, how soon they are, and how complete the
  listing is."

### Scene 4 — Multiple sources + normalization · 2:00–2:40
- **Do:** new search: `tech conferences in India`.
- **Say:** "Now conferences — these come from a different source, Confs.tech. The app
  merges both providers, removes duplicates, and normalizes messy data. For example,
  'Bengaluru' and 'Bangalore' are unified automatically, so a Bangalore search finds
  them all."
- **Screen:** point to a card whose city reads **Bangalore** (originally Bengaluru).

### Scene 5 — Filters, free events, dark mode · 2:40–3:15
- **Do:** search `free machine learning webinars` (shows the free-only intent), then
  toggle **dark mode** with the header button.
- **Say:** "It understands budget and format too — 'free' filters to free events. And
  the whole UI is responsive, accessible, and supports dark mode."

### Scene 6 — Resilience · 3:15–3:40
- **Do:** search something out-of-scope like `cooking classes in Mumbai` → empty state.
- **Say:** "It never fabricates events — if there's nothing, it says so, clearly. And
  if a source or the AI is unavailable, the app degrades gracefully instead of
  breaking."

### Scene 7 — Close · 3:40–4:00
- **Screen:** back to results, or a quick flash of the architecture diagram from
  ARCHITECTURE.md.
- **Say:** "Natural language in, real ranked events out — from two live sources, at
  zero cost, deployed on Render and Vercel. Thanks for watching."

---

## Optional 30–45s technical addendum (for a dev audience)
- Show `POST /search` in the browser Network tab → the JSON response (`query`, `count`,
  `events`, `cached`).
- Mention: two architectural seams (`QueryParser`, `EventProvider`), a composite
  multi-provider engine, two-tier TTL caching, 77 backend tests, frozen public API.

## Recording tips
- Do a warm-up search before recording (avoids the Render cold-start pause on camera).
- If Gemini is rate-limited mid-demo, the fallback still returns results — fine to show.
- Keep each search to one clean take; pause ~1s after results load before narrating.
