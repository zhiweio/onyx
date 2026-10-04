/**
 * MCP tool-name presentation helpers shared by the craft and chat timelines.
 *
 * MCP-bridged tools may carry server-qualified names. Two conventions exist:
 * `mcp__<server>__<tool>` (double-underscore, unambiguous) and
 * `mcp_<server>_<tool>` (single-underscore, split on the first underscore —
 * best effort when the server name itself has no underscores). When neither
 * matches, the server is unknown and only the tool name is shown.
 */

export interface McpToolPresentation {
  serverName: string | null;
  toolName: string;
}

export function parseMcpToolName(rawName: string): McpToolPresentation {
  if (rawName.includes("__")) {
    const parts = rawName.split("__");
    if (parts.length >= 3 && parts[0] === "mcp") {
      return {
        serverName: parts[1] || null,
        toolName: parts.slice(2).join("__"),
      };
    }
  }
  if (rawName.startsWith("mcp_")) {
    const rest = rawName.slice("mcp_".length);
    const underscore = rest.indexOf("_");
    if (underscore > 0) {
      return {
        serverName: rest.slice(0, underscore),
        toolName: rest.slice(underscore + 1),
      };
    }
  }
  return { serverName: null, toolName: rawName };
}

export function isMcpToolName(rawName: string): boolean {
  return rawName.startsWith("mcp__") || rawName.startsWith("mcp_");
}
