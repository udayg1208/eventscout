# Event Discovery — Frontend

Next.js (App Router) + Tailwind UI for the Event Discovery Agent. Consumes the frozen
backend endpoint `POST /search`.

## Run locally

```bash
cd frontend
npm install
cp .env.local.example .env.local        # point at your backend
npm run dev                              # http://localhost:3000
```

The backend must be running (default `http://127.0.0.1:8000`). Set the base URL via
`NEXT_PUBLIC_API_BASE_URL` in `.env.local`.

## Scripts
- `npm run dev` — dev server
- `npm run build` — production build
- `npm run start` — serve the production build

## Structure
```
app/            layout.tsx (theme no-FOUC script), page.tsx (orchestrator), globals.css
components/     SearchBar, EventCard, EventList, CategoryChip, SourceBadge, PriceBadge,
               SkeletonCard, EmptyState, ErrorState, ThemeToggle, Header, icons, ...
hooks/         useSearch (abortable), useSearchHistory (localStorage), useTheme
lib/           types.ts (mirrors backend models), api.ts, format.ts, styles.ts
```

## Notes
- Types in `lib/types.ts` mirror the backend Pydantic models (single source of truth).
- The backend returns all ranked matches at once; pagination is client-side ("Load more").
- Dark mode uses Tailwind `class` strategy with a pre-hydration script (no flash).
- For deployment, add the frontend's origin to the backend's `CORS_ORIGINS`.
