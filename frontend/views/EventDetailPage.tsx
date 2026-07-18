"use client";

import { useEffect, useState } from "react";

import { AIMetadataPanel } from "@/components/AIMetadataPanel";
import { CommunityCard, CityCard, OrganizerCard } from "@/components/EntityCards";
import { EventGrid } from "@/components/EventGrid";
import { Breadcrumbs } from "@/components/PageHeader";
import { SaveButton } from "@/components/SaveButton";
import { ShareButton } from "@/components/ShareButton";
import {
  CategoryBadge,
  FormatBadge,
  LifecycleBadge,
  PriceBadge,
  ProviderBadge,
} from "@/components/ui/Badge";
import { buttonClass } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState, ErrorState } from "@/components/ui/States";
import { CalendarIcon, ExternalIcon, PinIcon, TrendingIcon } from "@/components/ui/icons";
import { useRecentlyViewed } from "@/hooks/useLocalStorage";
import { useEvent } from "@/hooks/usePlatform";
import { formatEventDate, formatWeekday, formatWhere } from "@/utils/format";

export function EventDetailPage({ eventKey }: { eventKey: string }) {
  const { status, data, error, reload } = useEvent(eventKey);
  const { record } = useRecentlyViewed();
  const [shareUrl, setShareUrl] = useState("");

  useEffect(() => setShareUrl(window.location.href), []);
  useEffect(() => {
    if (data?.event) record(data.event);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data?.event?.key]);

  if (status === "loading") {
    return (
      <div className="container space-y-4 py-8">
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="h-5 w-1/3" />
        <Skeleton className="h-40 w-full rounded-2xl" />
      </div>
    );
  }
  if (status === "error") {
    return (
      <div className="container py-8">
        <ErrorState message={error ?? undefined} onRetry={reload} />
      </div>
    );
  }
  if (!data) return null;

  const { event, ai, lifecycle, trending_score, similar, organizer, community, city } = data;

  return (
    <div className="container py-8">
      <Breadcrumbs
        trail={[
          { label: "Home", href: "/" },
          { label: "Events", href: "/home" },
          { label: event.title },
        ]}
      />

      <Card className="p-6 sm:p-8">
        <div className="flex flex-wrap items-center gap-2">
          <CategoryBadge category={event.category} />
          <LifecycleBadge lifecycle={lifecycle} />
          <FormatBadge isOnline={event.is_online} />
          <PriceBadge isFree={event.is_free} price={event.price} />
        </div>

        <h1 className="mt-4 text-2xl font-bold tracking-tight text-ink sm:text-3xl">
          {event.title}
        </h1>

        <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-muted">
          <span className="flex items-center gap-2">
            <CalendarIcon className="h-4 w-4 text-faint" />
            {formatWeekday(event.start_date)}, {formatEventDate(event.start_date, event.end_date)}
          </span>
          <span className="flex items-center gap-2">
            <PinIcon className="h-4 w-4 text-faint" />
            {formatWhere(event.city, event.is_online)}
          </span>
          <ProviderBadge provider={event.provider} />
        </div>

        <div className="mt-6 flex flex-wrap items-center gap-2">
          <a
            href={event.url}
            target="_blank"
            rel="noopener noreferrer"
            className={buttonClass("primary", "md")}
          >
            Register
            <ExternalIcon className="h-4 w-4" />
          </a>
          <SaveButton
            event={event}
            showLabel
            className="border border-line bg-surface px-4 py-2"
          />
          {shareUrl && <ShareButton title={event.title} url={shareUrl} />}
        </div>
      </Card>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {event.description && (
            <Card className="p-6">
              <h2 className="text-sm font-semibold text-ink">About this event</h2>
              <p className="mt-3 whitespace-pre-line text-sm leading-relaxed text-muted">
                {event.description}
              </p>
            </Card>
          )}
          {ai && <AIMetadataPanel ai={ai} />}

          <div>
            <h2 className="mb-4 text-lg font-semibold text-ink">Similar events</h2>
            <EventGrid
              events={similar}
              empty={<EmptyState title="No similar events" message="Nothing closely related yet." />}
            />
          </div>
        </div>

        <aside className="space-y-4">
          <Card className="p-5">
            <h3 className="text-sm font-semibold text-ink">Quick facts</h3>
            <dl className="mt-3 space-y-2 text-sm">
              <Fact label="Format" value={event.is_online ? "Online" : "In-person"} />
              <Fact label="City" value={event.city ?? "—"} />
              <Fact
                label="Price"
                value={event.is_free ? "Free" : (event.price ?? "See site")}
              />
              <Fact
                label="Momentum"
                value={
                  <span className="inline-flex items-center gap-1">
                    <TrendingIcon className="h-3.5 w-3.5 text-accent" />
                    {trending_score.toFixed(2)}
                  </span>
                }
              />
            </dl>
          </Card>

          {(organizer || community || city) && (
            <div className="space-y-3">
              {organizer && (
                <OrganizerCard name={organizer.name} count={organizer.total_events} />
              )}
              {community && (
                <CommunityCard name={community.name} count={community.total_events} />
              )}
              {city && <CityCard name={city.name} count={city.total_events} />}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <dt className="text-faint">{label}</dt>
      <dd className="text-right font-medium text-ink">{value}</dd>
    </div>
  );
}
