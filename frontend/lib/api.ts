import type { SearchResponse } from "./types";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ??
  "http://127.0.0.1:8000";

export class ApiError extends Error {}

/** Call the frozen backend endpoint: POST /search {query}. */
export async function searchEvents(
  query: string,
  signal?: AbortSignal,
): Promise<SearchResponse> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
      signal,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError(
      "Could not reach the server. Is the backend running?",
    );
  }

  if (!response.ok) {
    throw new ApiError(`Search failed (${response.status}). Please try again.`);
  }

  return (await response.json()) as SearchResponse;
}
