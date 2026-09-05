export interface McpGatewayPack {
  slug: string;
  display_name: string;
  default_upstream_url: string;
  transport: string;
  auth_adapter: string;
}

export interface McpGatewayProvider {
  id: number;
  slug: string;
  display_name: string;
  pack_slug: string;
  upstream_url: string;
  transport: string;
  auth_adapter: string;
  enabled: boolean;
  mcp_server_id: number | null;
  gateway_url: string;
  tools_list_refreshed_at: string | null;
  created_at: string;
}

export interface McpGatewayPolicy {
  tool_name: string;
  refresh_mode: string;
  ttl_seconds: number;
  swr_seconds: number;
  schedule_cron: string | null;
  key_fields: string[] | null;
  normalize: Record<string, unknown> | null;
  cache_empty_ttl_seconds: number;
  max_response_bytes: number;
  is_db_override: boolean;
}

export interface McpGatewayCacheEntry {
  cache_key: string;
  provider_slug: string;
  tool_name: string;
  effective_tool_name: string;
  hit_count: number;
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
  by_outcome: Record<string, number>;
}

export interface McpGatewayProviderCreate {
  slug: string;
  pack_slug: string;
  upstream_url: string;
  credentials: Record<string, string>;
  enabled: boolean;
  attach_mcp_server: boolean;
}
