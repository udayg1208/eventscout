import { sourceMeta } from "@/lib/styles";

export function SourceBadge({ provider }: { provider: string }) {
  const { label, className } = sourceMeta(provider);
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ${className}`}
      title={`Source: ${label}`}
    >
      {label}
    </span>
  );
}
