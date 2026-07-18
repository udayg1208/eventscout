# Frontend Architecture (Phase 6B)

The **EventScout Web Platform** — a Next.js 15 (App Router) + React 19 + TypeScript + Tailwind
frontend that consumes the Phase-6A Platform Service over HTTP. It exposes every backend
capability (search, browse, discovery, homepage, event details, entity profiles,
recommendations, analytics) as a fast, responsive, accessible SaaS UI. It contains **no
business logic** — every piece of data comes from the backend; the client only fetches,
composes, and renders.

Code: `frontend/`. Backend read surface: `backend/app/api/routes/platform.py` (additive
HTTP exposure of `PlatformService` — the only backend change 6B required; no logic or frozen
contract touched).

## How the frontend talks to the backend

A web page can't import a Python service, so Phase 6A's `PlatformService` is exposed over
HTTP by a thin, additive router (`/platform/*`). Every endpoint resolves a **cached
singleton** built once from the catalog and returns the frozen DTOs verbatim as JSON.

```
Browser (React)
   │  fetch (services/)         NEXT_PUBLIC_API_BASE_URL = http://127.0.0.1:8000
   ▼
/platform/homepage · /discover/{feed} · /browse/{dim}/{value} · /events/{key}
/entities/{kind}/{name} · /analytics · /directory · /search · /recommendations
   ▼
PlatformService (6A facade)  →  Search 4B · Intelligence 4D · User 5B · AI 5A · Graph 3F · Repository
```

CORS on the backend already allows `localhost:3000`, so the browser calls the API origin
directly (no proxy).

## Folder structure

```
frontend/
  app/            Next.js App Router routes (thin — delegate to views/)
  views/          page-level components (the "pages" of the app; named views/ because
                  Next.js reserves the top-level pages/ dir for the legacy Pages Router)
  layouts/        AppShell (nav + main + footer), used by the root layout
  components/     reusable UI — cards, grids, sections, search, filters, badges…
    ui/           primitives — Button, Card, Badge, Skeleton, States, icons
  hooks/          data hooks (useAsync, usePlatform*, usePlatformSearch) + local state
                  (useLocalStorage → saved / recently-viewed / preferences, useSearchHistory, useTheme)
  services/       HTTP client — api.ts (fetch wrapper) + platform.ts (one fn per endpoint)
  types/          platform.ts — TS mirror of the backend DTOs (snake_case)
  utils/          cn, format, categories, feeds, eventKey — pure helpers + registries
```

> **Note on `pages/` → `views/`:** the requested structure named this folder `pages/`, but in
> an App Router project a top-level `pages/` directory is claimed by Next's legacy Pages
> Router (it tries to treat each file as a route and the build fails). Page-level components
> therefore live in `views/`; routing stays in `app/`.

## Routing

App Router. Each `app/**/page.tsx` is a thin wrapper that renders a view; dynamic routes read
their (async) params/searchParams on the server and pass plain props to the client view.

| Route | View | Notes |
|---|---|---|
| `/` | LandingPage | hero search + stats + trending |
| `/home` | HomeDashboard | 16 homepage sections (carousels) |
| `/search` | SearchPage | NL search (reads `?q=`) |
| `/browse`, `/browse/[dimension]/[value]` | BrowseHub / BrowseResults | topic/tech/city/difficulty/audience/community/organizer |
| `/categories`, `/categories/[category]` | CategoriesPage / FeedPage | |
| `/trending` `/new` `/closing-soon` `/ai-events` `/hackathons` `/conferences` `/meetups` `/workshops` `/startup-events` `/developer-festivals` `/university-events` `/government-tech` `/online` `/free` | **FeedPage** | 14 routes, **one template**, driven by the `FEEDS` registry (utils/feeds.ts) |
| `/communities` `/organizers` `/cities` (+ `/[name]`) | EntityIndexPage / EntityDetailPage | from `/directory` + entity profiles |
| `/events/[...key]` | EventDetailPage | catch-all: event keys contain `/` (and `#`) → encoded per segment |
| `/recommendations` | RecommendationsPage | explained recs from saved/viewed |
| `/dashboard` `/saved` `/history` `/preferences` | Dashboard / Saved / History / Preferences | localStorage-backed |

The 14 feed routes are the key reuse: each is ~6 lines; all behaviour lives in `FeedPage` +
the feed registry, which declares whether a feed's data comes from a discovery endpoint, a
category browse, or a homepage section.

## Component hierarchy

```
RootLayout (app/layout.tsx, theme no-FOUC script)
└─ AppShell (layouts/)
   ├─ Navbar         active links, saved-count badge, ThemeToggle, mobile menu
   ├─ main → <view>
   │   ├─ PageHeader / Breadcrumbs
   │   ├─ Section (carousel)      ─┐
   │   ├─ EventGrid / LoadMoreGrid │ all render →  EventCard  ─┬─ CategoryBadge / FormatBadge / PriceBadge
   │   ├─ Filters (+ applyFilters) │                           ├─ SaveButton (localStorage)
   │   ├─ RecommendationCard ──────┘                           └─ links to /events/[...key]
   │   ├─ EntityCards, StatCard, AIMetadataPanel, ShareButton
   │   └─ Skeletons / EmptyState / ErrorState (ui/)
   └─ Footer
```

One `EventCard` is the atom every listing reuses; `Section` (carousel), `EventGrid`,
`LoadMoreGrid` (paginated), and `EventList` (compact) are the only containers.

## State management

Deliberately no state library — state is local and scoped:

- **Server data** — `useAsync` (a generic fetch-on-mount hook with abort + reload) powers
  `useHomepage / useFeed / useEvent / useBrowseResults / useEntity / useAnalytics /
  useDirectory / useRecommendations`. `usePlatformSearch` is the imperative NL-search hook.
- **Client persistence** (no auth) — `useLocalStorage` backs `useSavedEvents`,
  `useRecentlyViewed`, and `usePreferences`; `useSearchHistory` and `useTheme` persist too.
  Saved events, recently-viewed, search history, and preferences live entirely on the device.
- **Recommendations without accounts** — the client sends its saved/viewed event keys to
  `POST /platform/recommendations`; the backend replays them into the 5B engine as a
  transient anonymous user and returns explained picks. Stateless, no login.

## API integration

All requests flow through `services/api.ts` (`apiGet`/`apiPost`, one place for the base URL,
JSON parsing, `ApiError`, and abort handling). `services/platform.ts` is one typed function
per endpoint — the UI never builds a URL. Event keys are catalog URLs containing `/` and
sometimes `#`; `utils/eventKey.ts` encodes them per-segment so they survive both Next routing
and the backend `:path` route.

## Responsive behavior

- Mobile-first Tailwind: grids collapse `1 → 2 → 3` columns (`sm:` / `lg:`), the navbar
  switches to a hamburger menu under `md:`, homepage rows are horizontally-scrollable
  carousels on every width, and the page body never scrolls horizontally.
- `container` is centered with responsive padding; long text clamps (`line-clamp`).

## Accessibility

Semantic landmarks (`header`/`main`/`footer`/`nav`), `aria-label`/`aria-pressed` on icon
buttons and toggles, `role="search"` forms, visible `:focus-visible` rings on every
interactive element, `role="alert"` error states, and `prefers-reduced-motion` disabling
animations. Dark mode is a first-class theme (see [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md)).

## Running it

```
# 1. seed the catalog (once, network):   cd backend && python -m spikes.seed_catalog
# 2. backend:                            uvicorn app.main:app --port 8000
# 3. frontend:                           cd frontend && npm run dev      (or build && start)
# open http://localhost:3000
```

## Constraints honored

No backend logic modified (only the additive `/platform/*` router + one read-only
`directory()` method); no duplicated intelligence (all data from the Platform Service); no
auth, payments, notifications, or deployment. Everything reuses existing layers.
