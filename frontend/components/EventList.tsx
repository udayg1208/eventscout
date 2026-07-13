"use client";

import { useEffect, useState } from "react";

import { EventCard } from "@/components/EventCard";
import type { EventItem } from "@/lib/types";

const PAGE_SIZE = 12;

/**
 * The backend returns all ranked matches at once, so pagination is client-side:
 * reveal in batches of PAGE_SIZE.
 */
export function EventList({ events }: { events: EventItem[] }) {
  const [visible, setVisible] = useState(PAGE_SIZE);

  // Reset the window whenever a new result set arrives.
  useEffect(() => setVisible(PAGE_SIZE), [events]);

  const shown = events.slice(0, visible);
  const remaining = events.length - shown.length;

  return (
    <div>
      <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {shown.map((event) => (
          <EventCard key={`${event.provider}:${event.url}`} event={event} />
        ))}
      </ul>

      {remaining > 0 && (
        <div className="mt-8 flex justify-center">
          <button
            type="button"
            onClick={() => setVisible((v) => v + PAGE_SIZE)}
            className="rounded-full border border-slate-300 bg-white px-6 py-2.5 text-sm font-medium text-slate-700 transition hover:border-violet-400 hover:text-violet-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:border-violet-500/50 dark:hover:text-violet-300"
          >
            Load more ({remaining} more)
          </button>
        </div>
      )}
    </div>
  );
}
