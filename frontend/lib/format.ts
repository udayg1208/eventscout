/** Presentation helpers (dates, labels). Pure functions. */

function parseISO(date: string): Date {
  // Treat as a local calendar date (avoid timezone shifting the day).
  const [y, m, d] = date.split("-").map(Number);
  return new Date(y, (m ?? 1) - 1, d ?? 1);
}

const DAY = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short" });
const FULL = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  year: "numeric",
});

/** "18 Jul 2026" for single-day, "18–20 Jul 2026" for a range. */
export function formatEventDate(start: string, end: string | null): string {
  if (!end || end === start) return FULL.format(parseISO(start));
  return `${DAY.format(parseISO(start))} – ${FULL.format(parseISO(end))}`;
}

/** Human label for where the event happens. */
export function formatWhere(
  city: string | null,
  location: string | null,
  isOnline: boolean,
): string {
  if (city) return city;
  if (isOnline) return "Online";
  return location ?? "Location TBA";
}
