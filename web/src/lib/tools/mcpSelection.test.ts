import {
  MCPAuthenticationPerformer,
  MCPAuthenticationType,
  MCPServerStatus,
  McpServerScope,
  type MCPServer,
} from "@/lib/tools/types";
import {
  mcpSelectionKey,
  parseMcpServerIds,
  serializeMcpServerIds,
  toChatMcpServer,
  uniqueMcpServerIds,
  withMcpServerEnabled,
} from "@/lib/tools/mcpSelection";

const catalogServer: MCPServer = {
  id: 12,
  name: "Parallel Search",
  server_url: "https://mcp.example.com/parallel",
  owner: "owner@example.com",
  status: MCPServerStatus.CONNECTED,
  is_public: true,
  groups: [],
  users: [],
  tool_count: 3,
  auth_type: MCPAuthenticationType.NONE,
  auth_performer: MCPAuthenticationPerformer.ADMIN,
  user_can_authenticate: true,
  scope: McpServerScope.USER,
};

describe("mcpSelection", () => {
  it("keeps one sorted copy of each positive id", () => {
    expect(uniqueMcpServerIds([3, 1, 1], [2], undefined)).toEqual([1, 2, 3]);
    expect(uniqueMcpServerIds([0, -1, 2.5, 4])).toEqual([4]);
  });

  it("adds and removes a server without mutating the source", () => {
    const ids = [2];
    expect(withMcpServerEnabled(ids, 5, true)).toEqual([2, 5]);
    expect(withMcpServerEnabled([2, 5], 2, false)).toEqual([5]);
    expect(ids).toEqual([2]);
  });

  it("reads and writes a stored id list", () => {
    expect(parseMcpServerIds(serializeMcpServerIds([9, 3, 3]))).toEqual([3, 9]);
    expect(parseMcpServerIds("not-json")).toEqual([]);
    expect(parseMcpServerIds('{"ids":[1]}')).toEqual([]);
  });

  it("keys selection by agent so chats on the same agent share it", () => {
    expect(mcpSelectionKey(0)).toBe("onyx:mcp-servers:agent:0");
  });

  it("maps an accessible server onto the chat row shape", () => {
    expect(toChatMcpServer(catalogServer)).toEqual({
      id: 12,
      name: "Parallel Search",
      owner_email: "owner@example.com",
      owner: "owner@example.com",
      server_url: "https://mcp.example.com/parallel",
      auth_type: MCPAuthenticationType.NONE,
      auth_performer: MCPAuthenticationPerformer.ADMIN,
      user_can_authenticate: true,
      auth_template: undefined,
      user_credentials: undefined,
      scope: McpServerScope.USER,
    });
  });
});
