import type { AIMetadataDTO } from "@/types/platform";

import { DifficultyBadge } from "./ui/Badge";
import { Card } from "./ui/Card";
import { SparklesIcon } from "./ui/icons";

function TagRow({ label, items }: { label: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <div>
      <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-faint">
        {label}
      </p>
      <div className="flex flex-wrap gap-1.5">
        {items.map((t) => (
          <span
            key={t}
            className="rounded-md bg-surface-2 px-2 py-0.5 text-xs font-medium text-ink"
          >
            {t}
          </span>
        ))}
      </div>
    </div>
  );
}

/** The AI understanding (Phase 5A enrichment) for an event. */
export function AIMetadataPanel({ ai }: { ai: AIMetadataDTO }) {
  return (
    <Card className="p-6">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-ink">
        <SparklesIcon className="h-4 w-4 text-accent" />
        AI Understanding
      </h3>
      {ai.summary && (
        <p className="mt-3 text-sm leading-relaxed text-muted">{ai.summary}</p>
      )}
      <div className="mt-5 space-y-4">
        <TagRow label="Topics" items={ai.topics} />
        <TagRow label="Technologies" items={ai.technologies} />
        <TagRow label="Skills" items={ai.skills} />
        <TagRow label="Audience" items={ai.audiences} />
        <TagRow label="Careers" items={ai.careers} />
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium uppercase tracking-wide text-faint">
            Difficulty
          </span>
          <DifficultyBadge difficulty={ai.difficulty} />
        </div>
      </div>
    </Card>
  );
}
