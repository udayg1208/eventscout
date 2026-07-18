import type { RecommendationDTO } from "@/types/platform";

import { EventCard } from "./EventCard";
import { SparklesIcon } from "./ui/icons";

/** An event card annotated with the (deterministic) reasons it was recommended. */
export function RecommendationCard({ rec }: { rec: RecommendationDTO }) {
  return (
    <EventCard event={rec.event}>
      {rec.reasons.length > 0 && (
        <div className="mt-4 rounded-xl bg-accent-soft/60 p-3">
          <p className="flex items-center gap-1.5 text-xs font-semibold text-accent">
            <SparklesIcon className="h-3.5 w-3.5" />
            Why this
          </p>
          <ul className="mt-1.5 space-y-1">
            {rec.reasons.slice(0, 3).map((reason, i) => (
              <li key={i} className="text-xs leading-snug text-muted">
                {reason}
              </li>
            ))}
          </ul>
        </div>
      )}
    </EventCard>
  );
}
