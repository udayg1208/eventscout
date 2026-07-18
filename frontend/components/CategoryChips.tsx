import Link from "next/link";

import { cn } from "@/utils/cn";
import { ALL_CATEGORIES, CATEGORY_CLASS, CATEGORY_LABEL } from "@/utils/categories";

/** Category pills linking to each category's listing page. */
export function CategoryChips({ className }: { className?: string }) {
  return (
    <div className={cn("flex flex-wrap gap-2", className)}>
      {ALL_CATEGORIES.map((c) => (
        <Link
          key={c}
          href={`/categories/${c}`}
          className={cn(
            "rounded-full px-3.5 py-1.5 text-sm font-medium transition-transform hover:scale-105",
            CATEGORY_CLASS[c],
          )}
        >
          {CATEGORY_LABEL[c]}
        </Link>
      ))}
    </div>
  );
}
