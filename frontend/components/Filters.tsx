"use client";

import type { EventCategory, EventDTO } from "@/types/platform";
import { cn } from "@/utils/cn";
import { ALL_CATEGORIES, CATEGORY_CLASS, CATEGORY_LABEL } from "@/utils/categories";

export type SortKey = "soonest" | "newest" | "az";

export interface FilterState {
  categories: EventCategory[];
  format: "all" | "online" | "offline";
  free: boolean;
  sort: SortKey;
}

export const DEFAULT_FILTERS: FilterState = {
  categories: [],
  format: "all",
  free: false,
  sort: "soonest",
};

/** Pure client-side filter + sort applied to an already-fetched list. */
export function applyFilters(events: EventDTO[], f: FilterState): EventDTO[] {
  const filtered = events.filter(
    (e) =>
      (f.categories.length === 0 || f.categories.includes(e.category)) &&
      (f.format === "all" || (f.format === "online") === e.is_online) &&
      (!f.free || e.is_free === true),
  );
  const cmp =
    f.sort === "az"
      ? (a: EventDTO, b: EventDTO) => a.title.localeCompare(b.title)
      : f.sort === "newest"
        ? (a: EventDTO, b: EventDTO) => b.start_date.localeCompare(a.start_date)
        : (a: EventDTO, b: EventDTO) => a.start_date.localeCompare(b.start_date);
  return [...filtered].sort(cmp);
}

function Segmented<T extends string>({
  value,
  onChange,
  options,
}: {
  value: T;
  onChange: (v: T) => void;
  options: [T, string][];
}) {
  return (
    <div className="inline-flex rounded-lg border border-line bg-surface p-0.5">
      {options.map(([val, label]) => (
        <button
          key={val}
          type="button"
          onClick={() => onChange(val)}
          aria-pressed={value === val}
          className={cn(
            "rounded-md px-3 py-1 text-xs font-medium transition-colors",
            value === val ? "bg-accent text-accent-fg" : "text-muted hover:text-ink",
          )}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

export function Filters({
  value,
  onChange,
  resultCount,
}: {
  value: FilterState;
  onChange: (f: FilterState) => void;
  resultCount: number;
}) {
  const toggleCategory = (c: EventCategory) =>
    onChange({
      ...value,
      categories: value.categories.includes(c)
        ? value.categories.filter((x) => x !== c)
        : [...value.categories, c],
    });

  return (
    <div className="flex flex-col gap-4 rounded-2xl border border-line bg-surface p-4">
      <div className="flex flex-wrap items-center gap-2">
        {ALL_CATEGORIES.map((c) => {
          const active = value.categories.includes(c);
          return (
            <button
              key={c}
              type="button"
              onClick={() => toggleCategory(c)}
              aria-pressed={active}
              className={cn(
                "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                active
                  ? cn("border-transparent", CATEGORY_CLASS[c])
                  : "border-line text-muted hover:bg-surface-2",
              )}
            >
              {CATEGORY_LABEL[c]}
            </button>
          );
        })}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <Segmented
            value={value.format}
            onChange={(format) => onChange({ ...value, format })}
            options={[
              ["all", "All"],
              ["online", "Online"],
              ["offline", "In-person"],
            ]}
          />
          <label className="flex cursor-pointer items-center gap-2 text-sm text-muted">
            <input
              type="checkbox"
              checked={value.free}
              onChange={(e) => onChange({ ...value, free: e.target.checked })}
              className="h-4 w-4 accent-violet-600"
            />
            Free only
          </label>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-sm text-faint">{resultCount} events</span>
          <select
            value={value.sort}
            onChange={(e) => onChange({ ...value, sort: e.target.value as SortKey })}
            aria-label="Sort"
            className="h-9 rounded-lg border border-line bg-surface px-3 text-sm text-ink outline-none"
          >
            <option value="soonest">Soonest</option>
            <option value="newest">Newest</option>
            <option value="az">A–Z</option>
          </select>
        </div>
      </div>
    </div>
  );
}
