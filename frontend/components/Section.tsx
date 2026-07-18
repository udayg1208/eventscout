"use client";

import Link from "next/link";
import { useRef, type ReactNode } from "react";

import type { EventDTO } from "@/types/platform";

import { EventCard } from "./EventCard";
import { buttonClass } from "./ui/Button";
import { ArrowRightIcon, ChevronLeftIcon, ChevronRightIcon } from "./ui/icons";

/** A horizontally-scrolling row of event cards, used to compose the homepage. */
export function Section({
  title,
  events,
  viewAllHref,
  icon,
}: {
  title: string;
  events: EventDTO[];
  viewAllHref?: string;
  icon?: ReactNode;
}) {
  const track = useRef<HTMLDivElement>(null);
  if (!events.length) return null;

  const scroll = (dir: number) =>
    track.current?.scrollBy({
      left: dir * track.current.clientWidth * 0.85,
      behavior: "smooth",
    });

  return (
    <section className="animate-slide-up">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-ink">
          {icon}
          {title}
        </h2>
        <div className="flex items-center gap-1">
          {viewAllHref && (
            <Link href={viewAllHref} className={buttonClass("ghost", "sm")}>
              View all
              <ArrowRightIcon className="h-4 w-4" />
            </Link>
          )}
          <button
            type="button"
            aria-label="Scroll left"
            onClick={() => scroll(-1)}
            className="hidden h-8 w-8 items-center justify-center rounded-lg border border-line text-muted transition-colors hover:bg-surface-2 hover:text-ink sm:inline-flex"
          >
            <ChevronLeftIcon className="h-4 w-4" />
          </button>
          <button
            type="button"
            aria-label="Scroll right"
            onClick={() => scroll(1)}
            className="hidden h-8 w-8 items-center justify-center rounded-lg border border-line text-muted transition-colors hover:bg-surface-2 hover:text-ink sm:inline-flex"
          >
            <ChevronRightIcon className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div
        ref={track}
        className="no-scrollbar flex snap-x snap-mandatory gap-5 overflow-x-auto pb-2"
      >
        {events.map((event) => (
          <div key={event.key} className="w-[300px] shrink-0 snap-start">
            <EventCard event={event} />
          </div>
        ))}
      </div>
    </section>
  );
}
