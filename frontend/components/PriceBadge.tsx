export function PriceBadge({
  isFree,
  price,
}: {
  isFree: boolean | null;
  price: string | null;
}) {
  if (isFree === true) {
    return (
      <span className="inline-flex items-center rounded-md bg-green-100 px-2 py-0.5 text-xs font-semibold text-green-700 dark:bg-green-500/15 dark:text-green-300">
        Free
      </span>
    );
  }
  if (isFree === false) {
    return (
      <span className="inline-flex items-center rounded-md bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-700 dark:bg-slate-800 dark:text-slate-300">
        {price ?? "Paid"}
      </span>
    );
  }
  // Unknown — the source didn't say. Stay honest, keep it muted.
  return (
    <span className="inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium text-slate-400 dark:text-slate-500">
      Price N/A
    </span>
  );
}
