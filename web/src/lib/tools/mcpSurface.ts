export type McpSurface = "admin" | "personal" | "gallery";

export function mcpApiRoot(surface: McpSurface): string {
  if (surface === "personal") {
    return "/api/mcp/personal";
  }
  if (surface === "gallery") {
    return "/api/mcp";
  }
  return "/api/admin/mcp";
}

export function mcpActionsPath(surface: McpSurface): string {
  return surface === "admin" ? "/admin/mcp-actions" : "/craft/v1/mcp-actions";
}

export function isGalleryMcpSurface(surface: McpSurface): boolean {
  return surface === "gallery";
}
