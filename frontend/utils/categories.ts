/**
 * Static presentation maps for categories, difficulty, lifecycle, providers, and
 * homepage sections. Full class strings (never interpolated) so Tailwind's purge
 * keeps them. Single source of truth for badge styling across the app.
 */

import type { EventCategory } from "@/types/platform";

export const ALL_CATEGORIES: EventCategory[] = [
  "ai",
  "hackathon",
  "conference",
  "meetup",
  "workshop",
  "startup",
  "webinar",
];

export const CATEGORY_LABEL: Record<EventCategory, string> = {
  ai: "AI",
  hackathon: "Hackathon",
  conference: "Conference",
  meetup: "Meetup",
  workshop: "Workshop",
  startup: "Startup",
  webinar: "Webinar",
};

export const CATEGORY_CLASS: Record<EventCategory, string> = {
  ai: "bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300",
  hackathon: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300",
  conference: "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300",
  meetup: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300",
  workshop: "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300",
  startup: "bg-orange-100 text-orange-700 dark:bg-orange-500/15 dark:text-orange-300",
  webinar: "bg-cyan-100 text-cyan-700 dark:bg-cyan-500/15 dark:text-cyan-300",
};

export const DIFFICULTY_CLASS: Record<string, string> = {
  Beginner: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300",
  Intermediate: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300",
  Advanced: "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300",
};

export const LIFECYCLE: Record<string, { label: string; class: string }> = {
  upcoming: {
    label: "Upcoming",
    class: "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300",
  },
  registration_closing: {
    label: "Closing Soon",
    class: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300",
  },
  live_today: {
    label: "Live Today",
    class: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300",
  },
  completed: {
    label: "Completed",
    class: "bg-slate-100 text-slate-600 dark:bg-slate-700/40 dark:text-slate-300",
  },
  archived: {
    label: "Archived",
    class: "bg-slate-100 text-slate-600 dark:bg-slate-700/40 dark:text-slate-300",
  },
};

const PROVIDER_LABEL: Record<string, string> = {
  gdg: "GDG",
  cncf: "CNCF",
  fossunited: "FOSS United",
  hasgeek: "Hasgeek",
  devfolio: "Devfolio",
  "confs.tech": "Confs.tech",
  luma: "Lu.ma",
  seed: "Seed",
};

export function providerLabel(provider: string): string {
  return PROVIDER_LABEL[provider] ?? provider;
}

/** Homepage section key → display title (matches backend HomepageDTO.sections keys). */
export const SECTION_TITLE: Record<string, string> = {
  trending: "Trending Events",
  upcoming: "Upcoming",
  ai_events: "AI Events",
  hackathons: "Hackathons",
  conferences: "Conferences",
  meetups: "Meetups",
  workshops: "Workshops",
  startup_events: "Startup Events",
  developer_festivals: "Developer Festivals",
  government_tech: "Government Tech Events",
  university_events: "University Tech Events",
  recently_added: "Recently Added",
  registration_closing: "Registration Closing Soon",
  online_events: "Online Events",
  free_events: "Free Events",
  nearby_events: "Near You",
  recommended: "Recommended For You",
};

/** Homepage section key → the full-listing route for its "View all" link. */
export const SECTION_LINK: Record<string, string> = {
  trending: "/trending",
  upcoming: "/home",
  ai_events: "/ai-events",
  hackathons: "/hackathons",
  conferences: "/conferences",
  meetups: "/meetups",
  workshops: "/workshops",
  startup_events: "/startup-events",
  developer_festivals: "/developer-festivals",
  government_tech: "/government-tech",
  university_events: "/university-events",
  recently_added: "/new",
  registration_closing: "/closing-soon",
  online_events: "/online",
  free_events: "/free",
  nearby_events: "/cities",
  recommended: "/recommendations",
};

/** Order homepage sections are rendered in on the dashboard. */
export const SECTION_ORDER: string[] = [
  "trending",
  "recommended",
  "ai_events",
  "registration_closing",
  "hackathons",
  "conferences",
  "meetups",
  "workshops",
  "startup_events",
  "developer_festivals",
  "university_events",
  "government_tech",
  "online_events",
  "free_events",
  "recently_added",
  "nearby_events",
  "upcoming",
];
