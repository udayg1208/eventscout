"use client";

import { useState } from "react";

import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { EventList } from "@/components/EventList";
import { ExampleChips } from "@/components/ExampleChips";
import { Header } from "@/components/Header";
import { QueryUnderstanding } from "@/components/QueryUnderstanding";
import { SearchBar } from "@/components/SearchBar";
import { SearchHistory } from "@/components/SearchHistory";
import { SkeletonCard } from "@/components/SkeletonCard";
import { useSearch } from "@/hooks/useSearch";
import { useSearchHistory } from "@/hooks/useSearchHistory";

export default function Home() {
  const [input, setInput] = useState("");
  const { status, data, error, lastQuery, run } = useSearch();
  const { history, add, clear } = useSearchHistory();

  function doSearch(query: string) {
    const trimmed = query.trim();
    if (!trimmed) return;
    setInput(query);
    run(trimmed);
    add(trimmed);
  }

  return (
    <div className="min-h-screen">
      <Header />

      <main className="mx-auto max-w-6xl px-4 pb-24">
        <section className="pb-8 pt-10 text-center sm:pt-16">
          <h1 className="mx-auto max-w-2xl text-3xl font-extrabold tracking-tight sm:text-4xl">
            Discover tech &amp; professional events across India
          </h1>
          <p className="mx-auto mt-3 max-w-xl text-slate-500 dark:text-slate-400">
            Search workshops, meetups, conferences, hackathons and webinars in
            plain English.
          </p>

          <div className="mx-auto mt-8 max-w-2xl text-left">
            <SearchBar
              value={input}
              onChange={setInput}
              onSubmit={() => doSearch(input)}
              loading={status === "loading"}
            />
            <SearchHistory history={history} onPick={doSearch} onClear={clear} />
          </div>

          {status === "idle" && (
            <div className="mt-8">
              <ExampleChips onPick={doSearch} />
            </div>
          )}
        </section>

        <section aria-live="polite" aria-busy={status === "loading"}>
          {status === "loading" && (
            <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <SkeletonCard key={i} />
              ))}
            </ul>
          )}

          {status === "error" && error && (
            <ErrorState message={error} onRetry={() => run(lastQuery)} />
          )}

          {status === "success" && data && (
            <>
              <div className="mb-5 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-sm font-medium text-slate-600 dark:text-slate-300">
                  {data.count} {data.count === 1 ? "event" : "events"} for “
                  {lastQuery}”
                  {data.cached && (
                    <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-400 dark:bg-slate-800">
                      cached
                    </span>
                  )}
                </p>
                <QueryUnderstanding query={data.query} />
              </div>

              {data.count === 0 ? (
                <EmptyState query={lastQuery} />
              ) : (
                <EventList events={data.events} />
              )}
            </>
          )}
        </section>
      </main>

      <footer className="border-t border-slate-200 py-6 text-center text-xs text-slate-400 dark:border-slate-800">
        Event data from Confs.tech &amp; Devfolio · Built with Next.js
      </footer>
    </div>
  );
}
