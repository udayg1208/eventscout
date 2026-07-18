"use client";

import { useSavedEvents } from "@/hooks/useLocalStorage";
import type { EventDTO } from "@/types/platform";
import { cn } from "@/utils/cn";

import { BookmarkIcon, BookmarkSolidIcon } from "./ui/icons";

export function SaveButton({
  event,
  showLabel = false,
  className,
}: {
  event: EventDTO;
  showLabel?: boolean;
  className?: string;
}) {
  const { isSaved, toggle, ready } = useSavedEvents();
  const saved = ready && isSaved(event.key);

  return (
    <button
      type="button"
      onClick={() => toggle(event)}
      aria-pressed={saved}
      aria-label={saved ? "Remove from saved" : "Save event"}
      title={saved ? "Saved" : "Save"}
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm font-medium transition-colors",
        saved ? "text-accent" : "text-faint hover:bg-surface-2 hover:text-ink",
        className,
      )}
    >
      {saved ? (
        <BookmarkSolidIcon className="h-4 w-4" />
      ) : (
        <BookmarkIcon className="h-4 w-4" />
      )}
      {showLabel && <span>{saved ? "Saved" : "Save"}</span>}
    </button>
  );
}
