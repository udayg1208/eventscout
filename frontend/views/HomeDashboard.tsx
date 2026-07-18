"use client";

import type { ReactNode } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Section } from "@/components/Section";
import { Skeleton, RowSkeleton } from "@/components/ui/Skeleton";
import { ErrorState } from "@/components/ui/States";
import {
  BoltIcon,
  ClockIcon,
  FireIcon,
  GlobeIcon,
  SparklesIcon,
  TicketIcon,
} from "@/components/ui/icons";
import { useSavedEvents, useRecentlyViewed, usePreferences } from "@/hooks/useLocalStorage";
import { useHomepage, useRecommendations } from "@/hooks/usePlatform";
import type { EventDTO } from "@/types/platform";
import { SECTION_LINK, SECTION_ORDER, SECTION_TITLE } from "@/utils/categories";

const ICON: Record<string, ReactNode> = {
  trending: <FireIcon className="h-5 w-5 text-orange-500" />,
  recommended: <SparklesIcon className="h-5 w-5 text-accent" />,
  ai_events: <BoltIcon className="h-5 w-5 text-violet-500" />,
  registration_closing: <ClockIcon className="h-5 w-5 text-amber-500" />,
  online_events: <GlobeIcon className="h-5 w-5 text-cyan-500" />,
  free_events: <TicketIcon className="h-5 w-5 text-emerald-500" />,
};

export function HomeDashboard() {
  const { prefs } = usePreferences();
  const { status, data, error, reload } = useHomepage(prefs.city || undefined);
  const { savedKeys } = useSavedEvents();
  const { items: viewed } = useRecentlyViewed();
  const recs = useRecommendations(savedKeys, viewed.map((v) => v.key));

  return (
    <div className="container space-y-10 py-8">
      <PageHeader
        title="Home"
        description="Your live feed of tech and professional events across India."
      />

      {status === "loading" && (
        <div className="space-y-10">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="space-y-3">
              <Skeleton className="h-6 w-44" />
              <RowSkeleton />
            </div>
          ))}
        </div>
      )}

      {status === "error" && <ErrorState message={error ?? undefined} onRetry={reload} />}

      {status === "success" && data && (
        <div className="space-y-10">
          {SECTION_ORDER.map((key) => {
            const events: EventDTO[] =
              key === "recommended"
                ? (recs.data ?? []).map((r) => r.event)
                : (data.sections[key] ?? []);
            if (!events.length) return null;
            return (
              <Section
                key={key}
                title={SECTION_TITLE[key] ?? key}
                events={events}
                viewAllHref={SECTION_LINK[key]}
                icon={ICON[key]}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}
