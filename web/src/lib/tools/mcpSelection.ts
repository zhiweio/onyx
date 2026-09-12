import {
  MCPAuthenticationPerformer,
  MCPAuthenticationType,
  type MCPServer,
} from "@/lib/tools/types";
import type { MCPServer as ChatMcpServer } from "@/lib/tools/components/MCPLineItem";

export const MCP_SELECTION_STORAGE_PREFIX = "onyx:mcp-servers";

export function mcpSelectionKey(agentId: number): string {
  return `${MCP_SELECTION_STORAGE_PREFIX}:agent:${agentId}`;
}

export function uniqueMcpServerIds(
  ...groups: Array<readonly number[] | undefined>
): number[] {
  const ids = new Set<number>();
  for (const group of groups) {
    for (const id of group ?? []) {
      if (Number.isInteger(id) && id > 0) {
        ids.add(id);
      }
    }
  }
  return [...ids].sort((left, right) => left - right);
}

export function withMcpServerEnabled(
  ids: readonly number[],
  serverId: number,
  enabled: boolean
): number[] {
  return uniqueMcpServerIds(
    enabled ? [...ids, serverId] : ids.filter((id) => id !== serverId)
  );
}

export function parseMcpServerIds(raw: string): number[] {
  try {
    const value: unknown = JSON.parse(raw);
    if (!Array.isArray(value)) {
      return [];
    }
    return uniqueMcpServerIds(
      value.filter((id): id is number => Number.isInteger(id))
    );
  } catch {
    return [];
  }
}

export function serializeMcpServerIds(ids: readonly number[]): string {
  return JSON.stringify(uniqueMcpServerIds(ids));
}

/** Shape the chat MCP list can render from the user-accessible server payload. */
export function toChatMcpServer(server: MCPServer): ChatMcpServer {
  return {
    id: server.id,
    name: server.name,
    owner_email: server.owner,
    owner: server.owner,
    server_url: server.server_url,
    auth_type: server.auth_type ?? MCPAuthenticationType.NONE,
    auth_performer: server.auth_performer ?? MCPAuthenticationPerformer.ADMIN,
    user_can_authenticate: server.user_can_authenticate,
    auth_template: server.auth_template,
    user_credentials: server.user_credentials,
    scope: server.scope,
  };
}
