"use client";

import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { usePreferences } from "@/hooks/useLocalStorage";
import type { EventCategory } from "@/types/platform";
import { cn } from "@/utils/cn";
import { ALL_CATEGORIES, CATEGORY_CLASS, CATEGORY_LABEL } from "@/utils/categories";

export function PreferencesPage() {
  const { prefs, setPrefs } = usePreferences();

  const toggleCategory = (c: EventCategory) =>
    setPrefs({
      ...prefs,
      categories: prefs.categories.includes(c)
        ? prefs.categories.filter((x) => x !== c)
        : [...prefs.categories, c],
    });

  return (
    <div className="container max-w-2xl py-8">
      <PageHeader
        title="Preferences"
        description="Personalize your home feed. Saved on this device — no account needed."
      />

      <div className="space-y-6">
        <Card className="p-6">
          <label htmlFor="pref-city" className="block text-sm font-semibold text-ink">
            Default city
          </label>
          <p className="mb-3 text-sm text-muted">
            Powers the “Near You” section on your home feed.
          </p>
          <input
            id="pref-city"
            value={prefs.city}
            onChange={(e) => setPrefs({ ...prefs, city: e.target.value })}
            placeholder="e.g. Bangalore"
            className="h-11 w-full rounded-lg border border-line bg-surface px-3 text-ink outline-none transition-colors focus:border-accent"
          />
        </Card>

        <Card className="p-6">
          <p className="text-sm font-semibold text-ink">Favorite categories</p>
          <p className="mb-3 text-sm text-muted">Highlight the kinds of events you care about.</p>
          <div className="flex flex-wrap gap-2">
            {ALL_CATEGORIES.map((c) => {
              const active = prefs.categories.includes(c);
              return (
                <button
                  key={c}
                  type="button"
                  onClick={() => toggleCategory(c)}
                  aria-pressed={active}
                  className={cn(
                    "rounded-full border px-3 py-1 text-sm font-medium transition-colors",
                    active
                      ? cn("border-transparent", CATEGORY_CLASS[c])
                      : "border-line text-muted hover:bg-surface-2",
                  )}
                >
                  {CATEGORY_LABEL[c]}
                </button>
              );
            })}
          </div>
        </Card>

        <Card className="p-6">
          <p className="text-sm font-semibold text-ink">Format</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {(["all", "online", "offline"] as const).map((f) => (
              <button
                key={f}
                type="button"
                onClick={() => setPrefs({ ...prefs, format: f })}
                aria-pressed={prefs.format === f}
                className={cn(
                  "rounded-lg border px-3 py-1.5 text-sm",
                  prefs.format === f
                    ? "border-accent bg-accent text-accent-fg"
                    : "border-line text-muted hover:bg-surface-2",
                )}
              >
                {f === "offline" ? "In-person" : f === "all" ? "All" : "Online"}
              </button>
            ))}
          </div>
          <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm text-muted">
            <input
              type="checkbox"
              checked={prefs.freeOnly}
              onChange={(e) => setPrefs({ ...prefs, freeOnly: e.target.checked })}
              className="h-4 w-4 accent-violet-600"
            />
            Prefer free events
          </label>
        </Card>
      </div>
    </div>
  );
}
