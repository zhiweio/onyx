import { render, screen, setupUser } from "@tests/setup/test-utils";
import {
  MCPAuthenticationPerformer,
  MCPAuthenticationType,
} from "@/lib/tools/types";
import ManageConnectionsView from "@/lib/tools/components/ManageConnectionsView";
import { MCPServer } from "@/lib/tools/components/MCPLineItem";

const deepWiki: MCPServer = {
  id: 1,
  name: "DeepWiki",
  owner_email: "owner@example.com",
  server_url: "https://mcp.example.com/deepwiki",
  auth_type: MCPAuthenticationType.NONE,
  auth_performer: MCPAuthenticationPerformer.ADMIN,
  user_can_authenticate: true,
};

const parallelSearch: MCPServer = {
  id: 2,
  name: "Parallel Search",
  owner_email: "owner@example.com",
  server_url: "https://mcp.example.com/parallel",
  auth_type: MCPAuthenticationType.NONE,
  auth_performer: MCPAuthenticationPerformer.ADMIN,
  user_can_authenticate: true,
};

function renderView({
  canManage = true,
  servers = [deepWiki, parallelSearch],
}: {
  canManage?: boolean;
  servers?: MCPServer[];
} = {}) {
  const onAuthenticate = jest.fn();
  const onBack = jest.fn();
  const onSelectServer = jest.fn();
  const onToggleServer = jest.fn();

  render(
    <ManageConnectionsView
      canManage={canManage}
      enabledToolsByServer={new Map()}
      mcpServerData={{}}
      onAuthenticate={onAuthenticate}
      onBack={onBack}
      onSelectServer={onSelectServer}
      onToggleServer={onToggleServer}
      servers={servers}
      toolsByServer={new Map()}
      enabledServerIds={new Set()}
    />
  );

  return { onAuthenticate, onBack, onSelectServer, onToggleServer };
}

describe("ManageConnectionsView", () => {
  it("shows search and a manage link to the user MCP library", () => {
    renderView();

    expect(screen.getByPlaceholderText("Search MCPs...")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Manage" })).toHaveAttribute(
      "href",
      "/craft/v1/mcp-actions"
    );
    expect(
      screen.getByRole("switch", { name: `Toggle ${deepWiki.name}` })
    ).toBeVisible();
  });

  it("hides the manage link without permission", () => {
    renderView({ canManage: false });

    expect(
      screen.queryByRole("link", { name: "Manage" })
    ).not.toBeInTheDocument();
  });

  it("filters servers by name", async () => {
    const user = setupUser();
    renderView();

    await user.type(screen.getByPlaceholderText("Search MCPs..."), "deep");

    expect(
      screen.getByRole("switch", { name: `Toggle ${deepWiki.name}` })
    ).toBeVisible();
    expect(
      screen.queryByRole("switch", { name: `Toggle ${parallelSearch.name}` })
    ).not.toBeInTheDocument();
  });

  it("keeps every server off until the user turns one on", async () => {
    const user = setupUser();
    const { onToggleServer } = renderView();

    const deepWikiSwitch = screen.getByRole("switch", {
      name: `Toggle ${deepWiki.name}`,
    });
    expect(deepWikiSwitch).not.toBeChecked();
    expect(
      screen.getByRole("switch", { name: `Toggle ${parallelSearch.name}` })
    ).not.toBeChecked();

    await user.click(deepWikiSwitch);
    expect(onToggleServer).toHaveBeenCalledWith(deepWiki.id, true);
  });
});
