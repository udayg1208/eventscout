"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { useSavedEvents } from "@/hooks/useLocalStorage";
import { cn } from "@/utils/cn";

import { ThemeToggle } from "./ThemeToggle";
import { BookmarkIcon, CloseIcon, CompassIcon, MenuIcon } from "./ui/icons";

const NAV = [
  { href: "/home", label: "Home" },
  { href: "/search", label: "Search" },
  { href: "/browse", label: "Browse" },
  { href: "/trending", label: "Trending" },
  { href: "/recommendations", label: "For You" },
];

export function Navbar() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const { savedKeys, ready } = useSavedEvents();

  const isActive = (href: string) =>
    pathname === href || (href !== "/home" && pathname.startsWith(href));

  return (
    <header className="sticky top-0 z-40 border-b border-line bg-bg/80 backdrop-blur">
      <div className="container flex h-16 items-center justify-between gap-4">
        <Link href="/" className="flex shrink-0 items-center gap-2 font-bold text-ink">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent text-accent-fg">
            <CompassIcon className="h-5 w-5" />
          </span>
          <span className="text-lg tracking-tight">EventScout</span>
        </Link>

        <nav className="hidden items-center gap-1 md:flex">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                isActive(item.href) ? "bg-surface-2 text-ink" : "text-muted hover:text-ink",
              )}
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <Link
            href="/saved"
            aria-label="Saved events"
            className="relative inline-flex h-9 w-9 items-center justify-center rounded-lg border border-line bg-surface text-muted transition-colors hover:text-ink"
          >
            <BookmarkIcon className="h-5 w-5" />
            {ready && savedKeys.length > 0 && (
              <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-accent px-1 text-[10px] font-semibold text-accent-fg">
                {savedKeys.length}
              </span>
            )}
          </Link>
          <ThemeToggle />
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            aria-label="Toggle menu"
            aria-expanded={open}
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-line bg-surface text-muted md:hidden"
          >
            {open ? <CloseIcon className="h-5 w-5" /> : <MenuIcon className="h-5 w-5" />}
          </button>
        </div>
      </div>

      {open && (
        <nav className="border-t border-line bg-surface md:hidden">
          <div className="container flex flex-col py-2">
            {[...NAV, { href: "/dashboard", label: "Dashboard" }, { href: "/saved", label: "Saved" }].map(
              (item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setOpen(false)}
                  className={cn(
                    "rounded-lg px-3 py-2.5 text-sm font-medium",
                    isActive(item.href) ? "bg-surface-2 text-ink" : "text-muted",
                  )}
                >
                  {item.label}
                </Link>
              ),
            )}
          </div>
        </nav>
      )}
    </header>
  );
}
