export type McpSurface = "admin" | "personal";

export function mcpApiRoot(surface: McpSurface): string {
  return surface === "personal" ? "/api/mcp/personal" : "/api/admin/mcp";
}

export function mcpActionsPath(surface: McpSurface): string {
  return surface === "personal" ? "/craft/v1/mcp-actions" : "/admin/mcp-actions";
}
