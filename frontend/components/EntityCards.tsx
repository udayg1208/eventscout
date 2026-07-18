import Link from "next/link";
import type { ReactNode } from "react";

import { ArrowRightIcon, BuildingIcon, LayersIcon, MapIcon, UsersIcon } from "./ui/icons";

function EntityCard({
  href,
  icon,
  name,
  kind,
  count,
}: {
  href: string;
  icon: ReactNode;
  name: string;
  kind: string;
  count?: number;
}) {
  return (
    <Link
      href={href}
      className="group flex items-center gap-4 rounded-2xl border border-line bg-surface p-4 transition-all hover:-translate-y-0.5 hover:border-line-strong hover:shadow-soft"
    >
      <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-accent-soft text-accent">
        {icon}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate font-semibold text-ink transition-colors group-hover:text-accent">
          {name}
        </p>
        <p className="text-xs text-muted">
          {kind}
          {count != null && ` · ${count} events`}
        </p>
      </div>
      <ArrowRightIcon className="h-4 w-4 shrink-0 text-faint" />
    </Link>
  );
}

const enc = encodeURIComponent;

export function CommunityCard({ name, count }: { name: string; count?: number }) {
  return (
    <EntityCard
      href={`/communities/${enc(name)}`}
      icon={<UsersIcon className="h-5 w-5" />}
      name={name}
      kind="Community"
      count={count}
    />
  );
}

export function OrganizerCard({ name, count }: { name: string; count?: number }) {
  return (
    <EntityCard
      href={`/organizers/${enc(name)}`}
      icon={<BuildingIcon className="h-5 w-5" />}
      name={name}
      kind="Organizer"
      count={count}
    />
  );
}

export function CityCard({ name, count }: { name: string; count?: number }) {
  return (
    <EntityCard
      href={`/cities/${enc(name)}`}
      icon={<MapIcon className="h-5 w-5" />}
      name={name}
      kind="City"
      count={count}
    />
  );
}

export function SeriesCard({ name, count }: { name: string; count?: number }) {
  return (
    <EntityCard
      href={`/browse/series/${enc(name)}`}
      icon={<LayersIcon className="h-5 w-5" />}
      name={name}
      kind="Series"
      count={count}
    />
  );
}
