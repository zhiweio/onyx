/**
 * Shared tape-page constants — the single source for the personal and admin
 * entries (dsh keeps one definition per concept; these were duplicated across
 * both pages before the dsh-style rebuild).
 */

export const WINDOW_OPTIONS = [7, 30, 90] as const;

export const ORIGINS = [
  "interactive",
  "scheduled",
  "slack",
  "job",
  "im",
  "eval",
] as const;

export type KnownOrigin = (typeof ORIGINS)[number] | "unknown";

export function isKnownOrigin(value: string): value is KnownOrigin {
  return value === "unknown" || (ORIGINS as readonly string[]).includes(value);
}

/** Localized origin label; unknown enum values pass through raw. */
export function originKeyLabel(
  origin: string,
  t: (key: string) => string
): string {
  return isKnownOrigin(origin) ? t(`origins.${origin}`) : origin;
}

/** Sort keys the list endpoint accepts. */
export const SORT_KEYS = ["created_at", "name", "last_activity"] as const;

export type TapeSortKey = (typeof SORT_KEYS)[number];
export type TapeSortOrder = "asc" | "desc";

export type TapeReasonTagColor = "green" | "red" | "amber" | "gray";

export const KNOWN_REASONS = [
  "completed",
  "aborted",
  "error",
  "interrupted",
  "deadline_exceeded",
] as const;

export type KnownReason = (typeof KNOWN_REASONS)[number];

export function isKnownReason(value: string): value is KnownReason {
  return (KNOWN_REASONS as readonly string[]).includes(value);
}

export const REASON_TAG_COLORS: Record<string, TapeReasonTagColor> = {
  completed: "green",
  error: "red",
  aborted: "amber",
  interrupted: "amber",
  deadline_exceeded: "amber",
};

export function reasonTagColor(reason: string | null): TapeReasonTagColor {
  if (reason === null) return "amber";
  return REASON_TAG_COLORS[reason] ?? "gray";
}

export function isoDaysAgo(days: number): string {
  return new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString();
}

/** Row and header title: the task name, falling back to a short session id. */
export function sessionTitle(session: {
  name: string | null;
  session_id: string;
}): string {
  return session.name ?? session.session_id.slice(0, 8);
}

/** Compact duration ("42s", "3m 12s", "1h 04m"); null when unbounded. */
export function formatDuration(
  startedAt: string | null,
  endedAt: string | null
): string | null {
  if (!startedAt || !endedAt) return null;
  const ms = new Date(endedAt).getTime() - new Date(startedAt).getTime();
  if (!Number.isFinite(ms) || ms < 0) return null;
  if (ms < 1000) return "<1s";
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${String(s % 60).padStart(2, "0")}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${String(m % 60).padStart(2, "0")}m`;
}

/** Compact token counts ("1.2k", "3.4M") for meta lines and rail tooltips. */
export function formatTokenCount(value: number | null): string {
  if (value === null) return "—";
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return String(value);
}
