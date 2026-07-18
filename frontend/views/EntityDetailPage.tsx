"use client";

import { EventFeed } from "@/components/EventFeed";
import { Breadcrumbs, PageHeader } from "@/components/PageHeader";
import { StatCard } from "@/components/StatCard";
import { useEntity, useEntityEvents } from "@/hooks/usePlatform";
import type { BrowseDimension, EntityKind } from "@/services/platform";

const META: Record<
  Exclude<EntityKind, "series">,
  { label: string; index: string; dim: BrowseDimension }
> = {
  community: { label: "Community", index: "/communities", dim: "community" },
  organizer: { label: "Organizer", index: "/organizers", dim: "organizer" },
  city: { label: "City", index: "/cities", dim: "city" },
};

export function EntityDetailPage({
  kind,
  name,
}: {
  kind: "community" | "organizer" | "city";
  name: string;
}) {
  const profile = useEntity(kind, name);
  const result = useEntityEvents(META[kind].dim, name);
  const p = profile.data;
  const count = result.status === "success" ? result.total : undefined;

  return (
    <div className="container py-8">
      <PageHeader
        title={name}
        description={`${META[kind].label} · events across India`}
        count={count}
        breadcrumb={
          <Breadcrumbs
            trail={[
              { label: `${META[kind].label}s`, href: META[kind].index },
              { label: name },
            ]}
          />
        }
      />

      {p && (
        <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <StatCard label="Total events" value={p.total_events} />
          <StatCard label="Active now" value={p.active_events} />
          {p.cities.length > 0 && <StatCard label="Cities" value={p.cities.length} />}
        </div>
      )}

      <EventFeed
        result={result}
        emptyTitle="No events"
        emptyMessage={`No events for ${name} right now.`}
      />
    </div>
  );
}
