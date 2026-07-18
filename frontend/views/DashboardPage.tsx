"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { EventList } from "@/components/EventList";
import { PageHeader } from "@/components/PageHeader";
import { RecommendationCard } from "@/components/RecommendationCard";
import { StatCard } from "@/components/StatCard";
import { buttonClass } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/States";
import { BookmarkIcon, ClockIcon } from "@/components/ui/icons";
import { useRecentlyViewed, useSavedEvents } from "@/hooks/useLocalStorage";
import { useRecommendations } from "@/hooks/usePlatform";
import { useSearchHistory } from "@/hooks/useSearchHistory";

function DashSection({
  title,
  href,
  hrefLabel,
  children,
}: {
  title: string;
  href?: string;
  hrefLabel?: string;
  children: ReactNode;
}) {
  return (
    <section>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-ink">{title}</h2>
        {href && hrefLabel && (
          <Link href={href} className="text-sm text-accent hover:underline">
            {hrefLabel}
          </Link>
        )}
      </div>
      {children}
    </section>
  );
}

export function DashboardPage() {
  const { items: saved } = useSavedEvents();
  const { items: viewed } = useRecentlyViewed();
  const { history } = useSearchHistory();
  const recs = useRecommendations(saved.map((s) => s.key), viewed.map((v) => v.key));

  const today = new Date().toISOString().slice(0, 10);
  const upcomingSaved = saved.filter((e) => (e.end_date ?? e.start_date) >= today);

  return (
    <div className="container space-y-10 py-8">
      <PageHeader
        title="Your Dashboard"
        description="Saved events, recommendations, and recent activity — stored on this device."
      />

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label="Saved" value={saved.length} icon={<BookmarkIcon className="h-5 w-5" />} />
        <StatCard label="Upcoming saved" value={upcomingSaved.length} />
        <StatCard
          label="Recently viewed"
          value={viewed.length}
          icon={<ClockIcon className="h-5 w-5" />}
        />
        <StatCard label="Searches" value={history.length} />
      </div>

      <DashSection title="Recommendations" href="/recommendations" hrefLabel="See all">
        {recs.status === "success" && recs.data && recs.data.length ? (
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {recs.data.slice(0, 3).map((r) => (
              <RecommendationCard key={r.event.key} rec={r} />
            ))}
          </div>
        ) : (
          <EmptyState
            title="No recommendations yet"
            message="Save events to get personalized picks."
            action={
              <Link href="/home" className={buttonClass("primary", "sm")}>
                Browse
              </Link>
            }
          />
        )}
      </DashSection>

      <DashSection title="Upcoming saved events" href="/saved" hrefLabel="All saved">
        {upcomingSaved.length ? (
          <EventList events={upcomingSaved.slice(0, 6)} />
        ) : (
          <EmptyState title="Nothing saved yet" message="Tap the bookmark on any event to save it." />
        )}
      </DashSection>

      <DashSection title="Recently viewed">
        {viewed.length ? (
          <EventList events={viewed.slice(0, 6)} />
        ) : (
          <EmptyState title="No history yet" message="Events you open will show up here." />
        )}
      </DashSection>

      <DashSection title="Recent searches" href="/history" hrefLabel="Search history">
        {history.length ? (
          <div className="flex flex-wrap gap-2">
            {history.map((h) => (
              <Link
                key={h}
                href={`/search?q=${encodeURIComponent(h)}`}
                className="rounded-full bg-surface-2 px-3 py-1.5 text-sm text-muted transition-colors hover:text-ink"
              >
                {h}
              </Link>
            ))}
          </div>
        ) : (
          <EmptyState title="No searches yet" message="Your recent searches will appear here." />
        )}
      </DashSection>
    </div>
  );
}
