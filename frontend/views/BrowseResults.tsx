"use client";

import { EventFeed } from "@/components/EventFeed";
import { Breadcrumbs, PageHeader } from "@/components/PageHeader";
import { useBrowseResults } from "@/hooks/usePlatform";
import type { BrowseDimension } from "@/services/platform";
import { titleCase } from "@/utils/format";

const LABEL: Record<string, string> = {
  category: "Category",
  city: "City",
  topic: "Topic",
  technology: "Technology",
  difficulty: "Difficulty",
  audience: "Audience",
  community: "Community",
  organizer: "Organizer",
};

export function BrowseResults({
  dimension,
  value,
}: {
  dimension: BrowseDimension;
  value: string;
}) {
  const result = useBrowseResults(dimension, value);
  const count = result.status === "success" ? result.total : undefined;

  return (
    <div className="container py-8">
      <PageHeader
        title={value}
        description={`${LABEL[dimension] ?? titleCase(dimension)} · events across India`}
        count={count}
        breadcrumb={
          <Breadcrumbs trail={[{ label: "Browse", href: "/browse" }, { label: value }]} />
        }
      />
      <EventFeed
        result={result}
        emptyTitle="No events"
        emptyMessage={`No events found for “${value}”.`}
      />
    </div>
  );
}
