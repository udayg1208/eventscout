/** Loading placeholder matching EventCard's shape. */
export function SkeletonCard() {
  return (
    <li
      className="flex flex-col rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900"
      aria-hidden="true"
    >
      <div className="mb-3 flex justify-between">
        <div className="h-5 w-20 animate-pulse rounded-full bg-slate-200 dark:bg-slate-800" />
        <div className="h-5 w-16 animate-pulse rounded-md bg-slate-200 dark:bg-slate-800" />
      </div>
      <div className="mb-3 h-5 w-3/4 animate-pulse rounded bg-slate-200 dark:bg-slate-800" />
      <div className="mb-2 h-4 w-1/2 animate-pulse rounded bg-slate-200 dark:bg-slate-800" />
      <div className="mb-4 h-4 w-2/5 animate-pulse rounded bg-slate-200 dark:bg-slate-800" />
      <div className="mt-auto flex items-center justify-between pt-2">
        <div className="h-5 w-12 animate-pulse rounded bg-slate-200 dark:bg-slate-800" />
        <div className="h-8 w-24 animate-pulse rounded-lg bg-slate-200 dark:bg-slate-800" />
      </div>
    </li>
  );
}
