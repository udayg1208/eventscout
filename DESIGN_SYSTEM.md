# Design System (Phase 6B)

EventScout's visual language: a professional, minimal SaaS aesthetic — calm surfaces, one
accent, generous whitespace, subtle motion, first-class dark mode, and excellent legibility.
Everything is Tailwind + a small set of semantic design tokens.

## Design principles

1. **Content first.** The event is the hero; chrome recedes. Cards are quiet until hovered.
2. **One accent.** Violet is the single brand/interactive color; everything else is neutral
   slate. Category colors are the only other hues, used sparingly as small badges.
3. **Semantic tokens, not scattered `dark:`.** Colors are CSS variables that flip with the
   theme, so components read `bg-surface` / `text-muted` / `border-line` and work in both
   modes automatically.
4. **Subtle motion.** Short, purposeful transitions (hover lift, fade/slide-in). Never
   decorative; fully disabled under `prefers-reduced-motion`.
5. **Reuse over repetition.** One `EventCard`, one `Section`, one `FeedPage`. No duplicated UI.

## Tokens

Defined in `app/globals.css` as RGB channel triples, exposed to Tailwind as semantic colors
(`tailwind.config.ts`). Each has a light and dark value.

| Token | Tailwind | Role |
|---|---|---|
| `--bg` | `bg-bg` | page background |
| `--surface` / `--surface-2` | `bg-surface` / `bg-surface-2` | cards / raised & hover |
| `--border` / `--border-strong` | `border` / `border-line-strong` | hairlines |
| `--text` | `text-ink` | primary text |
| `--muted` / `--faint` | `text-muted` / `text-faint` | secondary / tertiary text |
| `--accent` (+ `-hover`, `-soft`, `-fg`) | `bg-accent`, `text-accent`, `bg-accent-soft` | brand / interactive |

Light: near-white surfaces on `slate-50`; violet-600 accent. Dark: `slate-950` background,
`slate-900` surfaces, brighter violet-500 accent. Changing a token restyles the whole app.

### Category / status colors (static badge classes, `utils/categories.ts`)

AI → violet · Hackathon → amber · Conference → blue · Meetup → emerald · Workshop → rose ·
Startup → orange · Webinar → cyan. Difficulty (Beginner/Intermediate/Advanced) and lifecycle
(Upcoming / Closing Soon / Live Today / Completed) have their own fixed classes. All are full,
purge-safe class strings — never interpolated.

## Typography

System font stack (`ui-sans-serif, system-ui, "Segoe UI", Roboto, …`) — no web-font fetch, so
builds stay hermetic and text paints instantly. Tightened tracking on headings
(`letter-spacing: -0.02em`), `font-feature-settings` for refined numerals, antialiased.
Scale: hero `text-5xl` bold → page titles `text-2xl/3xl` → section `text-lg` → body `text-sm`
→ meta `text-xs`. Line clamps keep cards uniform.

## Spacing & shape

- **Container**: centered, `max-width 1240px`, responsive padding.
- **Radii**: `rounded-lg` (controls) · `rounded-xl` (inputs) · `rounded-2xl` (cards).
- **Elevation**: borders do most of the work; `shadow-soft` / `shadow-card` add a gentle lift
  on hover. Dark mode leans on borders over shadows.
- **Rhythm**: `gap-5` grids, `space-y-10` between homepage sections, `py-8` page padding.

## Components (the reusable kit)

**Primitives** (`components/ui/`): `Button` (primary/secondary/outline/ghost × sm/md/lg, plus
`buttonClass()` for link-styled anchors), `Card`, `Badge` (+ Category/Difficulty/Lifecycle/
Price/Format/Provider), `Skeleton` (+ EventCard/Grid/Row skeletons, shimmer), `States`
(Spinner/EmptyState/ErrorState), and an inline SVG `icons` set.

**Composites** (`components/`): `EventCard` (the atom), `EventGrid`, `LoadMoreGrid`
(paginated, generic), `EventList` (compact), `Section` (carousel with scroll controls),
`SearchBar`, `Filters` (+ `applyFilters`), `CategoryChips`, `RecommendationCard`,
`EntityCards` (Community/Organizer/City), `StatCard`, `AIMetadataPanel`, `SaveButton`,
`ShareButton`, `PageHeader`/`Breadcrumbs`, `Navbar`, `Footer`, `ThemeToggle`.

Every "list of events" surface composes the same three containers (Section / Grid /
LoadMoreGrid) around the same `EventCard`, so a change to the card propagates everywhere.

## Dark mode

Tailwind class strategy (`.dark` on `<html>`). A pre-hydration inline script in the root
layout sets the theme before first paint (no flash), reading `localStorage.theme` then the OS
`prefers-color-scheme`. `useTheme` toggles the class and persists the choice; `ThemeToggle`
(sun/moon) lives in the navbar. Because components use semantic tokens, dark mode needs almost
no per-component overrides.

## States

Every data view renders four states explicitly: **loading** (shape-matched skeletons — grid or
carousel), **error** (`role="alert"` panel with retry), **empty** (guidance + a call to
action), and **success**. No spinner-only screens; skeletons preserve layout to avoid shift.

## Motion

Three keyframes (`fade-in`, `slide-up`, `shimmer`) at 0.3–0.4s with an ease-out curve; hover
transitions on cards/links at ~200ms. All suppressed under `prefers-reduced-motion: reduce`.
