"use client";

import { type FormEvent } from "react";

import { SearchIcon } from "@/components/icons";

export function SearchBar({
  value,
  onChange,
  onSubmit,
  loading,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  loading: boolean;
}) {
  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    onSubmit();
  }

  return (
    <form onSubmit={handleSubmit} role="search" className="relative">
      <label htmlFor="event-search" className="sr-only">
        Search for events
      </label>
      <SearchIcon className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
      <input
        id="event-search"
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Try “AI workshops in Bangalore this weekend”"
        autoComplete="off"
        enterKeyHint="search"
        className="w-full rounded-2xl border border-slate-300 bg-white py-4 pl-12 pr-28 text-base shadow-sm transition placeholder:text-slate-400 focus:border-violet-500 focus-visible:ring-2 focus-visible:ring-violet-500 dark:border-slate-700 dark:bg-slate-900 dark:placeholder:text-slate-500"
      />
      {value && (
        <button
          type="button"
          onClick={() => onChange("")}
          aria-label="Clear search"
          className="absolute right-24 top-1/2 -translate-y-1/2 rounded p-1 text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
        >
          ✕
        </button>
      )}
      <button
        type="submit"
        disabled={loading || !value.trim()}
        className="absolute right-2 top-1/2 -translate-y-1/2 rounded-xl bg-violet-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {loading ? "…" : "Search"}
      </button>
    </form>
  );
}
