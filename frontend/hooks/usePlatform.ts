"use client";

import {
  browse,
  discover,
  getAnalytics,
  getDirectory,
  getEntity,
  getEvent,
  getHomepage,
  getRecommendations,
  getSimilar,
  type BrowseDimension,
  type EntityKind,
} from "@/services/platform";
import type { EventDTO } from "@/types/platform";
import type { FeedSource } from "@/utils/feeds";

import { useAsync } from "./useAsync";
import { usePaginated, type PagedResult } from "./usePaginated";

/** Page size for offset-paginated browse feeds (Load More fetches this many at a time). */
const BROWSE_PAGE = 48;

export function useHomepage(city?: string) {
  return useAsync((signal) => getHomepage(city, 10, signal), [city]);
}

export function useFeed(source: FeedSource, city?: string) {
  return useAsync<EventDTO[]>(
    async (signal) => {
      if (source.kind === "discover")
        return discover(source.feed, { city, limit: 60 }, signal);
      if (source.kind === "category")
        return (await browse("category", source.category, { limit: 60 }, signal)).events;
      const hp = await getHomepage(city, 40, signal);
      return hp.sections[source.section] ?? [];
    },
    [source.kind, JSON.stringify(source), city],
  );
}

/**
 * Offset-paginated feed for the FeedPage template. A "category" source pages through
 * the *entire* catalog for that category (Load More fetches the next page from the
 * server); discover/section sources return their single curated page (hasMore=false).
 */
export function useFeedPaged(source: FeedSource, city?: string): PagedResult<EventDTO> {
  return usePaginated<EventDTO>(
    async (offset, signal) => {
      if (source.kind === "category") {
        const p = await browse("category", source.category, { offset, limit: BROWSE_PAGE }, signal);
        return { items: p.events, total: p.total_count, hasMore: p.has_more };
      }
      if (source.kind === "discover") {
        const items = await discover(source.feed, { city, limit: 60 }, signal);
        return { items, total: items.length, hasMore: false };
      }
      const hp = await getHomepage(city, 40, signal);
      const items = hp.sections[source.section] ?? [];
      return { items, total: items.length, hasMore: false };
    },
    [source.kind, JSON.stringify(source), city],
  );
}

/** Offset-paginated browse over one dimension (category/city/topic/community/organizer/…). */
export function usePagedBrowse(
  dimension: BrowseDimension,
  value: string,
  enabled = true,
): PagedResult<EventDTO> {
  return usePaginated<EventDTO>(
    (offset, signal) =>
      browse(dimension, value, { offset, limit: BROWSE_PAGE }, signal).then((p) => ({
        items: p.events,
        total: p.total_count,
        hasMore: p.has_more,
      })),
    [dimension, value],
    enabled && Boolean(value),
  );
}

export function useEvent(key: string) {
  return useAsync((signal) => getEvent(key, signal), [key], Boolean(key));
}

export function useSimilar(key: string) {
  return useAsync((signal) => getSimilar(key, 8, signal), [key], Boolean(key));
}

export function useBrowseResults(dimension: BrowseDimension, value: string) {
  return usePagedBrowse(dimension, value);
}

export function useEntity(kind: EntityKind, name: string) {
  return useAsync((signal) => getEntity(kind, name, signal), [kind, name], Boolean(name));
}

export function useEntityEvents(dimension: BrowseDimension, name: string) {
  return usePagedBrowse(dimension, name);
}

export function useAnalytics() {
  return useAsync((signal) => getAnalytics(signal), []);
}

export function useDirectory() {
  return useAsync((signal) => getDirectory(signal), []);
}

export function useRecommendations(saved: string[], viewed: string[]) {
  const seedKey = [...saved].sort().join(",") + "#" + [...viewed].sort().join(",");
  return useAsync(
    (signal) => getRecommendations({ saved, viewed, limit: 24 }, signal),
    [seedKey],
    saved.length > 0 || viewed.length > 0,
  );
}
