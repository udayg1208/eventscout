"use client";

import { cn } from "@/utils/cn";

import { buttonClass } from "./ui/Button";
import { CloseIcon, SearchIcon } from "./ui/icons";
import { Spinner } from "./ui/States";

export function SearchBar({
  value,
  onChange,
  onSubmit,
  loading = false,
  placeholder = "Search events…",
  autoFocus = false,
  size = "md",
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  loading?: boolean;
  placeholder?: string;
  autoFocus?: boolean;
  size?: "md" | "lg";
}) {
  return (
    <form
      role="search"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
      className="relative w-full"
    >
      <SearchIcon className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-faint" />
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoFocus={autoFocus}
        autoComplete="off"
        enterKeyHint="search"
        aria-label="Search events"
        className={cn(
          "w-full rounded-xl border border-line bg-surface pl-12 pr-32 text-ink shadow-sm outline-none transition-colors placeholder:text-faint focus:border-accent",
          size === "lg" ? "h-14 text-base" : "h-12 text-sm",
        )}
      />
      {value && (
        <button
          type="button"
          onClick={() => onChange("")}
          aria-label="Clear search"
          className="absolute right-[104px] top-1/2 -translate-y-1/2 rounded p-1 text-faint hover:text-ink"
        >
          <CloseIcon className="h-4 w-4" />
        </button>
      )}
      <button
        type="submit"
        disabled={loading}
        className={cn(
          buttonClass("primary", size === "lg" ? "md" : "sm"),
          "absolute right-2 top-1/2 -translate-y-1/2",
        )}
      >
        {loading ? <Spinner className="h-4 w-4 border-white/40 border-t-white" /> : "Search"}
      </button>
    </form>
  );
}
