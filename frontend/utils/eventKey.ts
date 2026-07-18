/**
 * Event-identity transport for URLs.
 *
 * A catalog event `key` can contain ANY character — `host/path`, `host#digest`, and (for
 * browser-rendered / arbitrary-URL events) `%`, `+`, `?`, `&`, spaces, unicode, multiple
 * slashes. Putting a raw key into a URL is fundamentally fragile: `#` starts a fragment,
 * `?` a query, `%XX` double-decodes, a lone `%` throws in decodeURIComponent, etc.
 *
 * So every URL (the detail route AND the API path) carries an OPAQUE base64url token whose
 * alphabet is only `[A-Za-z0-9_-]` — no URL-reserved character can ever appear. It round-trips
 * any key losslessly, so the routing is correct for all providers, present and future. The raw
 * key remains the internal identity (DB lookup, saved list, recommendations, analytics); the
 * token is derived from it on demand — no migration, no stored ids.
 */

function toBase64Url(bytes: Uint8Array): string {
  let bin = "";
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function fromBase64Url(token: string): Uint8Array {
  const b64 = token.replace(/-/g, "+").replace(/_/g, "/");
  const pad = b64.length % 4 === 0 ? "" : "=".repeat(4 - (b64.length % 4));
  const bin = atob(b64 + pad);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

/** Encode a catalog key into a URL-safe opaque token (base64url of its UTF-8 bytes). */
export function encodeEventKey(key: string): string {
  return toBase64Url(new TextEncoder().encode(key));
}

/** Decode a token produced by {@link encodeEventKey} back into the raw key. */
export function decodeEventKey(token: string): string {
  return new TextDecoder().decode(fromBase64Url(token));
}

const TOKEN_RE = /^[A-Za-z0-9_-]+$/;

/**
 * Resolve the raw key from the catch-all route segments.
 * - New format: a single opaque base64url token (alphabet `[A-Za-z0-9_-]`, so no `.`/`/`).
 * - Legacy format (old bookmarks): a raw key path — every real key contains a host `.` or a
 *   `/`, so it can never be mistaken for a token; decode each segment (reverses the old
 *   per-segment encoding, which also repairs the historical `#` double-encode bug).
 */
export function resolveEventKey(segments: string[]): string {
  if (segments.length === 1 && TOKEN_RE.test(segments[0])) {
    try {
      return decodeEventKey(segments[0]);
    } catch {
      /* not a valid token — fall through to legacy handling */
    }
  }
  return segments
    .map((s) => {
      try {
        return decodeURIComponent(s);
      } catch {
        return s;
      }
    })
    .join("/");
}
