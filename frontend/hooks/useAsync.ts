"use client";

import { useEffect, useState } from "react";

import { ApiError } from "@/services/api";

export type AsyncStatus = "idle" | "loading" | "success" | "error";

export interface AsyncState<T> {
  status: AsyncStatus;
  data: T | null;
  error: string | null;
}

/**
 * Generic data-fetching hook: runs `fetcher` on mount and whenever `deps`
 * change, aborting the previous request. `enabled=false` short-circuits to idle
 * (used when there's nothing to fetch yet, e.g. an empty browse query).
 */
export function useAsync<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  deps: unknown[],
  enabled = true,
): AsyncState<T> & { reload: () => void } {
  const [state, setState] = useState<AsyncState<T>>({
    status: enabled ? "loading" : "idle",
    data: null,
    error: null,
  });
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (!enabled) {
      setState({ status: "idle", data: null, error: null });
      return;
    }
    const controller = new AbortController();
    setState((s) => ({ status: "loading", data: s.data, error: null }));
    fetcher(controller.signal)
      .then((data) => setState({ status: "success", data, error: null }))
      .catch((err: unknown) => {
        if ((err as Error)?.name === "AbortError") return;
        setState({
          status: "error",
          data: null,
          error: err instanceof ApiError ? err.message : "Something went wrong.",
        });
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce, enabled]);

  return { ...state, reload: () => setNonce((n) => n + 1) };
}
