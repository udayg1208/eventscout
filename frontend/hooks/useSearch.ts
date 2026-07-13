"use client";

import { useCallback, useRef, useState } from "react";

import { ApiError, searchEvents } from "@/lib/api";
import type { SearchResponse } from "@/lib/types";

export type SearchStatus = "idle" | "loading" | "success" | "error";

export interface UseSearch {
  status: SearchStatus;
  data: SearchResponse | null;
  error: string | null;
  lastQuery: string;
  run: (query: string) => void;
}

/**
 * Owns search lifecycle state. Aborts any in-flight request when a newer search
 * starts, so results never arrive out of order.
 */
export function useSearch(): UseSearch {
  const [status, setStatus] = useState<SearchStatus>("idle");
  const [data, setData] = useState<SearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastQuery, setLastQuery] = useState("");
  const controllerRef = useRef<AbortController | null>(null);

  const run = useCallback((query: string) => {
    const trimmed = query.trim();
    if (!trimmed) return;

    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;

    setStatus("loading");
    setError(null);
    setLastQuery(trimmed);

    searchEvents(trimmed, controller.signal)
      .then((response) => {
        if (controller.signal.aborted) return;
        setData(response);
        setStatus("success");
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted || (err as Error).name === "AbortError") {
          return;
        }
        setError(
          err instanceof ApiError
            ? err.message
            : "Something went wrong. Please try again.",
        );
        setStatus("error");
      });
  }, []);

  return { status, data, error, lastQuery, run };
}
