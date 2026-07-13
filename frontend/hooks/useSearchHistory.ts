"use client";

import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "eda:search-history";
const MAX_ITEMS = 8;

/** Local-only recent searches, persisted in localStorage. */
export function useSearchHistory() {
  const [history, setHistory] = useState<string[]>([]);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) setHistory(JSON.parse(raw));
    } catch {
      /* ignore malformed/absent storage */
    }
  }, []);

  const persist = useCallback((next: string[]) => {
    setHistory(next);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      /* storage may be unavailable (private mode) */
    }
  }, []);

  const add = useCallback(
    (query: string) => {
      const trimmed = query.trim();
      if (!trimmed) return;
      setHistory((prev) => {
        const next = [
          trimmed,
          ...prev.filter((q) => q.toLowerCase() !== trimmed.toLowerCase()),
        ].slice(0, MAX_ITEMS);
        try {
          localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
        } catch {
          /* ignore */
        }
        return next;
      });
    },
    [],
  );

  const clear = useCallback(() => persist([]), [persist]);

  return { history, add, clear };
}
