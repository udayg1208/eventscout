import Link from "next/link";

import type { EventDTO } from "@/types/platform";
import { encodeEventKey } from "@/utils/eventKey";
import { formatEventDate, formatWhere } from "@/utils/format";

import { SaveButton } from "./SaveButton";
import { CategoryBadge, PriceBadge } from "./ui/Badge";
import { CalendarIcon, PinIcon } from "./ui/icons";

/** Compact vertical list — used on the dashboard, saved, and recently-viewed. */
export function EventList({ events }: { events: EventDTO[] }) {
  return (
    <ul className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface">
      {events.map((event) => (
        <li
          key={event.key}
          className="flex items-center gap-4 p-4 transition-colors hover:bg-surface-2"
        >
          <div className="min-w-0 flex-1">
            <Link
              href={`/events/${encodeEventKey(event.key)}`}
              className="block truncate font-medium text-ink hover:text-accent"
            >
              {event.title}
            </Link>
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
              <CategoryBadge category={event.category} />
              <span className="flex items-center gap-1">
                <CalendarIcon className="h-3.5 w-3.5" />
                {formatEventDate(event.start_date, event.end_date)}
              </span>
              <span className="flex items-center gap-1">
                <PinIcon className="h-3.5 w-3.5" />
                {formatWhere(event.city, event.is_online)}
              </span>
              <PriceBadge isFree={event.is_free} price={event.price} />
            </div>
          </div>
          <SaveButton event={event} />
        </li>
      ))}
    </ul>
  );
}
