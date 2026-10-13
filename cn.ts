export type ClassValue = string | number | null | false | undefined;

/**
 * Tiny dependency-free className joiner. Filters out falsy values so
 * conditional classes (`cond && "..."`) compose cleanly.
 */
export function cn(...values: ClassValue[]): string {
  return values.filter(Boolean).join(" ");
}
