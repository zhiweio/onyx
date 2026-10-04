import { render, waitFor } from "@tests/setup/test-utils";
import MCPPageContent from "@/sections/actions/MCPPageContent";
import { MCPServerStatus, type MCPServer } from "@/lib/tools/types";

const mockUpdateMCPServerStatus = jest.fn();
const mockRefreshMCPServerTools = jest.fn();
const mockUpdateMCPServerEnabled = jest.fn();
const mockMutateMcpServers = jest.fn();
const mockRouterReplace = jest.fn();
const mockToastSuccess = jest.fn();
const mockToastError = jest.fn();

// Regression for onyx-dot-app/onyx#14346: the OAuth return URL
// (?server_id=N&trigger_fetch=true) must start exactly one tool fetch.
const mockSearchParams = new URLSearchParams({
  server_id: "7",
  trigger_fetch: "true",
});

jest.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mockRouterReplace, push: jest.fn() }),
  usePathname: () => "/admin/actions",
  useSearchParams: () => mockSearchParams,
}));

// Stable identity, like SWR's cached data. A fresh object per render would
// spin the component's own effects instead of testing the trigger effect.
const mockMcpData = { mcp_servers: [] };
let mockGalleryData: { mcp_servers: MCPServer[] } = { mcp_servers: [] };

jest.mock("@/lib/tools/hooks", () => ({
  useAdminMcpServers: () => ({
    mcpData: mockMcpData,
    isLoading: false,
    mutateMcpServers: mockMutateMcpServers,
  }),
  usePersonalMcpServers: () => ({
    mcpData: { mcp_servers: [] },
    isLoading: false,
    mutateMcpServers: mockMutateMcpServers,
  }),
  useGalleryMcpServers: () => ({
    mcpData: mockGalleryData,
    isLoading: false,
    mutateMcpServers: mockMutateMcpServers,
  }),
}));

jest.mock("@/lib/tools/svc", () => ({
  ...jest.requireActual("@/lib/tools/svc"),
  updateMCPServerStatus: (...args: unknown[]) =>
    mockUpdateMCPServerStatus(...args),
  refreshMCPServerTools: (...args: unknown[]) =>
    mockRefreshMCPServerTools(...args),
  updateMCPServerEnabled: (...args: unknown[]) =>
    mockUpdateMCPServerEnabled(...args),
  discoverEmptyMcpTools: () =>
    Promise.resolve({ refreshed: 0, failed: 0, errors: [] }),
}));

jest.mock("@opal/layouts", () => ({
  ...jest.requireActual("@opal/layouts"),
  toast: {
    success: (...args: unknown[]) => mockToastSuccess(...args),
    error: (...args: unknown[]) => mockToastError(...args),
    info: jest.fn(),
  },
}));

// Captures what the list hands each card, so tests can assert on the props
// (the per-user enable switch wiring) without rendering the real card.
const cardProps: Record<string, unknown>[] = [];
jest.mock("@/sections/actions/MCPActionCard", () => ({
  __esModule: true,
  default: (props: Record<string, unknown>) => {
    cardProps.push(props);
    return <div data-testid="mcp-action-card" />;
  },
}));
jest.mock("@/sections/actions/modals/MCPAuthenticationModal", () => ({
  __esModule: true,
  default: () => null,
}));
jest.mock("@/sections/actions/modals/AddMCPServerModal", () => ({
  __esModule: true,
  default: () => null,
}));
jest.mock("@/sections/actions/modals/DisconnectEntityModal", () => ({
  __esModule: true,
  default: () => null,
}));

beforeEach(() => {
  jest.clearAllMocks();
  mockUpdateMCPServerStatus.mockResolvedValue(undefined);
  mockRefreshMCPServerTools.mockResolvedValue([]);
  mockUpdateMCPServerEnabled.mockResolvedValue(undefined);
  mockMutateMcpServers.mockResolvedValue(undefined);
  mockGalleryData = { mcp_servers: [] };
  cardProps.length = 0;
});

test("gallery listing does not start a trigger_fetch tool refresh", async () => {
  render(<MCPPageContent variant="gallery" />);

  await new Promise((resolve) => setTimeout(resolve, 50));

  expect(mockUpdateMCPServerStatus).not.toHaveBeenCalled();
  expect(mockRefreshMCPServerTools).not.toHaveBeenCalled();
});

test("trigger_fetch query param fetches tools exactly once", async () => {
  render(<MCPPageContent />);

  await waitFor(() => expect(mockToastSuccess).toHaveBeenCalledTimes(1));
  // Give any stray second run time to land before asserting the counts.
  await new Promise((resolve) => setTimeout(resolve, 50));

  expect(mockUpdateMCPServerStatus).toHaveBeenCalledTimes(1);
  expect(mockUpdateMCPServerStatus).toHaveBeenCalledWith(
    7,
    MCPServerStatus.FETCHING_TOOLS,
    "admin"
  );
  expect(mockRefreshMCPServerTools).toHaveBeenCalledTimes(1);
  expect(mockRefreshMCPServerTools).toHaveBeenCalledWith(7, "admin");
  expect(mockToastSuccess).toHaveBeenCalledTimes(1);
  expect(mockToastError).not.toHaveBeenCalled();
  expect(mockRouterReplace).toHaveBeenCalledTimes(1);
});

test("gallery cards carry the per-user enable switch and route it to the unified endpoint", async () => {
  mockGalleryData = {
    mcp_servers: [
      {
        id: 9,
        name: "Org Server",
        server_url: "https://mcp.example.com/org",
        status: MCPServerStatus.CONNECTED,
        tool_count: 2,
        user_enabled: true,
        is_public: true,
        groups: [],
        users: [],
      } as unknown as MCPServer,
    ],
  };

  render(<MCPPageContent variant="gallery" />);

  const card = cardProps.find((props) => props.serverId === 9);
  expect(card).toBeDefined();
  expect(card?.userEnabled).toBe(true);
  const onServerEnabledToggle = card?.onServerEnabledToggle as (
    id: number,
    enabled: boolean
  ) => void;
  expect(typeof onServerEnabledToggle).toBe("function");

  await onServerEnabledToggle(9, false);

  await waitFor(() =>
    expect(mockUpdateMCPServerEnabled).toHaveBeenCalledWith(9, false)
  );
  expect(mockToastSuccess).toHaveBeenCalled();
});
