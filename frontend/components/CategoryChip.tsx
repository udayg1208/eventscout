import { CATEGORY_CLASSES, CATEGORY_LABELS } from "@/lib/styles";
import type { EventCategory } from "@/lib/types";

export function CategoryChip({ category }: { category: EventCategory }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${CATEGORY_CLASSES[category]}`}
    >
      {CATEGORY_LABELS[category]}
    </span>
  );
}
