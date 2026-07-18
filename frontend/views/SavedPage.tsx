"use client";

import Link from "next/link";

import { EventGrid } from "@/components/EventGrid";
import { PageHeader } from "@/components/PageHeader";
import { Button, buttonClass } from "@/components/ui/Button";
import { GridSkeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/States";
import { BookmarkIcon } from "@/components/ui/icons";
import { useSavedEvents } from "@/hooks/useLocalStorage";

export function SavedPage() {
  const { items, clear, ready } = useSavedEvents();

  return (
    <div className="container py-8">
      <PageHeader
        title="Saved Events"
        description="Events you bookmarked, stored on this device."
        actions={
          items.length > 0 ? (
            <Button variant="ghost" size="sm" onClick={clear}>
              Clear all
            </Button>
          ) : undefined
        }
      />

      {!ready ? (
        <GridSkeleton />
      ) : items.length ? (
        <EventGrid events={items} />
      ) : (
        <EmptyState
          title="No saved events yet"
          message="Tap the bookmark icon on any event to save it here."
          icon={<BookmarkIcon className="h-6 w-6" />}
          action={
            <Link href="/home" className={buttonClass("primary", "md")}>
              Browse events
            </Link>
          }
        />
      )}
    </div>
  );
}
