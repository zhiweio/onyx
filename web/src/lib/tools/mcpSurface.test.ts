import {
  isGalleryMcpSurface,
  mcpActionsPath,
  mcpApiRoot,
} from "@/lib/tools/mcpSurface";

test("gallery reads user MCP APIs and stays on the craft page", () => {
  expect(mcpApiRoot("gallery")).toBe("/api/mcp");
  expect(mcpActionsPath("gallery")).toBe("/craft/v1/mcp-actions");
  expect(isGalleryMcpSurface("gallery")).toBe(true);
  expect(isGalleryMcpSurface("personal")).toBe(false);
  expect(mcpApiRoot("personal")).toBe("/api/mcp/personal");
  expect(mcpApiRoot("admin")).toBe("/api/admin/mcp");
});
