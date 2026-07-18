/**
 * Low-level HTTP client for the backend. Every request in the app flows through
 * here, so error handling, the base URL, and JSON parsing live in one place.
 * There is NO proxy — the browser calls the backend origin directly, so the
 * backend CORS must allow the frontend origin (it does: localhost:3000).
 */

const BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ??
  "http://127.0.0.1:8000";

export class ApiError extends Error {
  status?: number;
  constructor(message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function handle<T>(response: Response): Promise<T> {
  if (response.status === 404) {
    throw new ApiError("Not found", 404);
  }
  if (!response.ok) {
    throw new ApiError(
      `Request failed (${response.status}). Please try again.`,
      response.status,
    );
  }
  return (await response.json()) as T;
}

function networkError(err: unknown): never {
  if ((err as Error)?.name === "AbortError") throw err;
  throw new ApiError("Could not reach the server. Is the backend running?");
}

export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, { signal });
  } catch (err) {
    networkError(err);
  }
  return handle<T>(response);
}

export async function apiPost<T>(
  path: string,
  body: unknown,
  signal?: AbortSignal,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
  } catch (err) {
    networkError(err);
  }
  return handle<T>(response);
}
