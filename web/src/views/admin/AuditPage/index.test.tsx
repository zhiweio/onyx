import { render, screen, setupUser, waitFor } from "@tests/setup/test-utils";
import AuditPage from "@/views/admin/AuditPage";
import {
  fetchAuditApprovals,
  fetchAuditQueryHistory,
  fetchAuditQuarantines,
  fetchAuditToolCalls,
  fetchAuditUsage,
} from "@/views/admin/AuditPage/api";

jest.mock("next/navigation", () => ({
  useRouter: () => ({
    push: jest.fn(),
    replace: jest.fn(),
    prefetch: jest.fn(),
    back: jest.fn(),
  }),
  useSearchParams: () => new URLSearchParams(),
}));

jest.mock("@/views/admin/AuditPage/api", () => ({
  ...jest.requireActual("@/views/admin/AuditPage/api"),
  fetchAuditToolCalls: jest.fn(),
  fetchAuditApprovals: jest.fn(),
  fetchAuditQuarantines: jest.fn(),
  fetchAuditQueryHistory: jest.fn(),
  fetchAuditUsage: jest.fn(),
  downloadCsv: jest.fn(),
}));

const mockedToolCalls = fetchAuditToolCalls as jest.Mock;
const mockedApprovals = fetchAuditApprovals as jest.Mock;
const mockedQuarantines = fetchAuditQuarantines as jest.Mock;
const mockedHistory = fetchAuditQueryHistory as jest.Mock;
const mockedUsage = fetchAuditUsage as jest.Mock;

function seedResponses() {
  mockedToolCalls.mockResolvedValue({
    items: [
      {
        id: 1,
        user: "admin@example.com",
        session_id: null,
        tool: "rag_search",
        arguments: { query: "wifi" },
        ok: true,
        result_excerpt: "found 3 docs",
        duration_ms: 120,
        created_at: "2026-09-01T10:00:00Z",
      },
    ],
    total_items: 1,
    stats: [{ tool: "rag_search", calls: 1, failures: 0, avg_ms: 120 }],
  });
  mockedApprovals.mockResolvedValue({ items: [], total_items: 0 });
  mockedQuarantines.mockResolvedValue({ items: [], total_items: 0 });
  mockedHistory.mockResolvedValue({ items: [], total_items: 0 });
  mockedUsage.mockResolvedValue({
    days: 7,
    search_queries: 12,
    active_users: 3,
    tool_calls: 9,
  });
}

describe("AuditPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    seedResponses();
  });

  test("renders tabs, date toolbar, and the tool calls table", async () => {
    render(<AuditPage />);

    expect(screen.getByTestId("audit-tab-tools")).toBeInTheDocument();
    expect(screen.getByTestId("audit-tab-approvals")).toBeInTheDocument();
    expect(screen.getByTestId("audit-tab-history")).toBeInTheDocument();
    expect(screen.getByTestId("audit-refresh")).toBeInTheDocument();

    const search = await screen.findByTestId("audit-tool-calls-search");
    expect(search).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText("admin@example.com")).toBeInTheDocument()
    );
    expect(mockedToolCalls).toHaveBeenCalled();
  });

  test("switching tabs loads the query history table", async () => {
    const user = setupUser();
    render(<AuditPage />);

    await screen.findByTestId("audit-tool-calls-search");
    await user.click(screen.getByTestId("audit-tab-history"));

    expect(
      await screen.findByTestId("audit-history-search")
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("audit-tool-calls-search")
    ).not.toBeInTheDocument();
    expect(mockedHistory).toHaveBeenCalled();
  });
});
