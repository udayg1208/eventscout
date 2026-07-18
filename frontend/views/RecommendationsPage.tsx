"use client";

import Link from "next/link";

import { LoadMoreGrid } from "@/components/LoadMoreGrid";
import { PageHeader } from "@/components/PageHeader";
import { RecommendationCard } from "@/components/RecommendationCard";
import { Section } from "@/components/Section";
import { buttonClass } from "@/components/ui/Button";
import { GridSkeleton } from "@/components/ui/Skeleton";
import { EmptyState, ErrorState } from "@/components/ui/States";
import { SparklesIcon, TrendingIcon } from "@/components/ui/icons";
import { useRecentlyViewed, useSavedEvents } from "@/hooks/useLocalStorage";
import { useFeed, useRecommendations } from "@/hooks/usePlatform";

export function RecommendationsPage() {
  const { savedKeys, ready: sReady } = useSavedEvents();
  const { items: viewed, ready: vReady } = useRecentlyViewed();
  const ready = sReady && vReady;
  const hasSeeds = savedKeys.length > 0 || viewed.length > 0;
  const recs = useRecommendations(savedKeys, viewed.map((v) => v.key));
  const trending = useFeed({ kind: "discover", feed: "trending" });

  return (
    <div className="container py-8">
      <PageHeader
        title="Recommended For You"
        description="Personalized from the events you save and view — with the reason for every pick."
        icon={<SparklesIcon className="h-6 w-6 text-accent" />}
      />

      {!ready ? (
        <GridSkeleton />
      ) : !hasSeeds ? (
        <div className="space-y-10">
          <EmptyState
            title="Save a few events to get started"
            message="Recommendations are built from what you save and view — no account needed. Save some events and your picks appear here."
            icon={<SparklesIcon className="h-6 w-6" />}
            action={
              <Link href="/home" className={buttonClass("primary", "md")}>
                Browse events
              </Link>
            }
          />
          {trending.status === "success" && (
            <Section
              title="Trending now"
              events={trending.data ?? []}
              viewAllHref="/trending"
              icon={<TrendingIcon className="h-5 w-5 text-accent" />}
            />
          )}
        </div>
      ) : recs.status === "loading" ? (
        <GridSkeleton />
      ) : recs.status === "error" ? (
        <ErrorState message={recs.error ?? undefined} onRetry={recs.reload} />
      ) : recs.data && recs.data.length ? (
        <LoadMoreGrid
          items={recs.data}
          keyOf={(r) => r.event.key}
          render={(r) => <RecommendationCard rec={r} />}
        />
      ) : (
        <EmptyState
          title="No recommendations yet"
          message="Save or view a few more events to improve your picks."
        />
      )}
    </div>
  );
}
