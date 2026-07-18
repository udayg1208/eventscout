import type { ReactNode } from "react";

import { formatNumber } from "@/utils/format";

import { Card } from "./ui/Card";

export function StatCard({
  label,
  value,
  icon,
}: {
  label: string;
  value: string | number;
  icon?: ReactNode;
}) {
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted">{label}</p>
        {icon && <span className="text-accent">{icon}</span>}
      </div>
      <p className="mt-2 text-3xl font-bold tracking-tight text-ink">
        {typeof value === "number" ? formatNumber(value) : value}
      </p>
    </Card>
  );
}
