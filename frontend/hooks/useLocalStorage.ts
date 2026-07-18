"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import type { EventCategory, EventDTO } from "@/types/platform";

/**
 * Persisted state via localStorage. There is no auth in EventScout, so the
 * user's saved events, recently-viewed, and preferences live entirely on the
 * client. Reads happen after mount (SSR-safe); `ready` flags when hydrated.
 */
export function useLocalStorage<T>(key: string, initial: T) {
  const [value, setValue] = useState<T>(initial);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(key);
      if (raw != null) setValue(JSON.parse(raw) as T);
    } catch {
      /* ignore corrupt/blocked storage */
    }
    setReady(true);
  }, [key]);

  useEffect(() => {
    if (!ready) return;
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      /* ignore quota/blocked storage */
    }
  }, [key, value, ready]);

  return [value, setValue, ready] as const;
}

export function useSavedEvents() {
  const [items, setItems, ready] = useLocalStorage<EventDTO[]>("eventscout:saved", []);
  const keys = useMemo(() => new Set(items.map((e) => e.key)), [items]);

  const isSaved = useCallback((key: string) => keys.has(key), [keys]);
  const toggle = useCallback(
    (event: EventDTO) =>
      setItems((prev) =>
        prev.some((e) => e.key === event.key)
          ? prev.filter((e) => e.key !== event.key)
          : [event, ...prev],
      ),
    [setItems],
  );
  const remove = useCallback(
    (key: string) => setItems((prev) => prev.filter((e) => e.key !== key)),
    [setItems],
  );
  const clear = useCallback(() => setItems([]), [setItems]);

  return { items, savedKeys: [...keys], isSaved, toggle, remove, clear, ready };
}

export function useRecentlyViewed() {
  const [items, setItems, ready] = useLocalStorage<EventDTO[]>("eventscout:viewed", []);
  const record = useCallback(
    (event: EventDTO) =>
      setItems((prev) => [event, ...prev.filter((e) => e.key !== event.key)].slice(0, 24)),
    [setItems],
  );
  const clear = useCallback(() => setItems([]), [setItems]);
  return { items, record, clear, ready };
}

export interface Preferences {
  city: string;
  categories: EventCategory[];
  format: "all" | "online" | "offline";
  freeOnly: boolean;
}

const DEFAULT_PREFS: Preferences = {
  city: "",
  categories: [],
  format: "all",
  freeOnly: false,
};

export function usePreferences() {
  const [prefs, setPrefs, ready] = useLocalStorage<Preferences>(
    "eventscout:prefs",
    DEFAULT_PREFS,
  );
  return { prefs, setPrefs, ready };
}
