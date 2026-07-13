import { ThemeToggle } from "@/components/ThemeToggle";

export function Header() {
  return (
    <header className="sticky top-0 z-10 border-b border-slate-200 bg-slate-50/80 backdrop-blur dark:border-slate-800 dark:bg-slate-950/80">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
        <span className="flex items-center gap-2 text-lg font-bold tracking-tight">
          <span aria-hidden="true">🎟️</span>
          EventScout <span className="text-violet-600 dark:text-violet-400">India</span>
        </span>
        <ThemeToggle />
      </div>
    </header>
  );
}
