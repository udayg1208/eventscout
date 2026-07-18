import type { ReactNode } from "react";

import { cn } from "@/utils/cn";

/** Surface container with a hairline border. `hover` adds a subtle lift. */
export function Card({
  children,
  className,
  hover = false,
}: {
  children: ReactNode;
  className?: string;
  hover?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-line bg-surface",
        hover &&
          "transition-all duration-200 hover:-translate-y-0.5 hover:border-line-strong hover:shadow-soft",
        className,
      )}
    >
      {children}
    </div>
  );
}
