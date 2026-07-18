/**
 * Typed client for the backend Platform HTTP surface (backend
 * app/api/routes/platform.py). One function per endpoint — the UI never builds
 * URLs itself. All data the app shows comes from here (the Platform Service).
 */

import type {
  AnalyticsDTO,
  DirectoryDTO,
  EntityProfileDTO,
  EventDetailDTO,
  EventDTO,
  HomepageDTO,
  PlatformSearchResponse,
  RecommendationDTO,
} from "@/types/platform";

import { encodeEventKey } from "@/utils/eventKey";

import { apiGet, apiPost } from "./api";

export type DiscoverFeed =
  | "trending"
  | "popular"
  | "newest"
  | "registration-closing"
  | "this-weekend"
  | "this-month"
  | "online"
  | "offline"
  | "free"
  | "paid"
  | "nearby";

export type BrowseDimension =
  | "category"
  | "city"
  | "topic"
  | "technology"
  | "difficulty"
  | "audience"
  | "community"
  | "organizer"
  | "online"
  | "offline";

export type EntityKind = "community" | "organizer" | "city" | "series";

// The event key can contain any character, so it is transported as an opaque base64url
// token (alphabet [A-Za-z0-9_-]) — always a safe single path segment. The backend
// `/events/by-id/{token}` route decodes it back to the key. No reserved-char hazards.
const eventPath = (key: string) => `/platform/events/by-id/${encodeEventKey(key)}`;
const q = (v: string) => encodeURIComponent(v);

export const getHomepage = (city?: string, limit = 8, signal?: AbortSignal) =>
  apiGet<HomepageDTO>(
    `/platform/homepage?limit=${limit}${city ? `&city=${q(city)}` : ""}`,
    signal,
  );

export const discover = (
  feed: DiscoverFeed,
  opts: { city?: string; limit?: number } = {},
  signal?: AbortSignal,
) => {
  const { city, limit = 24 } = opts;
  return apiGet<EventDTO[]>(
    `/platform/discover/${feed}?limit=${limit}${city ? `&city=${q(city)}` : ""}`,
    signal,
  );
};

export interface BrowsePage {
  events: EventDTO[];
  total_count: number;
  offset: number;
  limit: number;
  has_more: boolean;
}

export const browse = (
  dimension: BrowseDimension,
  value: string,
  opts: { offset?: number; limit?: number } = {},
  signal?: AbortSignal,
) => {
  const { offset = 0, limit = 48 } = opts;
  return apiGet<BrowsePage>(
    `/platform/browse/${dimension}/${q(value)}?offset=${offset}&limit=${limit}`,
    signal,
  );
};

export const getEvent = (key: string, signal?: AbortSignal) =>
  apiGet<EventDetailDTO>(eventPath(key), signal);

export const getSimilar = (key: string, limit = 10, signal?: AbortSignal) =>
  apiGet<EventDTO[]>(`${eventPath(key)}/similar?limit=${limit}`, signal);

export const getEntity = (kind: EntityKind, name: string, signal?: AbortSignal) =>
  apiGet<EntityProfileDTO>(`/platform/entities/${kind}/${q(name)}`, signal);

export const getAnalytics = (signal?: AbortSignal) =>
  apiGet<AnalyticsDTO>(`/platform/analytics`, signal);

export const getDirectory = (signal?: AbortSignal) =>
  apiGet<DirectoryDTO>(`/platform/directory`, signal);

export const searchPlatform = (query: string, limit = 24, signal?: AbortSignal) =>
  apiPost<PlatformSearchResponse>(`/platform/search`, { query, limit }, signal);

export const getRecommendations = (
  payload: { saved: string[]; viewed: string[]; limit?: number },
  signal?: AbortSignal,
) => apiPost<RecommendationDTO[]>(`/platform/recommendations`, payload, signal);
