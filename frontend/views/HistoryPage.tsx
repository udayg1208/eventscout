"use client";

import Link from "next/link";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/States";
import { SearchIcon } from "@/components/ui/icons";
import { useSearchHistory } from "@/hooks/useSearchHistory";

export function HistoryPage() {
  const { history, clear } = useSearchHistory();

  return (
    <div className="container py-8">
      <PageHeader
        title="Search History"
        description="Your recent searches on this device."
        actions={
          history.length > 0 ? (
            <Button variant="ghost" size="sm" onClick={clear}>
              Clear
            </Button>
          ) : undefined
        }
      />

      {history.length ? (
        <ul className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface">
          {history.map((h) => (
            <li key={h}>
              <Link
                href={`/search?q=${encodeURIComponent(h)}`}
                className="flex items-center gap-3 p-4 transition-colors hover:bg-surface-2"
              >
                <SearchIcon className="h-4 w-4 text-faint" />
                <span className="text-ink">{h}</span>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState
          title="No search history"
          message="Search for events and your history will appear here."
        />
      )}
    </div>
  );
}
