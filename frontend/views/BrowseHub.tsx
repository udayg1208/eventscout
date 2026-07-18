import Link from "next/link";
import type { ReactNode } from "react";

import { CategoryChips } from "@/components/CategoryChips";
import { PageHeader } from "@/components/PageHeader";
import { ArrowRightIcon, BuildingIcon, MapIcon, UsersIcon } from "@/components/ui/icons";
import { BROWSE_DIMENSIONS } from "@/utils/feeds";

function BrowseLink({
  href,
  icon,
  title,
  desc,
}: {
  href: string;
  icon: ReactNode;
  title: string;
  desc: string;
}) {
  return (
    <Link
      href={href}
      className="group flex items-center gap-4 rounded-2xl border border-line bg-surface p-5 transition-all hover:-translate-y-0.5 hover:border-line-strong hover:shadow-soft"
    >
      <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-accent-soft text-accent">
        {icon}
      </span>
      <div className="flex-1">
        <p className="font-semibold text-ink transition-colors group-hover:text-accent">{title}</p>
        <p className="text-xs text-muted">{desc}</p>
      </div>
      <ArrowRightIcon className="h-4 w-4 text-faint" />
    </Link>
  );
}

export function BrowseHub() {
  return (
    <div className="container space-y-10 py-8">
      <PageHeader
        title="Browse"
        description="Explore events by category, topic, technology, city, community, and more."
      />

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-faint">
          Categories
        </h2>
        <CategoryChips />
      </section>

      {BROWSE_DIMENSIONS.map((dim) => (
        <section key={dim.dimension}>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-faint">
            {dim.title}
          </h2>
          <div className="flex flex-wrap gap-2">
            {dim.examples.map((ex) => (
              <Link
                key={ex}
                href={`/browse/${dim.dimension}/${encodeURIComponent(ex)}`}
                className="rounded-full border border-line bg-surface px-3.5 py-1.5 text-sm text-muted transition-colors hover:border-line-strong hover:text-ink"
              >
                {ex}
              </Link>
            ))}
          </div>
        </section>
      ))}

      <section className="grid gap-4 sm:grid-cols-3">
        <BrowseLink
          href="/communities"
          icon={<UsersIcon className="h-5 w-5" />}
          title="Communities"
          desc="GDG, FOSS United, Hasgeek…"
        />
        <BrowseLink
          href="/organizers"
          icon={<BuildingIcon className="h-5 w-5" />}
          title="Organizers"
          desc="Companies & organizations"
        />
        <BrowseLink
          href="/cities"
          icon={<MapIcon className="h-5 w-5" />}
          title="Cities"
          desc="Bangalore, Delhi, Mumbai…"
        />
      </section>
    </div>
  );
}
