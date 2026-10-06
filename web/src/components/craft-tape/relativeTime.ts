/**
 * Compact relative-time bucketing, ported from dsh `relative-time.ts` so two
 * surfaces dating the same session agree; the words live in i18n (dsh keeps
 * the bucketing shared and the copy locale-owned, for the same reason).
 */

export type RelativeTimeUnit =
  | "now"
  | "minutes"
  | "hours"
  | "days"
  | "months"
  | "years";

export interface RelativeTime {
  unit: RelativeTimeUnit;
  n: number;
}

const MIN = 60_000;
const HOUR = 3_600_000;
const DAY = 86_400_000;

export function relativeTime(atMs: number, nowMs: number): RelativeTime {
  const diff = Math.max(0, nowMs - atMs);
  if (diff < MIN) return { unit: "now", n: 0 };
  if (diff < HOUR) return { unit: "minutes", n: Math.floor(diff / MIN) };
  if (diff < DAY) return { unit: "hours", n: Math.floor(diff / HOUR) };
  if (diff < 30 * DAY) return { unit: "days", n: Math.floor(diff / DAY) };
  if (diff < 365 * DAY) {
    return { unit: "months", n: Math.floor(diff / (30 * DAY)) };
  }
  return { unit: "years", n: Math.floor(diff / (365 * DAY)) };
}

/** Bucket an ISO timestamp; missing or unparseable input stays null. */
export function relativeTimeFromIso(
  iso: string | null | undefined,
  nowMs: number
): RelativeTime | null {
  if (!iso) return null;
  const at = new Date(iso).getTime();
  if (!Number.isFinite(at)) return null;
  return relativeTime(at, nowMs);
}

/** dsh-style list group headers: which day bucket a timestamp falls into. */
export type DayGroup =
  | "today"
  | "yesterday"
  | "thisWeek"
  | "thisMonth"
  | "earlier";

export function dayGroupOf(atMs: number, nowMs: number): DayGroup {
  const startOfDay = (ms: number): number => {
    const d = new Date(ms);
    d.setHours(0, 0, 0, 0);
    return d.getTime();
  };
  const today = startOfDay(nowMs);
  if (atMs >= today) return "today";
  if (atMs >= today - DAY) return "yesterday";
  if (atMs >= today - 6 * DAY) return "thisWeek";
  if (atMs >= today - 29 * DAY) return "thisMonth";
  return "earlier";
}
