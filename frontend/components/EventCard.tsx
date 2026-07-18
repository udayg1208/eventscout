"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import type { EventDTO } from "@/types/platform";
import { cn } from "@/utils/cn";
import { encodeEventKey } from "@/utils/eventKey";
import { formatEventDate, formatWhere, relativeStart } from "@/utils/format";

import { SaveButton } from "./SaveButton";
import { CategoryBadge, FormatBadge, PriceBadge, ProviderBadge } from "./ui/Badge";
import { buttonClass } from "./ui/Button";
import { Card } from "./ui/Card";
import { CalendarIcon, ExternalIcon, PinIcon } from "./ui/icons";

/** The core event tile. `children` renders an extra slot above the footer
 * (used by RecommendationCard for its reasons). */
export function EventCard({
  event,
  children,
  className,
}: {
  event: EventDTO;
  children?: ReactNode;
  className?: string;
}) {
  const href = `/events/${encodeEventKey(event.key)}`;
  return (
    <Card hover className={cn("flex h-full flex-col p-5", className)}>
      <div className="mb-3 flex items-start justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <CategoryBadge category={event.category} />
          <FormatBadge isOnline={event.is_online} />
          <PriceBadge isFree={event.is_free} price={event.price} />
        </div>
        <SaveButton event={event} />
      </div>

      <h3 className="text-base font-semibold leading-snug">
        <Link href={href} className="line-clamp-2 text-ink transition-colors hover:text-accent">
          {event.title}
        </Link>
      </h3>

      {event.description && (
        <p className="mt-2 line-clamp-2 text-sm text-muted">{event.description}</p>
      )}

      <dl className="mt-4 space-y-1.5 text-sm text-muted">
        <div className="flex items-center gap-2">
          <CalendarIcon className="h-4 w-4 shrink-0 text-faint" />
          <span>
            {formatEventDate(event.start_date, event.end_date)}
            <span className="text-faint"> · {relativeStart(event.start_date)}</span>
          </span>
        </div>
        <div className="flex items-center gap-2">
          <PinIcon className="h-4 w-4 shrink-0 text-faint" />
          <span className="truncate">{formatWhere(event.city, event.is_online)}</span>
        </div>
      </dl>

      {children}

      <div className="mt-auto flex items-center justify-between gap-2 border-t border-line pt-3">
        <ProviderBadge provider={event.provider} />
        <div className="flex items-center gap-1">
          <Link href={href} className={buttonClass("ghost", "sm")}>
            Details
          </Link>
          <a
            href={event.url}
            target="_blank"
            rel="noopener noreferrer"
            className={buttonClass("secondary", "sm")}
            aria-label={`Register for ${event.title} (opens in a new tab)`}
          >
            Register
            <ExternalIcon className="h-3.5 w-3.5" />
          </a>
        </div>
      </div>
    </Card>
  );
}
