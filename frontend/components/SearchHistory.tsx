"use client";

export function SearchHistory({
  history,
  onPick,
  onClear,
}: {
  history: string[];
  onPick: (q: string) => void;
  onClear: () => void;
}) {
  if (history.length === 0) return null;

  return (
    <div className="mt-4">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-slate-400">
          Recent searches
        </span>
        <button
          type="button"
          onClick={onClear}
          className="text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
        >
          Clear
        </button>
      </div>
      <div className="flex flex-wrap gap-2">
        {history.map((query) => (
          <button
            key={query}
            type="button"
            onClick={() => onPick(query)}
            className="max-w-full truncate rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-600 transition hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
          >
            {query}
          </button>
        ))}
      </div>
    </div>
  );
}
