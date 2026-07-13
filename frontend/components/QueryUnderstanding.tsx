import { CATEGORY_LABELS } from "@/lib/styles";
import type { SearchQuery } from "@/lib/types";

/** Shows how the backend interpreted the natural-language query. */
export function QueryUnderstanding({ query }: { query: SearchQuery }) {
  const chips: string[] = [];
  if (query.city) chips.push(`📍 ${query.city}`);
  for (const category of query.categories) chips.push(CATEGORY_LABELS[category]);
  if (query.free_only) chips.push("Free only");
  if (query.date_from || query.date_to) {
    chips.push(`🗓 ${query.date_from ?? "…"} → ${query.date_to ?? "…"}`);
  }
  for (const keyword of query.keywords) chips.push(`“${keyword}”`);

  if (chips.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <span className="text-slate-400">Understood as</span>
      {chips.map((chip) => (
        <span
          key={chip}
          className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300"
        >
          {chip}
        </span>
      ))}
    </div>
  );
}
