"use client";

import { useEffect, useState } from "react";

import { EventCard } from "@/components/EventCard";
import { LoadMoreGrid } from "@/components/LoadMoreGrid";
import { PageHeader } from "@/components/PageHeader";
import { SearchBar } from "@/components/SearchBar";
import { GridSkeleton } from "@/components/ui/Skeleton";
import { EmptyState, ErrorState } from "@/components/ui/States";
import { useSearchHistory } from "@/hooks/useSearchHistory";
import { usePlatformSearch } from "@/hooks/usePlatformSearch";
import type { SearchQuery } from "@/types/platform";

const EXAMPLES = [
  "AI workshops in Bangalore",
  "free hackathons this month",
  "cloud conferences",
  "beginner python meetups",
  "startup events in Delhi",
];

function ParsedQuery({ query, count }: { query: SearchQuery; count: number }) {
  const chips: string[] = [];
  if (query.city) chips.push(`City: ${query.city}`);
  query.categories.forEach((c) => chips.push(c));
  if (query.free_only) chips.push("Free only");
  query.keywords.forEach((k) => chips.push(k));
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <span className="text-muted">
        {count} result{count === 1 ? "" : "s"}
      </span>
      {chips.length > 0 && <span className="text-faint">·</span>}
      {chips.map((c, i) => (
        <span
          key={i}
          className="rounded-full bg-surface-2 px-2.5 py-0.5 text-xs font-medium text-muted"
        >
          {c}
        </span>
      ))}
    </div>
  );
}

export function SearchPage({ initialQuery = "" }: { initialQuery?: string }) {
  const { status, data, error, run, lastQuery } = usePlatformSearch();
  const { history, add, clear } = useSearchHistory();
  const [input, setInput] = useState(initialQuery);

  const submit = (text?: string) => {
    const t = (text ?? input).trim();
    if (!t) return;
    if (text != null) setInput(text);
    run(t);
    add(t);
  };

  useEffect(() => {
    if (initialQuery) {
      setInput(initialQuery);
      run(initialQuery);
      add(initialQuery);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialQuery]);

  return (
    <div className="container py-8">
      <PageHeader
        title="AI Search"
        description="Describe what you're looking for in plain English — dates, cities, topics, and price all work."
      />

      <div className="mx-auto max-w-2xl">
        <SearchBar
          value={input}
          onChange={setInput}
          onSubmit={() => submit()}
          loading={status === "loading"}
          autoFocus
          placeholder="Try “free AI meetups in Bangalore this weekend”"
        />
      </div>

      {status === "idle" && (
        <div className="mx-auto mt-6 max-w-2xl">
          <p className="mb-2 text-sm text-muted">Try one of these:</p>
          <div className="flex flex-wrap gap-2">
            {EXAMPLES.map((ex) => (
              <button
                key={ex}
                onClick={() => submit(ex)}
                className="rounded-full border border-line bg-surface px-3 py-1.5 text-sm text-muted transition-colors hover:text-ink"
              >
                {ex}
              </button>
            ))}
          </div>
          {history.length > 0 && (
            <div className="mt-6">
              <div className="mb-2 flex items-center justify-between">
                <p className="text-sm text-muted">Recent searches</p>
                <button onClick={clear} className="text-xs text-faint hover:text-ink">
                  Clear
                </button>
              </div>
              <div className="flex flex-wrap gap-2">
                {history.map((h) => (
                  <button
                    key={h}
                    onClick={() => submit(h)}
                    className="rounded-full bg-surface-2 px-3 py-1.5 text-sm text-muted transition-colors hover:text-ink"
                  >
                    {h}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      <div className="mt-8">
        {status === "loading" && <GridSkeleton />}
        {status === "error" && (
          <ErrorState message={error ?? undefined} onRetry={() => submit(lastQuery)} />
        )}
        {status === "success" && data && (
          <div className="space-y-5">
            <ParsedQuery query={data.query} count={data.count} />
            {data.events.length === 0 ? (
              <EmptyState
                title="No matches"
                message={`Nothing found for “${lastQuery}”. Try broader terms.`}
              />
            ) : (
              <LoadMoreGrid
                items={data.events}
                keyOf={(e) => e.key}
                render={(e) => <EventCard event={e} />}
              />
            )}
          </div>
        )}
      </div>
    </div>
  );
}
