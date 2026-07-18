import { cn } from "@/utils/cn";

/** Shimmering placeholder block. */
export function Skeleton({ className }: { className?: string }) {
  return (
    <div className={cn("relative overflow-hidden rounded-md bg-surface-2", className)}>
      <span className="absolute inset-0 -translate-x-full animate-shimmer bg-gradient-to-r from-transparent via-black/[0.05] to-transparent dark:via-white/[0.06]" />
    </div>
  );
}

export function EventCardSkeleton() {
  return (
    <div className="rounded-2xl border border-line bg-surface p-5">
      <div className="flex items-center gap-2">
        <Skeleton className="h-5 w-16 rounded-full" />
        <Skeleton className="h-5 w-12 rounded-full" />
      </div>
      <Skeleton className="mt-4 h-5 w-4/5" />
      <Skeleton className="mt-2 h-5 w-3/5" />
      <Skeleton className="mt-4 h-4 w-1/2" />
      <Skeleton className="mt-2 h-4 w-2/5" />
      <Skeleton className="mt-5 h-9 w-full rounded-lg" />
    </div>
  );
}

export function GridSkeleton({ count = 6 }: { count?: number }) {
  return (
    <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: count }).map((_, i) => (
        <EventCardSkeleton key={i} />
      ))}
    </div>
  );
}

export function RowSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="flex gap-5 overflow-hidden">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="w-[300px] shrink-0">
          <EventCardSkeleton />
        </div>
      ))}
    </div>
  );
}
