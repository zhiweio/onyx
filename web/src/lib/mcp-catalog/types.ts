export enum McpCatalogOrigin {
  LOCAL = "LOCAL",
  PUSHED = "PUSHED",
}

export interface McpPack {
  slug: string;
  display_name: string;
  description: string;
  default_upstream_url: string;
  group?: string;
  transport: string;
  auth_adapter: string;
}

export interface McpCatalogEntry {
  id: number;
  slug: string;
  display_name: string;
  description: string | null;
  pack_slug: string;
  upstream_url: string;
  transport: string;
  auth_adapter: string;
  enabled: boolean;
  is_public: boolean;
  origin: McpCatalogOrigin;
  group_ids: number[];
  mcp_server_id: number | null;
  gateway_url: string;
  tool_count: number;
  tools_list_refreshed_at: string | null;
  created_at: string;
  has_credentials: boolean;
  discovery_error?: string | null;
}

/**
 * Upstream credentials for a system MCP. Shape is provider-specific, so it
 * stays open, but every value is a string the admin typed.
 */
export type McpCredentials = Record<string, string>;

/**
 * Cache policy overrides keyed by tool name, glob, or "*" for the entry
 * default. Values mirror the backend `CachePolicySpec` fields the admin chose
 * to change, so only a few are ever present.
 */
export type McpPolicyOverrides = Record<
  string,
  Partial<{
    refresh_mode: string;
    ttl_seconds: number;
    swr_seconds: number;
    schedule_cron: string | null;
    key_fields: string[] | null;
    cache_empty_ttl_seconds: number;
    inline_threshold_bytes: number;
    max_response_bytes: number;
    digest_max_bytes: number;
    digest_paths: string[];
  }>
>;

export interface McpCatalogEntryCreate {
  slug: string;
  display_name?: string;
  description?: string;
  pack_slug: string;
  upstream_url: string;
  credentials: McpCredentials;
  enabled: boolean;
  is_public: boolean;
  group_ids: number[];
}

export interface McpCatalogEntryUpdate {
  display_name?: string;
  description?: string;
  upstream_url?: string;
  credentials?: McpCredentials;
  policy_overrides?: McpPolicyOverrides;
  enabled?: boolean;
  is_public?: boolean;
  group_ids?: number[];
}

export interface McpCatalogPolicy {
  label: string;
  refresh_mode: string;
  ttl_seconds: number;
  swr_seconds: number;
  schedule_cron: string | null;
  key_fields: string[] | null;
  cache_empty_ttl_seconds: number;
  inline_threshold_bytes: number;
  max_response_bytes: number;
  digest_max_bytes: number;
  is_override: boolean;
}

export interface McpGatewayCacheEntry {
  cache_key: string;
  catalog_slug: string;
  tool_name: string;
  effective_tool_name: string;
  hit_count: number;
  size_bytes: number;
  storage: string;
  last_fetched_at: string;
  last_accessed_at: string;
  last_refresh_status: string | null;
}

export interface McpGatewayStats {
  total_calls: number;
  upstream_billed: number;
  cache_hits: number;
  hit_rate: number;
  saved_calls: number;
  total_response_bytes: number;
  by_outcome: Record<string, number>;
  blob_total_count: number;
  blob_total_bytes: number;
  blob_by_storage: Record<string, { count: number; bytes: number }>;
  retention_days?: number | null;
  top_servers?: { slug: string; count: number }[];
  top_tools?: { tool: string; count: number }[];
}

export interface McpGatewayCacheList {
  items: McpGatewayCacheEntry[];
  next_cursor: string | null;
  total: number;
}

export interface McpGatewayCallItem {
  id: number;
  created_at: string;
  catalog_slug: string;
  tool_name: string;
  effective_tool_name: string;
  outcome: string;
  upstream_billed: boolean;
  latency_ms: number;
  response_bytes: number;
  user_email: string | null;
  session_id: string | null;
  cache_key: string;
  arguments_preview: string;
  error_message: string | null;
}

export interface McpGatewayCallList {
  items: McpGatewayCallItem[];
  next_cursor: string | null;
  total: number;
}

export interface McpGatewayCallDetail extends McpGatewayCallItem {
  arguments: Record<string, unknown>;
}

/** One system MCP server as the current user sees it in their settings. */
export interface SystemMcpServer {
  mcp_server_id: number;
  catalog_slug: string;
  display_name: string;
  description: string | null;
  enabled_for_user: boolean;
  tool_count: number;
}
