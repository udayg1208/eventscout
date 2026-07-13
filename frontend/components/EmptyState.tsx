export function EmptyState({ query }: { query: string }) {
  return (
    <div className="mx-auto max-w-md rounded-2xl border border-dashed border-slate-300 bg-white/50 p-10 text-center dark:border-slate-700 dark:bg-slate-900/40">
      <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-2xl dark:bg-slate-800">
        🔍
      </div>
      <h2 className="mb-1 text-lg font-semibold text-slate-900 dark:text-slate-100">
        No events found
      </h2>
      <p className="text-sm text-slate-500 dark:text-slate-400">
        We couldn&apos;t find events for{" "}
        <span className="font-medium text-slate-700 dark:text-slate-300">
          “{query}”
        </span>
        . Try a different city, category, or a broader search.
      </p>
    </div>
  );
}
