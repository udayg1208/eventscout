"use client";

import type { ComponentType } from "react";

import { CityCard, CommunityCard, OrganizerCard } from "@/components/EntityCards";
import { PageHeader } from "@/components/PageHeader";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState, ErrorState } from "@/components/ui/States";
import { useDirectory } from "@/hooks/usePlatform";
import type { DirectoryDTO, Pair } from "@/types/platform";

type Kind = "communities" | "organizers" | "cities";

const CFG: Record<
  Kind,
  {
    title: string;
    description: string;
    pick: (d: DirectoryDTO) => Pair[];
    Card: ComponentType<{ name: string; count?: number }>;
  }
> = {
  communities: {
    title: "Communities",
    description: "Developer communities hosting events across India.",
    pick: (d) => d.communities,
    Card: CommunityCard,
  },
  organizers: {
    title: "Organizers",
    description: "Companies and organizations running events.",
    pick: (d) => d.organizers,
    Card: OrganizerCard,
  },
  cities: {
    title: "Cities",
    description: "Explore the tech-event scene city by city.",
    pick: (d) => d.cities,
    Card: CityCard,
  },
};

export function EntityIndexPage({ kind }: { kind: Kind }) {
  const { status, data, error, reload } = useDirectory();
  const cfg = CFG[kind];
  const rows = data ? cfg.pick(data) : [];
  const Card = cfg.Card;

  return (
    <div className="container py-8">
      <PageHeader title={cfg.title} description={cfg.description} />

      {status === "loading" && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 9 }).map((_, i) => (
            <Skeleton key={i} className="h-[76px] rounded-2xl" />
          ))}
        </div>
      )}
      {status === "error" && <ErrorState message={error ?? undefined} onRetry={reload} />}
      {status === "success" &&
        (rows.length ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {rows.map(([name, count]) => (
              <Card key={name} name={name} count={count} />
            ))}
          </div>
        ) : (
          <EmptyState
            title="Nothing here yet"
            message="The catalog has no entries here. Seed the catalog and refresh."
          />
        ))}
    </div>
  );
}
