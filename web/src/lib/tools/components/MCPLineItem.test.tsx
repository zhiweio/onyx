import { render, screen, setupUser } from "@tests/setup/test-utils";
import {
  MCPAuthenticationPerformer,
  MCPAuthenticationType,
  ToolSnapshot,
} from "@/lib/tools/types";
import MCPLineItem, { MCPServer } from "@/lib/tools/components/MCPLineItem";

const oauthServer: MCPServer = {
  id: 1,
  name: "Test MCP server",
  owner_email: "owner@example.com",
  server_url: "https://mcp.example.com",
  auth_type: MCPAuthenticationType.OAUTH,
  auth_performer: MCPAuthenticationPerformer.PER_USER,
  user_can_authenticate: false,
};

const tool: ToolSnapshot = {
  id: 1,
  name: "test_tool",
  display_name: "Test tool",
  description: "A test tool",
  definition: null,
  custom_headers: [],
  in_code_tool_id: null,
  passthrough_auth: false,
  enabled: true,
  chat_selectable: true,
  agent_creation_selectable: true,
  default_enabled: true,
};

interface RenderMCPLineItemOptions {
  isAuthenticated?: boolean;
  tools?: ToolSnapshot[];
}

function renderMCPLineItem({
  isAuthenticated = false,
  tools = [],
}: RenderMCPLineItemOptions = {}) {
  const onAuthenticate = jest.fn();
  const onSelect = jest.fn();

  render(
    <MCPLineItem
      server={oauthServer}
      isActive={false}
      onSelect={onSelect}
      onAuthenticate={onAuthenticate}
      tools={tools}
      enabledTools={tools}
      isAuthenticated={isAuthenticated}
      isLoading={false}
    />
  );

  return { onAuthenticate, onSelect };
}

function getTrailingIndicator(row: HTMLElement): HTMLElement {
  const indicators = row.querySelectorAll<HTMLElement>("[aria-hidden='true']");
  const indicator = indicators.item(indicators.length - 1);
  if (!indicator) throw new Error("Expected a trailing MCP row indicator.");
  return indicator;
}

describe("MCPLineItem", () => {
  it("authenticates once from either the row or key area", async () => {
    const user = setupUser();
    const { onAuthenticate, onSelect } = renderMCPLineItem();
    const row = screen.getByRole("button", { name: oauthServer.name });

    expect(screen.getAllByRole("button")).toHaveLength(1);
    await user.click(row);

    expect(onAuthenticate).toHaveBeenCalledTimes(1);
    expect(onSelect).not.toHaveBeenCalled();

    onAuthenticate.mockClear();
    await user.click(getTrailingIndicator(row));

    expect(onAuthenticate).toHaveBeenCalledTimes(1);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("authenticates once per keyboard activation", async () => {
    const user = setupUser();
    const { onAuthenticate, onSelect } = renderMCPLineItem();
    const row = screen.getByRole("button", { name: oauthServer.name });

    row.focus();
    await user.keyboard("{Enter}");

    expect(onAuthenticate).toHaveBeenCalledTimes(1);
    expect(onSelect).not.toHaveBeenCalled();

    await user.keyboard(" ");

    expect(onAuthenticate).toHaveBeenCalledTimes(2);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("selects once when the chevron area is clicked", async () => {
    const user = setupUser();
    const { onAuthenticate, onSelect } = renderMCPLineItem({
      isAuthenticated: true,
      tools: [tool],
    });
    const row = screen.getByRole("button", { name: oauthServer.name });

    await user.click(getTrailingIndicator(row));

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onAuthenticate).not.toHaveBeenCalled();
  });

  it("toggles the server without selecting it", async () => {
    const user = setupUser();
    const onAuthenticate = jest.fn();
    const onSelect = jest.fn();
    const onToggleEnabled = jest.fn();

    render(
      <MCPLineItem
        server={oauthServer}
        isActive={false}
        onSelect={onSelect}
        onAuthenticate={onAuthenticate}
        tools={[tool]}
        enabledTools={[]}
        isAuthenticated
        isLoading={false}
        onToggleEnabled={onToggleEnabled}
      />
    );

    await user.click(screen.getByRole("button", { name: "Enable" }));

    expect(onToggleEnabled).toHaveBeenCalledTimes(1);
    expect(onSelect).not.toHaveBeenCalled();
    expect(onAuthenticate).not.toHaveBeenCalled();
  });

  it("authenticates when an unauthenticated switch is turned on", async () => {
    const user = setupUser();
    const onAuthenticate = jest.fn();
    const onSelect = jest.fn();
    const onToggleEnabled = jest.fn();

    render(
      <MCPLineItem
        server={oauthServer}
        isActive={false}
        onSelect={onSelect}
        onAuthenticate={onAuthenticate}
        tools={[tool]}
        enabledTools={[]}
        isAuthenticated={false}
        isLoading={false}
        control="switch"
        onToggleEnabled={onToggleEnabled}
      />
    );

    await user.click(
      screen.getByRole("switch", { name: `Toggle ${oauthServer.name}` })
    );

    expect(onAuthenticate).toHaveBeenCalledTimes(1);
    expect(onToggleEnabled).not.toHaveBeenCalled();
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("can enable a server that has no tools on the agent", async () => {
    const user = setupUser();
    const onToggleEnabled = jest.fn();

    render(
      <MCPLineItem
        server={oauthServer}
        isActive={false}
        onSelect={jest.fn()}
        onAuthenticate={jest.fn()}
        tools={[]}
        enabledTools={[]}
        enabled={false}
        isAuthenticated
        isLoading={false}
        control="switch"
        onToggleEnabled={onToggleEnabled}
      />
    );

    const toggle = screen.getByRole("switch", {
      name: `Toggle ${oauthServer.name}`,
    });
    expect(toggle).not.toBeChecked();
    await user.click(toggle);
    expect(onToggleEnabled).toHaveBeenCalledTimes(1);
  });

  it("toggles a switch without selecting the server", async () => {
    const user = setupUser();
    const onAuthenticate = jest.fn();
    const onSelect = jest.fn();
    const onToggleEnabled = jest.fn();

    render(
      <MCPLineItem
        server={oauthServer}
        isActive={false}
        onSelect={onSelect}
        onAuthenticate={onAuthenticate}
        tools={[tool]}
        enabledTools={[tool]}
        isAuthenticated
        isLoading={false}
        control="switch"
        onToggleEnabled={onToggleEnabled}
      />
    );

    await user.click(
      screen.getByRole("switch", { name: `Toggle ${oauthServer.name}` })
    );

    expect(onToggleEnabled).toHaveBeenCalledTimes(1);
    expect(onSelect).not.toHaveBeenCalled();
    expect(onAuthenticate).not.toHaveBeenCalled();
  });
});
