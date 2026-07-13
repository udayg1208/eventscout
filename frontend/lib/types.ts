/**
 * Types mirroring the frozen backend response models
 * (backend/app/models/event.py, search.py; api/routes/search.py::SearchResponse).
 * Kept in sync by hand — these are the single source of truth on the client.
 */

export type EventCategory =
  | "workshop"
  | "meetup"
  | "conference"
  | "hackathon"
  | "startup"
  | "ai"
  | "webinar";

/** One normalized event (backend Event model). */
export interface EventItem {
  title: string;
  description: string | null;
  url: string;
  city: string | null;
  location: string | null;
  is_online: boolean;
  start_date: string; // ISO date, e.g. "2026-07-18"
  end_date: string | null;
  category: EventCategory;
  is_free: boolean | null; // null = unknown
  price: string | null;
  provider: string; // "confs.tech" | "devfolio" | ...
}

/** The structured query the backend parsed the text into (backend SearchQuery). */
export interface SearchQuery {
  keywords: string[];
  city: string | null;
  categories: EventCategory[];
  date_from: string | null;
  date_to: string | null;
  free_only: boolean;
}

/** Response of POST /search (backend SearchResponse). */
export interface SearchResponse {
  query: SearchQuery;
  count: number;
  events: EventItem[];
  cached: boolean;
}
