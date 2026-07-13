import { CategoryChip } from "@/components/CategoryChip";
import { PriceBadge } from "@/components/PriceBadge";
import { SourceBadge } from "@/components/SourceBadge";
import {
  CalendarIcon,
  ExternalIcon,
  GlobeIcon,
  PinIcon,
} from "@/components/icons";
import { formatEventDate, formatWhere } from "@/lib/format";
import type { EventItem } from "@/lib/types";

export function EventCard({ event }: { event: EventItem }) {
  const where = formatWhere(event.city, event.location, event.is_online);

  return (
    <li className="animate-fade-in group flex flex-col rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:border-violet-300 hover:shadow-md dark:border-slate-800 dark:bg-slate-900 dark:hover:border-violet-500/40">
      <div className="mb-3 flex items-start justify-between gap-2">
        <CategoryChip category={event.category} />
        <SourceBadge provider={event.provider} />
      </div>

      <h3 className="mb-2 text-base font-semibold leading-snug text-slate-900 dark:text-slate-100">
        <a
          href={event.url}
          target="_blank"
          rel="noopener noreferrer"
          className="rounded outline-none hover:text-violet-700 focus-visible:underline dark:hover:text-violet-300"
        >
          {event.title}
        </a>
      </h3>

      <dl className="mb-3 space-y-1.5 text-sm text-slate-600 dark:text-slate-400">
        <div className="flex items-center gap-2">
          <dt className="sr-only">Date</dt>
          <CalendarIcon className="h-4 w-4 shrink-0 text-slate-400" />
          <dd>{formatEventDate(event.start_date, event.end_date)}</dd>
        </div>
        <div className="flex items-center gap-2">
          <dt className="sr-only">Location</dt>
          {event.is_online ? (
            <GlobeIcon className="h-4 w-4 shrink-0 text-slate-400" />
          ) : (
            <PinIcon className="h-4 w-4 shrink-0 text-slate-400" />
          )}
          <dd className="truncate">{where}</dd>
        </div>
      </dl>

      {event.description && (
        <p className="mb-4 line-clamp-3 text-sm text-slate-500 dark:text-slate-400">
          {event.description}
        </p>
      )}

      <div className="mt-auto flex items-center justify-between gap-3 pt-2">
        <PriceBadge isFree={event.is_free} price={event.price} />
        <a
          href={event.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 rounded-lg bg-violet-600 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-violet-700 focus-visible:ring-2 focus-visible:ring-violet-500 focus-visible:ring-offset-2 dark:ring-offset-slate-900"
          aria-label={`Register for ${event.title} (opens in a new tab)`}
        >
          Register
          <ExternalIcon className="h-3.5 w-3.5" />
        </a>
      </div>
    </li>
  );
}
