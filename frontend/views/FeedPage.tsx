"use client";

import { EventFeed } from "@/components/EventFeed";
import { PageHeader } from "@/components/PageHeader";
import { useFeedPaged } from "@/hooks/usePlatform";
import type { FeedMeta } from "@/utils/feeds";

/** One template for every "list of events" route (trending, category, section…).
 * Category feeds are server-paginated: the count is the full catalog total and
 * "Load More" pages through every matching event. */
export function FeedPage({ meta }: { meta: FeedMeta }) {
  const result = useFeedPaged(meta.source);
  const count = result.status === "success" ? result.total : undefined;

  return (
    <div className="container py-8">
      <PageHeader title={meta.title} description={meta.description} count={count} />
      <EventFeed result={result} />
    </div>
  );
}
