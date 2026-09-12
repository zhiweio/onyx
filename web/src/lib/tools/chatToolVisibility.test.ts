import { FILE_READER_TOOL_ID, SEARCH_TOOL_ID } from "@/lib/tools/constants";
import { shouldShowBuiltInToolInChatMenu } from "@/lib/tools/chatToolVisibility";
import type { ToolSnapshot } from "@/lib/tools/types";

function tool(
  partial: Partial<ToolSnapshot> & Pick<ToolSnapshot, "id">
): ToolSnapshot {
  return {
    name: "tool",
    display_name: "Tool",
    description: "",
    definition: null,
    custom_headers: [],
    in_code_tool_id: null,
    passthrough_auth: false,
    enabled: true,
    chat_selectable: true,
    agent_creation_selectable: true,
    default_enabled: true,
    ...partial,
  };
}

describe("shouldShowBuiltInToolInChatMenu", () => {
  it("hides MCP tools, file reader, and unconfigured tools", () => {
    expect(
      shouldShowBuiltInToolInChatMenu({
        tool: tool({ id: 1, mcp_server_id: 9 }),
        availableToolIds: new Set([1]),
        currentProjectId: null,
        hasProjectFiles: false,
        hasNoConnectors: false,
      })
    ).toBe(false);

    expect(
      shouldShowBuiltInToolInChatMenu({
        tool: tool({ id: 2, in_code_tool_id: FILE_READER_TOOL_ID }),
        availableToolIds: new Set([2]),
        currentProjectId: null,
        hasProjectFiles: false,
        hasNoConnectors: false,
      })
    ).toBe(false);

    expect(
      shouldShowBuiltInToolInChatMenu({
        tool: tool({ id: 3, in_code_tool_id: "ImageGenerationTool" }),
        availableToolIds: new Set(),
        currentProjectId: null,
        hasProjectFiles: false,
        hasNoConnectors: false,
      })
    ).toBe(false);
  });

  it("shows project search only when the project has files", () => {
    const search = tool({ id: 4, in_code_tool_id: SEARCH_TOOL_ID });
    expect(
      shouldShowBuiltInToolInChatMenu({
        tool: search,
        availableToolIds: new Set([4]),
        currentProjectId: 12,
        hasProjectFiles: false,
        hasNoConnectors: true,
      })
    ).toBe(false);
    expect(
      shouldShowBuiltInToolInChatMenu({
        tool: search,
        availableToolIds: new Set([4]),
        currentProjectId: 12,
        hasProjectFiles: true,
        hasNoConnectors: true,
      })
    ).toBe(true);
  });

  it("hides internal search when no connectors are configured", () => {
    expect(
      shouldShowBuiltInToolInChatMenu({
        tool: tool({ id: 5, in_code_tool_id: SEARCH_TOOL_ID }),
        availableToolIds: new Set([5]),
        currentProjectId: null,
        hasProjectFiles: false,
        hasNoConnectors: true,
      })
    ).toBe(false);
  });
});
