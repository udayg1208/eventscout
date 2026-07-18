import Link from "next/link";

import { PageHeader } from "@/components/PageHeader";
import { cn } from "@/utils/cn";
import { ALL_CATEGORIES, CATEGORY_CLASS, CATEGORY_LABEL } from "@/utils/categories";

const BLURB: Record<string, string> = {
  ai: "AI, ML, LLMs & generative AI",
  hackathon: "Build in a weekend",
  conference: "Talks, tracks & networking",
  meetup: "Community gatherings",
  workshop: "Hands-on, learn by doing",
  startup: "Founders, pitches & demo days",
  webinar: "Learn from anywhere",
};

export function CategoriesPage() {
  return (
    <div className="container py-8">
      <PageHeader
        title="Categories"
        description="Every kind of tech event, grouped for easy discovery."
      />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {ALL_CATEGORIES.map((c) => (
          <Link
            key={c}
            href={`/categories/${c}`}
            className="group rounded-2xl border border-line bg-surface p-6 transition-all hover:-translate-y-0.5 hover:border-line-strong hover:shadow-soft"
          >
            <span
              className={cn(
                "inline-flex rounded-full px-3 py-1 text-sm font-semibold",
                CATEGORY_CLASS[c],
              )}
            >
              {CATEGORY_LABEL[c]}
            </span>
            <p className="mt-4 text-sm text-muted">{BLURB[c]}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
