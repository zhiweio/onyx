import { FILE_READER_TOOL_ID, SEARCH_TOOL_ID } from "@/lib/tools/constants";
import type { ToolSnapshot } from "@/lib/tools/types";

export function shouldShowBuiltInToolInChatMenu({
  tool,
  availableToolIds,
  currentProjectId,
  hasProjectFiles,
  hasNoConnectors,
}: {
  tool: ToolSnapshot;
  availableToolIds: ReadonlySet<number> | null;
  currentProjectId: number | null | undefined;
  hasProjectFiles: boolean;
  hasNoConnectors: boolean;
}): boolean {
  if (tool.mcp_server_id) return false;
  if (!tool.chat_selectable) return false;
  if (tool.in_code_tool_id === FILE_READER_TOOL_ID) return false;

  const isSearch = tool.in_code_tool_id === SEARCH_TOOL_ID;
  if (isSearch && currentProjectId != null) {
    return hasProjectFiles;
  }
  if (isSearch && hasNoConnectors) {
    return false;
  }
  if (availableToolIds && !availableToolIds.has(tool.id)) {
    return false;
  }
  return true;
}
