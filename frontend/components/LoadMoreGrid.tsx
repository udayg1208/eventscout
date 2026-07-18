"use client";

import { useEffect, useState, type ReactNode } from "react";

import { Button } from "./ui/Button";
import { EmptyState } from "./ui/States";

/** A responsive grid with client-side "Load more" pagination. Generic over the
 * item type so it renders both event cards and recommendation cards. */
export function LoadMoreGrid<T>({
  items,
  keyOf,
  render,
  pageSize = 12,
  empty,
}: {
  items: T[];
  keyOf: (item: T) => string;
  render: (item: T) => ReactNode;
  pageSize?: number;
  empty?: ReactNode;
}) {
  const [visible, setVisible] = useState(pageSize);

  useEffect(() => setVisible(pageSize), [items, pageSize]);

  if (!items.length) {
    return <>{empty ?? <EmptyState message="Nothing here yet." />}</>;
  }

  const shown = items.slice(0, visible);
  const remaining = items.length - shown.length;

  return (
    <div>
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {shown.map((item) => (
          <div key={keyOf(item)}>{render(item)}</div>
        ))}
      </div>
      {remaining > 0 && (
        <div className="mt-8 flex justify-center">
          <Button variant="outline" onClick={() => setVisible((v) => v + pageSize)}>
            Load more ({remaining} more)
          </Button>
        </div>
      )}
    </div>
  );
}
