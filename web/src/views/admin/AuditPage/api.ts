import { errorHandlingFetcher } from "@/lib/fetcher";
import type { PaginatedResult } from "@/hooks/useServerPaginatedTable";

export interface AuditToolCall {
  id: number;
  user: string;
  session_id: string | null;
  tool: string;
  arguments: Record<string, unknown> | null;
  ok: boolean;
  result_excerpt: string;
  duration_ms: number | null;
  created_at: string;
}

export interface AuditToolStat {
  tool: string;
  calls: number;
  failures: number;
  avg_ms: number | null;
}

export interface AuditToolCallsResponse extends PaginatedResult<AuditToolCall> {
  stats: AuditToolStat[];
}

export interface AuditApproval {
  id: string;
  session_id: string;
  app_name: string;
  decision: string | null;
  decided_at: string | null;
  created_at: string;
}

export interface AuditQuarantine {
  id: string;
  session_id: string | null;
  url_hash: string;
  verdict: string;
  decision: string | null;
  created_at: string;
}

export interface AuditQueryHistoryRow {
  user: string;
  query: string;
  created_at: string;
}

export interface AuditUsageSummary {
  days: number;
  search_queries: number;
  active_users: number;
  tool_calls: number;
}

export interface AuditWindow {
  start: string;
  end: string;
}

function buildQuery(
  params: Record<string, string | number | undefined>
): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "" && value !== null) {
      query.set(key, String(value));
    }
  }
  const encoded = query.toString();
  return encoded ? `?${encoded}` : "";
}

export function fetchAuditToolCalls(
  window: AuditWindow,
  args: { q: string; offset: number; limit: number }
): Promise<AuditToolCallsResponse> {
  return errorHandlingFetcher<AuditToolCallsResponse>(
    `/api/admin/audit/tool-calls${buildQuery({
      start: window.start,
      end: window.end,
      q: args.q || undefined,
      offset: args.offset,
      limit: args.limit,
    })}`
  );
}

export function fetchAuditApprovals(
  window: AuditWindow,
  args: { q: string; offset: number; limit: number }
): Promise<PaginatedResult<AuditApproval>> {
  return errorHandlingFetcher<PaginatedResult<AuditApproval>>(
    `/api/admin/audit/approvals${buildQuery({
      start: window.start,
      q: args.q || undefined,
      offset: args.offset,
      limit: args.limit,
    })}`
  );
}

export function fetchAuditQuarantines(
  window: AuditWindow,
  args: { q: string; offset: number; limit: number }
): Promise<PaginatedResult<AuditQuarantine>> {
  return errorHandlingFetcher<PaginatedResult<AuditQuarantine>>(
    `/api/admin/audit/quarantines${buildQuery({
      start: window.start,
      q: args.q || undefined,
      offset: args.offset,
      limit: args.limit,
    })}`
  );
}

export function fetchAuditQueryHistory(
  window: AuditWindow,
  args: { q: string; offset: number; limit: number }
): Promise<PaginatedResult<AuditQueryHistoryRow>> {
  return errorHandlingFetcher<PaginatedResult<AuditQueryHistoryRow>>(
    `/api/admin/audit/query-history${buildQuery({
      start: window.start,
      end: window.end,
      q: args.q || undefined,
      offset: args.offset,
      limit: args.limit,
    })}`
  );
}

export function fetchAuditUsage(days: number): Promise<AuditUsageSummary> {
  return errorHandlingFetcher<AuditUsageSummary>(
    `/api/admin/audit/usage${buildQuery({ days })}`
  );
}

/** Max rows a single CSV export will pull; guards the browser tab. */
export const EXPORT_ROW_LIMIT = 5000;

/** Trigger a client-side CSV download for the given rows. */
export function downloadCsv(filename: string, rows: string[][]): void {
  const csv = rows.map((row) => row.join(",")).join("\n");
  const url = URL.createObjectURL(
    new Blob(["\uFEFF" + csv], {
      type: "text/csv",
    })
  );
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

/** Sanitize one CSV cell (strip separators and newlines). */
export function csvCell(value: string): string {
  return value.replace(/[",\n]/g, " ");
}
