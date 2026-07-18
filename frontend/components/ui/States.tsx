import type { ReactNode } from "react";

import { cn } from "@/utils/cn";

import { Button } from "./Button";
import { CompassIcon } from "./icons";

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-block h-5 w-5 animate-spin rounded-full border-2 border-line-strong border-t-accent",
        className,
      )}
      aria-hidden="true"
    />
  );
}

export function EmptyState({
  title = "Nothing here yet",
  message,
  icon,
  action,
}: {
  title?: string;
  message?: string;
  icon?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-line bg-surface px-6 py-16 text-center">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-surface-2 text-muted">
        {icon ?? <CompassIcon className="h-6 w-6" />}
      </div>
      <h3 className="text-base font-semibold text-ink">{title}</h3>
      {message && <p className="mt-1 max-w-sm text-sm text-muted">{message}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function ErrorState({
  message = "Something went wrong.",
  onRetry,
}: {
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center justify-center rounded-2xl border border-rose-200 bg-rose-50 px-6 py-14 text-center dark:border-rose-500/20 dark:bg-rose-500/5"
    >
      <h3 className="text-base font-semibold text-rose-700 dark:text-rose-300">
        Couldn&apos;t load this
      </h3>
      <p className="mt-1 max-w-sm text-sm text-rose-600/90 dark:text-rose-300/80">
        {message}
      </p>
      {onRetry && (
        <Button variant="outline" size="sm" className="mt-5" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}
