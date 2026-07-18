"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { CategoryChips } from "@/components/CategoryChips";
import { SearchBar } from "@/components/SearchBar";
import { Section } from "@/components/Section";
import { StatCard } from "@/components/StatCard";
import { buttonClass } from "@/components/ui/Button";
import { RowSkeleton, Skeleton } from "@/components/ui/Skeleton";
import { ArrowRightIcon, SparklesIcon, TrendingIcon } from "@/components/ui/icons";
import { useAnalytics, useFeed } from "@/hooks/usePlatform";

export function LandingPage() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const trending = useFeed({ kind: "discover", feed: "trending" });
  const analytics = useAnalytics();

  const submit = () => {
    const t = q.trim();
    router.push(t ? `/search?q=${encodeURIComponent(t)}` : "/search");
  };
  const a = analytics.data;

  return (
    <div>
      <section className="relative overflow-hidden border-b border-line">
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-accent-soft/50 to-transparent" />
        <div className="container relative py-16 text-center sm:py-24">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-3 py-1 text-xs font-medium text-muted">
            <SparklesIcon className="h-3.5 w-3.5 text-accent" />
            AI-powered event discovery
          </span>
          <h1 className="mx-auto mt-5 max-w-3xl text-4xl font-bold tracking-tight text-ink sm:text-5xl">
            Every tech event in India, in one place.
          </h1>
          <p className="mx-auto mt-4 max-w-xl text-lg text-muted">
            Search naturally, browse by topic or city, and get recommendations across
            conferences, hackathons, meetups, and AI events.
          </p>
          <div className="mx-auto mt-8 max-w-2xl">
            <SearchBar
              value={q}
              onChange={setQ}
              onSubmit={submit}
              size="lg"
              placeholder="Try “AI workshops in Bangalore this weekend”"
            />
          </div>
          <div className="mt-5 flex flex-wrap items-center justify-center gap-3">
            <Link href="/home" className={buttonClass("primary", "md")}>
              Explore events
              <ArrowRightIcon className="h-4 w-4" />
            </Link>
            <Link href="/browse" className={buttonClass("outline", "md")}>
              Browse all
            </Link>
          </div>
          <div className="mt-8">
            <CategoryChips className="justify-center" />
          </div>
        </div>
      </section>

      {analytics.status === "success" && a && (
        <section className="container py-12">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <StatCard label="Events" value={a.total_events} />
            <StatCard label="Cities" value={a.cities} />
            <StatCard label="Communities" value={a.communities} />
            <StatCard label="Sources" value={a.providers} />
          </div>
        </section>
      )}

      <section className="container pb-4">
        {trending.status === "loading" && (
          <div className="space-y-3">
            <Skeleton className="h-6 w-40" />
            <RowSkeleton />
          </div>
        )}
        {trending.status === "success" && (
          <Section
            title="Trending now"
            events={trending.data ?? []}
            viewAllHref="/trending"
            icon={<TrendingIcon className="h-5 w-5 text-accent" />}
          />
        )}
      </section>
    </div>
  );
}
