"use client";

import { MoonIcon, SunIcon } from "@/components/icons";
import { useTheme } from "@/hooks/useTheme";

export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const isDark = theme === "dark";

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
      aria-pressed={isDark}
      className="rounded-lg border border-slate-200 bg-white p-2 text-slate-600 transition hover:text-violet-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300 dark:hover:text-violet-300"
    >
      {isDark ? <SunIcon className="h-5 w-5" /> : <MoonIcon className="h-5 w-5" />}
    </button>
  );
}
