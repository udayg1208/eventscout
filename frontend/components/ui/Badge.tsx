import type { ReactNode } from "react";

import type { EventCategory } from "@/types/platform";
import { cn } from "@/utils/cn";
import {
  CATEGORY_CLASS,
  CATEGORY_LABEL,
  DIFFICULTY_CLASS,
  LIFECYCLE,
  providerLabel,
} from "@/utils/categories";

import { GlobeIcon } from "./icons";

export function Badge({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium",
        className,
      )}
    >
      {children}
    </span>
  );
}

export function CategoryBadge({ category }: { category: EventCategory }) {
  return <Badge className={CATEGORY_CLASS[category]}>{CATEGORY_LABEL[category]}</Badge>;
}

export function DifficultyBadge({ difficulty }: { difficulty: string }) {
  return (
    <Badge className={DIFFICULTY_CLASS[difficulty] ?? "bg-surface-2 text-muted"}>
      {difficulty}
    </Badge>
  );
}

export function LifecycleBadge({ lifecycle }: { lifecycle: string }) {
  const meta = LIFECYCLE[lifecycle];
  if (!meta) return null;
  return <Badge className={meta.class}>{meta.label}</Badge>;
}

export function PriceBadge({
  isFree,
  price,
}: {
  isFree: boolean | null;
  price: string | null;
}) {
  if (isFree === true)
    return (
      <Badge className="bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300">
        Free
      </Badge>
    );
  if (isFree === false)
    return (
      <Badge className="bg-surface-2 text-muted">{price ? price : "Paid"}</Badge>
    );
  return null;
}

export function FormatBadge({ isOnline }: { isOnline: boolean }) {
  if (!isOnline) return null;
  return (
    <Badge className="bg-cyan-100 text-cyan-700 dark:bg-cyan-500/15 dark:text-cyan-300">
      <GlobeIcon className="h-3 w-3" />
      Online
    </Badge>
  );
}

export function ProviderBadge({ provider }: { provider: string }) {
  return (
    <span className="text-xs font-medium text-faint">via {providerLabel(provider)}</span>
  );
}
