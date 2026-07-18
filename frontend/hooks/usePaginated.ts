"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "@/services/api";

import type { AsyncStatus } from "./useAsync";

export interface Page<T> {
  items: T[];
  total: number;
  hasMore: boolean;
}

export interface PagedResult<T> {
  status: AsyncStatus;
  items: T[]; // everything loaded so far (page 0 … current)
  total: number; // full server-side count for the whole set
  hasMore: boolean;
  loadingMore: boolean;
  error: string | null;
  loadMore: () => void;
  reload: () => void;
}

/**
 * Offset-pagination hook. Loads page 0 on mount / dep change, then `loadMore()`
 * fetches the next page from the server and APPENDS it — so a page can walk an
 * arbitrarily large set (10,000+ events) without ever holding it all in one request.
 * A run token discards results from a superseded query, so rapid navigation can't
 * interleave pages from different sets.
 */
export function usePaginated<T>(
  fetchPage: (offset: number, signal: AbortSignal) => Promise<Page<T>>,
  deps: unknown[],
  enabled = true,
): PagedResult<T> {
  const [items, setItems] = useState<T[]>([]);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [status, setStatus] = useState<AsyncStatus>(enabled ? "loading" : "idle");
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  const offsetRef = useRef(0);
  const busyRef = useRef(false);
  const runRef = useRef(0);
  const fetchRef = useRef(fetchPage);
  fetchRef.current = fetchPage;

  useEffect(() => {
    if (!enabled) {
      runRef.current++;
      setStatus("idle");
      setItems([]);
      setTotal(0);
      setHasMore(false);
      return;
    }
    const myRun = ++runRef.current;
    const controller = new AbortController();
    busyRef.current = true;
    offsetRef.current = 0;
    setStatus("loading");
    setError(null);
    fetchRef
      .current(0, controller.signal)
      .then((page) => {
        if (runRef.current !== myRun) return;
        setItems(page.items);
        setTotal(page.total);
        setHasMore(page.hasMore);
        offsetRef.current = page.items.length;
        setStatus("success");
      })
      .catch((err: unknown) => {
        if ((err as Error)?.name === "AbortError" || runRef.current !== myRun) return;
        setStatus("error");
        setError(err instanceof ApiError ? err.message : "Something went wrong.");
      })
      .finally(() => {
        if (runRef.current === myRun) busyRef.current = false;
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce, enabled]);

  const loadMore = useCallback(() => {
    if (busyRef.current || !hasMore) return;
    const myRun = runRef.current;
    const controller = new AbortController();
    busyRef.current = true;
    setLoadingMore(true);
    fetchRef
      .current(offsetRef.current, controller.signal)
      .then((page) => {
        if (runRef.current !== myRun) return;
        setItems((prev) => [...prev, ...page.items]);
        setTotal(page.total);
        setHasMore(page.hasMore);
        offsetRef.current += page.items.length;
      })
      .catch((err: unknown) => {
        if ((err as Error)?.name === "AbortError" || runRef.current !== myRun) return;
        setError(err instanceof ApiError ? err.message : "Something went wrong.");
      })
      .finally(() => {
        if (runRef.current === myRun) {
          busyRef.current = false;
          setLoadingMore(false);
        }
      });
  }, [hasMore]);

  return {
    status,
    items,
    total,
    hasMore,
    loadingMore,
    error,
    loadMore,
    reload: () => setNonce((n) => n + 1),
  };
}
