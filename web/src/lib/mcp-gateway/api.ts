import { parseErrorDetail } from "@/lib/fetcher";
import type {
  McpGatewayCacheEntry,
  McpGatewayPack,
  McpGatewayPolicy,
  McpGatewayProvider,
  McpGatewayProviderCreate,
  McpGatewayStats,
} from "@/lib/mcp-gateway/types";

const BASE = "/api/admin/mcp-gateway";

async function readJson<T>(response: Response, fallback: string): Promise<T> {
  if (!response.ok) {
    throw new Error(await parseErrorDetail(response, fallback));
  }
  return response.json() as Promise<T>;
}

export async function listMcpGatewayPacks(): Promise<McpGatewayPack[]> {
  const response = await fetch(`${BASE}/packs`);
  return readJson<McpGatewayPack[]>(response, "Could not load packs");
}

export async function listMcpGatewayProviders(): Promise<McpGatewayProvider[]> {
  const response = await fetch(`${BASE}/providers`);
  return readJson<McpGatewayProvider[]>(response, "Could not load providers");
}

export async function createMcpGatewayProvider(
  input: McpGatewayProviderCreate
): Promise<McpGatewayProvider> {
  const response = await fetch(`${BASE}/providers`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return readJson<McpGatewayProvider>(response, "Could not create provider");
}

export async function listMcpGatewayPolicies(
  slug: string
): Promise<McpGatewayPolicy[]> {
  const response = await fetch(
    `${BASE}/providers/${encodeURIComponent(slug)}/policies`
  );
  return readJson<McpGatewayPolicy[]>(response, "Could not load policies");
}

export async function listMcpGatewayCache(
  providerSlug?: string
): Promise<McpGatewayCacheEntry[]> {
  const params = providerSlug
    ? `?provider_slug=${encodeURIComponent(providerSlug)}`
    : "";
  const response = await fetch(`${BASE}/cache${params}`);
  return readJson<McpGatewayCacheEntry[]>(response, "Could not load cache");
}

export async function getMcpGatewayStats(
  providerSlug?: string
): Promise<McpGatewayStats> {
  const params = providerSlug
    ? `?provider_slug=${encodeURIComponent(providerSlug)}`
    : "";
  const response = await fetch(`${BASE}/stats${params}`);
  return readJson<McpGatewayStats>(response, "Could not load stats");
}

export async function invalidateMcpGatewayCache(input: {
  cache_key?: string;
  provider_slug?: string;
  tool_name?: string;
}): Promise<{ deleted: number }> {
  const response = await fetch(`${BASE}/cache/invalidate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return readJson<{ deleted: number }>(response, "Could not invalidate cache");
}

export async function refreshMcpGatewayCache(cacheKey: string): Promise<void> {
  const response = await fetch(`${BASE}/cache/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cache_key: cacheKey }),
  });
  if (!response.ok) {
    throw new Error(await parseErrorDetail(response, "Could not refresh cache"));
  }
}
