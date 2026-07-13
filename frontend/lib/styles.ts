import type { EventCategory } from "./types";

/**
 * Full static class strings (never interpolated) so Tailwind's purge keeps them.
 */

export const CATEGORY_LABELS: Record<EventCategory, string> = {
  workshop: "Workshop",
  meetup: "Meetup",
  conference: "Conference",
  hackathon: "Hackathon",
  startup: "Startup",
  ai: "AI",
  webinar: "Webinar",
};

export const CATEGORY_CLASSES: Record<EventCategory, string> = {
  workshop: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",
  meetup: "bg-sky-100 text-sky-800 dark:bg-sky-500/15 dark:text-sky-300",
  conference:
    "bg-violet-100 text-violet-800 dark:bg-violet-500/15 dark:text-violet-300",
  hackathon: "bg-rose-100 text-rose-800 dark:bg-rose-500/15 dark:text-rose-300",
  startup:
    "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300",
  ai: "bg-fuchsia-100 text-fuchsia-800 dark:bg-fuchsia-500/15 dark:text-fuchsia-300",
  webinar: "bg-cyan-100 text-cyan-800 dark:bg-cyan-500/15 dark:text-cyan-300",
};

/** Known source badges; unknown providers fall back to a neutral style. */
export const SOURCE_META: Record<string, { label: string; className: string }> = {
  "confs.tech": {
    label: "Confs.tech",
    className:
      "bg-blue-50 text-blue-700 ring-1 ring-blue-200 dark:bg-blue-500/10 dark:text-blue-300 dark:ring-blue-500/20",
  },
  devfolio: {
    label: "Devfolio",
    className:
      "bg-indigo-50 text-indigo-700 ring-1 ring-indigo-200 dark:bg-indigo-500/10 dark:text-indigo-300 dark:ring-indigo-500/20",
  },
};

export function sourceMeta(provider: string) {
  return (
    SOURCE_META[provider] ?? {
      label: provider,
      className:
        "bg-slate-100 text-slate-600 ring-1 ring-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:ring-slate-700",
    }
  );
}

export const ALL_CATEGORIES: EventCategory[] = [
  "workshop",
  "meetup",
  "conference",
  "hackathon",
  "startup",
  "ai",
  "webinar",
];
