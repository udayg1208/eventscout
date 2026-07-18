"use client";

import { useMemo, useState } from "react";

import { EventCard } from "@/components/EventCard";
import { applyFilters, DEFAULT_FILTERS, Filters, type FilterState } from "@/components/Filters";
import { Button } from "@/components/ui/Button";
import { GridSkeleton } from "@/components/ui/Skeleton";
import { EmptyState, ErrorState } from "@/components/ui/States";
import type { PagedResult } from "@/hooks/usePaginated";
import type { EventDTO } from "@/types/platform";

/**
 * Renders a server-paginated list of events: filters + grid + a real "Load More"
 * that fetches the next page from the API (not a client-side slice), so the user can
 * page through the entire catalog. The client filters (online/free/sort) refine the
 * pages loaded so far — Load More keeps fetching until every event is loaded.
 */
export function EventFeed({
  result,
  withFilters = true,
  emptyTitle = "No events here yet",
  emptyMessage = "Nothing matches right now. Try clearing the filters or check back soon.",
}: {
  result: PagedResult<EventDTO>;
  withFilters?: boolean;
  emptyTitle?: string;
  emptyMessage?: string;
}) {
  const { status, items, total, hasMore, loadingMore, loadMore, error, reload } = result;
  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS);
  const shown = useMemo(
    () => (withFilters ? applyFilters(items, filters) : items),
    [withFilters, items, filters],
  );

  if (status === "loading") return <GridSkeleton />;
  if (status === "error") return <ErrorState message={error ?? undefined} onRetry={reload} />;

  const remaining = Math.max(0, total - items.length);

  return (
    <div className="space-y-5">
      {withFilters && <Filters value={filters} onChange={setFilters} resultCount={shown.length} />}

      {shown.length === 0 ? (
        <EmptyState title={emptyTitle} message={emptyMessage} />
      ) : (
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {shown.map((e) => (
            <div key={e.key}>
              <EventCard event={e} />
            </div>
          ))}
        </div>
      )}

      {hasMore && (
        <div className="mt-8 flex justify-center">
          <Button variant="outline" onClick={loadMore} disabled={loadingMore}>
            {loadingMore ? "Loading…" : `Load more (${remaining.toLocaleString()} more)`}
          </Button>
        </div>
      )}

      {!hasMore && total > 0 && items.length >= total && (
        <p className="mt-6 text-center text-sm text-muted">
          All {total.toLocaleString()} events loaded
        </p>
      )}
    </div>
  );
}
