import { render, screen, setupUser, waitFor } from "@tests/setup/test-utils";
import CraftProjectDetailPage from "@/views/CraftProjectDetailPage";
import type { CraftProject } from "@/lib/craft-projects/types";

const mockRouterPush = jest.fn();
const mockUseCraftProject = jest.fn();
const mockStartSession = jest.fn();
const mockRefreshHistory = jest.fn();
const mockRefresh = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockRouterPush }),
  usePathname: () => "/craft/v1/projects/proj-tax",
}));

jest.mock("@/lib/craft-projects/hooks", () => ({
  useCraftProject: () => mockUseCraftProject(),
}));

jest.mock("@/lib/craft-projects/api", () => ({
  startCraftProjectSession: (...args: unknown[]) => mockStartSession(...args),
  updateCraftProject: jest.fn(),
  deleteCraftProject: jest.fn(),
  deleteCraftProjectFile: jest.fn(),
  uploadCraftProjectFile: jest.fn(),
  craftProjectFileUrl: (projectId: string, fileId: string) =>
    `/api/craft-projects/${projectId}/files/${fileId}`,
}));

jest.mock("@/app/craft/hooks/useBuildSessionStore", () => ({
  useBuildSessionStore: (
    selector: (state: { refreshSessionHistory: () => Promise<void> }) => unknown
  ) => selector({ refreshSessionHistory: mockRefreshHistory }),
}));

const project: CraftProject = {
  id: "proj-tax",
  name: "年报税务复核",
  description: "Tax review files",
  instructions: "Keep citations.",
  file_count: 1,
  session_count: 1,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
  files: [
    {
      id: "file-1",
      project_id: "proj-tax",
      path: "/rates.xlsx",
      name: "rates.xlsx",
      mime_type: "application/vnd.ms-excel",
      size_bytes: 12,
      content_hash: "abc",
      source: "upload",
      produced_by_session_id: null,
      version: 1,
      created_at: "2026-08-01T00:00:00Z",
      updated_at: "2026-08-01T00:00:00Z",
    },
  ],
  sessions: [
    {
      id: "session-1",
      name: "First pass",
      status: "IDLE",
      created_at: "2026-08-01T00:00:00Z",
      last_activity_at: "2026-08-01T00:00:00Z",
    },
  ],
};

describe("CraftProjectDetailPage", () => {
  beforeEach(() => {
    mockUseCraftProject.mockReturnValue({
      data: project,
      error: undefined,
      isLoading: false,
      refresh: mockRefresh,
    });
    mockRouterPush.mockReset();
    mockStartSession.mockReset();
    mockRefreshHistory.mockReset();
    mockRefresh.mockReset();
    mockRefreshHistory.mockResolvedValue(undefined);
  });

  it("shows files, chats, and starts a new chat", async () => {
    const user = setupUser();
    mockStartSession.mockResolvedValue({ id: "session-new" });
    render(<CraftProjectDetailPage projectId="proj-tax" />);

    expect(screen.getAllByText("年报税务复核").length).toBeGreaterThan(0);
    expect(screen.getByText("Tax review files")).toBeInTheDocument();
    expect(screen.getByText("rates.xlsx")).toBeInTheDocument();
    expect(screen.getByText("Uploaded")).toBeInTheDocument();
    expect(screen.getByText(/First pass/)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Continue" })
    ).not.toBeInTheDocument();
    expect(screen.queryByText("No chats yet")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "New chat" }));
    await waitFor(() =>
      expect(mockStartSession).toHaveBeenCalledWith("proj-tax", "年报税务复核")
    );
    await waitFor(() =>
      expect(mockRouterPush).toHaveBeenCalledWith(
        "/craft/v1?sessionId=session-new"
      )
    );
  });

  it("uses Start chat when the project has no chats", async () => {
    mockUseCraftProject.mockReturnValue({
      data: { ...project, sessions: [], session_count: 0 },
      error: undefined,
      isLoading: false,
      refresh: mockRefresh,
    });
    render(<CraftProjectDetailPage projectId="proj-tax" />);

    expect(screen.getByRole("button", { name: "Start chat" })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "New chat" })
    ).not.toBeInTheDocument();
    expect(
      screen.getByText("Start a chat to work in this project.")
    ).toBeInTheDocument();
    expect(screen.queryByText("No chats yet")).not.toBeInTheDocument();
  });
});
