import { parseErrorDetail } from "@/lib/fetcher";
import type {
  McpCatalogEntry,
  McpCatalogEntryCreate,
  McpCatalogEntryUpdate,
  McpCatalogPolicy,
  McpGatewayCacheEntry,
  McpGatewayStats,
  McpPack,
  SystemMcpServer,
} from "@/lib/mcp-catalog/types";

const CATALOG_BASE = "/api/admin/mcp-catalog";
const OPS_BASE = "/api/admin/mcp-gateway";
const USER_BASE = "/api/mcp-catalog";

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
    await fetch(`${CATALOG_BASE}/packs`),
    "Could not load provider packs"
  );
}

export async function listMcpCatalogEntries(): Promise<McpCatalogEntry[]> {
  return readJson<McpCatalogEntry[]>(
    await fetch(`${CATALOG_BASE}/entries`),
    "Could not load system MCP servers"
  );
}

export async function createMcpCatalogEntry(
  input: McpCatalogEntryCreate
): Promise<McpCatalogEntry> {
  const response = await fetch(`${CATALOG_BASE}/entries`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return readJson<McpCatalogEntry>(
    response,
    "Could not install the system MCP"
  );
}

export async function updateMcpCatalogEntry(
  entryId: number,
  input: McpCatalogEntryUpdate
): Promise<McpCatalogEntry> {
  const response = await fetch(`${CATALOG_BASE}/entries/${entryId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return readJson<McpCatalogEntry>(response, "Could not update the system MCP");
}

export async function refreshMcpCatalogEntryTools(
  entryId: number
): Promise<McpCatalogEntry> {
  const response = await fetch(
    `${CATALOG_BASE}/entries/${entryId}/refresh-tools`,
    { method: "POST" }
  );
  return readJson<McpCatalogEntry>(
    response,
    "Could not refresh the tool list"
  );
}

export async function deleteMcpCatalogEntry(entryId: number): Promise<void> {
  await expectOk(
    await fetch(`${CATALOG_BASE}/entries/${entryId}`, { method: "DELETE" }),
    "Could not remove the system MCP"
  );
}

export async function listMcpCatalogPolicies(
  entryId: number
): Promise<McpCatalogPolicy[]> {
  return readJson<McpCatalogPolicy[]>(
    await fetch(`${CATALOG_BASE}/entries/${entryId}/policies`),
    "Could not load cache policies"
  );
}

// ── Admin: gateway operations ──────────────────────────────────────────────

function slugParam(catalogSlug?: string): string {
  return catalogSlug ? `?catalog_slug=${encodeURIComponent(catalogSlug)}` : "";
}

export async function listMcpGatewayCache(
  catalogSlug?: string
): Promise<McpGatewayCacheEntry[]> {
  return readJson<McpGatewayCacheEntry[]>(
    await fetch(`${OPS_BASE}/cache${slugParam(catalogSlug)}`),
    "Could not load the cache"
  );
}

export async function getMcpGatewayStats(
  catalogSlug?: string
): Promise<McpGatewayStats> {
  return readJson<McpGatewayStats>(
    await fetch(`${OPS_BASE}/stats${slugParam(catalogSlug)}`),
    "Could not load gateway stats"
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

// ── User: my system MCP servers ────────────────────────────────────────────

export async function listSystemMcpServers(): Promise<SystemMcpServer[]> {
  return readJson<SystemMcpServer[]>(
    await fetch(`${USER_BASE}/servers`),
    "Could not load system MCP servers"
  );
}

export async function setSystemMcpServerEnabled(
  mcpServerId: number,
  enabled: boolean
): Promise<void> {
  await expectOk(
    await fetch(`${USER_BASE}/servers/${mcpServerId}/enabled`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    }),
    "Could not change the setting"
  );
}
