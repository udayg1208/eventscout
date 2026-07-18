import type { ReactNode } from "react";

import type { EventDTO } from "@/types/platform";

import { EventCard } from "./EventCard";
import { EmptyState } from "./ui/States";

export function EventGrid({
  events,
  empty,
}: {
  events: EventDTO[];
  empty?: ReactNode;
}) {
  if (!events.length) {
    return <>{empty ?? <EmptyState message="No events match here yet." />}</>;
  }
  return (
    <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
      {events.map((event) => (
        <EventCard key={event.key} event={event} />
      ))}
    </div>
  );
}
