import Link from "next/link";
import type { ReactNode } from "react";

import { ChevronRightIcon } from "./ui/icons";

export function Breadcrumbs({
  trail,
}: {
  trail: { label: string; href?: string }[];
}) {
  return (
    <nav aria-label="Breadcrumb" className="mb-4">
      <ol className="flex flex-wrap items-center gap-1 text-sm text-muted">
        {trail.map((item, i) => (
          <li key={i} className="flex items-center gap-1">
            {item.href ? (
              <Link href={item.href} className="hover:text-ink">
                {item.label}
              </Link>
            ) : (
              <span className="text-ink">{item.label}</span>
            )}
            {i < trail.length - 1 && <ChevronRightIcon className="h-3.5 w-3.5 text-faint" />}
          </li>
        ))}
      </ol>
    </nav>
  );
}

export function PageHeader({
  title,
  description,
  icon,
  actions,
  breadcrumb,
  count,
}: {
  title: string;
  description?: string;
  icon?: ReactNode;
  actions?: ReactNode;
  breadcrumb?: ReactNode;
  count?: number;
}) {
  return (
    <div className="mb-8">
      {breadcrumb}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="flex items-center gap-2.5 text-2xl font-bold tracking-tight text-ink sm:text-3xl">
            {icon}
            {title}
          </h1>
          {count !== undefined && (
            <p className="mt-1 text-sm font-semibold text-accent">
              {count.toLocaleString()} {count === 1 ? "event" : "events"}
            </p>
          )}
          {description && <p className="mt-2 max-w-2xl text-muted">{description}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </div>
  );
}
