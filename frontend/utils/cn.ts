/** Tiny className combiner (no clsx dependency): drops falsy parts, joins with spaces. */
export function cn(
  ...parts: Array<string | false | null | undefined>
): string {
  return parts.filter(Boolean).join(" ");
}
