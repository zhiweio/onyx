import { errorHandlingFetcher } from "@/lib/fetcher";
import type {
  ReplayPage,
  TapeEventList,
  TapeSessionList,
  TapeStats,
  TapeStatsSeriesPoint,
  TapeTurnList,
} from "@/lib/craft-tape/types";

const TAPE_BASE = "/api/build/admin/tape";
const MY_TAPE_BASE = "/api/build/tape";

function buildQuery(
  params: Record<string, string | number | undefined>
): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") {
      search.set(key, String(value));
    }
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

export function listTapeSessions(args: {
  from?: string;
  to?: string;
  origin?: string;
  userQ?: string;
  q?: string;
  sort?: string;
  order?: string;
  offset: number;
  limit: number;
}): Promise<TapeSessionList> {
  return errorHandlingFetcher<TapeSessionList>(
    `${TAPE_BASE}/sessions${buildQuery({
      from: args.from,
      to: args.to,
      origin: args.origin,
      user_q: args.userQ || undefined,
      q: args.q || undefined,
      sort: args.sort,
      order: args.order,
      offset: args.offset,
      limit: args.limit,
    })}`
  );
}

export function listTapeTurns(sessionId: string): Promise<TapeTurnList> {
  return errorHandlingFetcher<TapeTurnList>(
    `${TAPE_BASE}/sessions/${sessionId}/turns`
  );
}

export function listTapeEvents(
  sessionId: string,
  afterSourceId?: number | null
): Promise<TapeEventList> {
  return errorHandlingFetcher<TapeEventList>(
    `${TAPE_BASE}/sessions/${sessionId}/events${buildQuery({
      after_source_id: afterSourceId ?? undefined,
      limit: 200,
    })}`
  );
}

export function fetchTapeStats(args: {
  from?: string;
  to?: string;
}): Promise<TapeStats> {
  return errorHandlingFetcher<TapeStats>(
    `${TAPE_BASE}/stats${buildQuery({ from: args.from, to: args.to })}`
  );
}

export function fetchTapeStatsSeries(args: {
  from?: string;
  to?: string;
}): Promise<{ series: TapeStatsSeriesPoint[] }> {
  return errorHandlingFetcher<{ series: TapeStatsSeriesPoint[] }>(
    `${TAPE_BASE}/stats/series${buildQuery({ from: args.from, to: args.to })}`
  );
}

export async function exportTapeSession(sessionId: string): Promise<void> {
  const response = await fetch(`${TAPE_BASE}/sessions/${sessionId}/export`, {
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(`Export failed (${response.status})`);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `craft-tape-${sessionId}.jsonl`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function fetchTapeReplay(
  sessionId: string,
  args: { afterSourceId?: number | null; turnIndex?: number } = {}
): Promise<ReplayPage> {
  return errorHandlingFetcher<ReplayPage>(
    `${TAPE_BASE}/sessions/${sessionId}/replay${buildQuery({
      after_source_id: args.afterSourceId ?? undefined,
      turn_index: args.turnIndex,
    })}`
  );
}

export function listMyTapeSessions(args: {
  from?: string;
  to?: string;
  origin?: string;
  q?: string;
  sort?: string;
  order?: string;
  offset: number;
  limit: number;
}): Promise<TapeSessionList> {
  return errorHandlingFetcher<TapeSessionList>(
    `${MY_TAPE_BASE}/sessions${buildQuery({
      from: args.from,
      to: args.to,
      origin: args.origin,
      q: args.q || undefined,
      sort: args.sort,
      order: args.order,
      offset: args.offset,
      limit: args.limit,
    })}`
  );
}

export function listMyTapeTurns(sessionId: string): Promise<TapeTurnList> {
  return errorHandlingFetcher<TapeTurnList>(
    `${MY_TAPE_BASE}/sessions/${sessionId}/turns`
  );
}

export function listMyTapeEvents(
  sessionId: string,
  afterSourceId?: number | null
): Promise<TapeEventList> {
  return errorHandlingFetcher<TapeEventList>(
    `${MY_TAPE_BASE}/sessions/${sessionId}/events${buildQuery({
      after_source_id: afterSourceId ?? undefined,
      limit: 200,
    })}`
  );
}

export function fetchMyTapeReplay(
  sessionId: string,
  args: { afterSourceId?: number | null; turnIndex?: number } = {}
): Promise<ReplayPage> {
  return errorHandlingFetcher<ReplayPage>(
    `${MY_TAPE_BASE}/sessions/${sessionId}/replay${buildQuery({
      after_source_id: args.afterSourceId ?? undefined,
      turn_index: args.turnIndex,
    })}`
  );
}

export async function exportMyTapeSession(sessionId: string): Promise<void> {
  const response = await fetch(`${MY_TAPE_BASE}/sessions/${sessionId}/export`, {
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(`Export failed (${response.status})`);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `craft-tape-${sessionId}.jsonl`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
