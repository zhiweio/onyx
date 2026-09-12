import { parseErrorDetail } from "@/lib/fetcher";
import type {
  McpGatewayCacheList,
  McpGatewayCallDetail,
  McpGatewayCallList,
  McpGatewayStats,
  McpGatewayStatsSeries,
  McpPack,
} from "@/lib/mcp-catalog/types";

const OPS_BASE = "/api/admin/mcp-gateway";
const ADMIN_MCP_BASE = "/api/admin/mcp";

async function readJson<T>(response: Response, fallback: string): Promise<T> {
  if (!response.ok) {
    throw new Error(await parseErrorDetail(response, fallback));
  }
  // SAFETY: every caller pairs a route with the response model that route is
  // typed to return in the backend, so the parsed body matches T.
  return response.json() as Promise<T>;
}

async function expectOk(response: Response, fallback: string): Promise<void> {
  if (!response.ok) {
    throw new Error(await parseErrorDetail(response, fallback));
  }
}

// ── Admin: catalog ─────────────────────────────────────────────────────────

export async function listMcpPacks(): Promise<McpPack[]> {
  return readJson<McpPack[]>(
    await fetch(`${ADMIN_MCP_BASE}/packs`),
    "Could not load provider packs"
  );
}

function queryString(params: Record<string, string | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) search.set(key, value);
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export async function listMcpGatewayCache(params: {
  catalog_slug?: string;
  tool?: string;
  q?: string;
  cursor?: string;
  limit?: number;
  offset?: number;
}): Promise<McpGatewayCacheList> {
  return readJson<McpGatewayCacheList>(
    await fetch(
      `${OPS_BASE}/cache${queryString({
        catalog_slug: params.catalog_slug,
        tool: params.tool,
        q: params.q,
        cursor: params.cursor,
        limit: params.limit ? String(params.limit) : undefined,
        offset:
          params.offset && params.offset > 0
            ? String(params.offset)
            : undefined,
      })}`
    ),
    "Could not load the cache"
  );
}

export async function getMcpGatewayStats(params: {
  from: string;
  to: string;
  catalog_slug?: string;
}): Promise<McpGatewayStats> {
  return readJson<McpGatewayStats>(
    await fetch(
      `${OPS_BASE}/stats${queryString({
        from: params.from,
        to: params.to,
        catalog_slug: params.catalog_slug,
      })}`
    ),
    "Could not load gateway stats"
  );
}

export async function listMcpGatewayCalls(params: {
  from: string;
  to: string;
  catalog_slug?: string;
  tool?: string;
  outcome?: string;
  user_email?: string;
  q?: string;
  cursor?: string;
  limit?: number;
  offset?: number;
}): Promise<McpGatewayCallList> {
  return readJson<McpGatewayCallList>(
    await fetch(
      `${OPS_BASE}/calls${queryString({
        from: params.from,
        to: params.to,
        catalog_slug: params.catalog_slug,
        tool: params.tool,
        outcome: params.outcome,
        user_email: params.user_email,
        q: params.q,
        cursor: params.cursor,
        limit: params.limit ? String(params.limit) : undefined,
        offset:
          params.offset && params.offset > 0
            ? String(params.offset)
            : undefined,
      })}`
    ),
    "Could not load call history"
  );
}

export async function getMcpGatewayStatsSeries(params: {
  from: string;
  to: string;
  catalog_slug?: string;
}): Promise<McpGatewayStatsSeries> {
  return readJson<McpGatewayStatsSeries>(
    await fetch(
      `${OPS_BASE}/stats/series${queryString({
        from: params.from,
        to: params.to,
        catalog_slug: params.catalog_slug,
      })}`
    ),
    "Could not load gateway series"
  );
}

export async function clearMcpGatewayHistory(input?: {
  cache?: boolean;
  calls?: boolean;
}): Promise<Record<string, number>> {
  return readJson<Record<string, number>>(
    await fetch(`${OPS_BASE}/history/clear`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        cache: input?.cache ?? true,
        calls: input?.calls ?? true,
      }),
    }),
    "Could not clear gateway history"
  );
}

export async function getMcpGatewayCall(
  callId: string
): Promise<McpGatewayCallDetail> {
  return readJson<McpGatewayCallDetail>(
    await fetch(`${OPS_BASE}/calls/${callId}`),
    "Could not load the call"
  );
}

export async function invalidateMcpGatewayCache(input: {
  cache_key?: string;
  catalog_slug?: string;
  tool_name?: string;
}): Promise<{ deleted: number }> {
  const response = await fetch(`${OPS_BASE}/cache/invalidate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return readJson<{ deleted: number }>(
    response,
    "Could not invalidate the cache"
  );
}

export async function refreshMcpGatewayCache(cacheKey: string): Promise<void> {
  await expectOk(
    await fetch(`${OPS_BASE}/cache/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cache_key: cacheKey }),
    }),
    "Could not queue a refresh"
  );
}
