"use client";

import { useCallback, useRef, useState } from "react";

import { ApiError } from "@/services/api";
import { searchPlatform } from "@/services/platform";
import type { PlatformSearchResponse } from "@/types/platform";

import type { AsyncStatus } from "./useAsync";

interface SearchState {
  status: AsyncStatus;
  data: PlatformSearchResponse | null;
  error: string | null;
  lastQuery: string;
}

/**
 * Imperative natural-language search over the Platform surface. The backend
 * resolves the text to a structured query (reusing the AI query parser) and
 * returns repository-backed DTOs. Aborts any in-flight request when a newer one
 * starts, so results never arrive out of order.
 */
export function usePlatformSearch() {
  const [state, setState] = useState<SearchState>({
    status: "idle",
    data: null,
    error: null,
    lastQuery: "",
  });
  const controller = useRef<AbortController | null>(null);

  const run = useCallback((query: string) => {
    const trimmed = query.trim();
    if (!trimmed) return;
    controller.current?.abort();
    const ctrl = new AbortController();
    controller.current = ctrl;
    setState({ status: "loading", data: null, error: null, lastQuery: trimmed });
    searchPlatform(trimmed, 48, ctrl.signal)
      .then((data) =>
        setState({ status: "success", data, error: null, lastQuery: trimmed }),
      )
      .catch((err: unknown) => {
        if ((err as Error)?.name === "AbortError") return;
        setState({
          status: "error",
          data: null,
          error: err instanceof ApiError ? err.message : "Search failed.",
          lastQuery: trimmed,
        });
      });
  }, []);

  return { ...state, run };
}
