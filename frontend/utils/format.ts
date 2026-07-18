/** Presentation helpers — pure functions, no side effects. */

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
const WEEKDAY = new Intl.DateTimeFormat("en-IN", { weekday: "long" });

/** "18 Jul 2026" for single-day, "18 – 20 Jul 2026" for a range. */
export function formatEventDate(start: string, end: string | null): string {
  if (!end || end === start) return FULL.format(parseISO(start));
  return `${DAY.format(parseISO(start))} – ${FULL.format(parseISO(end))}`;
}

export function formatWeekday(start: string): string {
  return WEEKDAY.format(parseISO(start));
}

/** Days from today until the event start (negative = past). */
export function daysUntil(start: string): number {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const diff = parseISO(start).getTime() - today.getTime();
  return Math.round(diff / 86_400_000);
}

/** "in 3 days" / "tomorrow" / "today" / "in 2 weeks". */
export function relativeStart(start: string): string {
  const d = daysUntil(start);
  if (d < 0) return "past";
  if (d === 0) return "today";
  if (d === 1) return "tomorrow";
  if (d < 14) return `in ${d} days`;
  if (d < 60) return `in ${Math.round(d / 7)} weeks`;
  return `in ${Math.round(d / 30)} months`;
}

/** Human label for where the event happens. */
export function formatWhere(
  city: string | null,
  isOnline: boolean,
): string {
  if (city) return city;
  if (isOnline) return "Online";
  return "Location TBA";
}

export function formatNumber(n: number): string {
  return new Intl.NumberFormat("en-IN").format(n);
}

export function titleCase(s: string): string {
  return s.replace(/(^|[\s-])(\w)/g, (_, p, c) => p + c.toUpperCase());
}
