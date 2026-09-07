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
  fetchCraftProjectFileContent: jest.fn(async (_projectId, file) => {
    if (String(file?.name ?? "").endsWith(".md")) {
      return {
        status: "text",
        text: "# Claim map\n\nPatent families follow.",
      };
    }
    return { status: "unsupported" };
  }),
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
    expect(screen.getByText(/Uploaded/)).toBeInTheDocument();
    expect(screen.getByText(/First pass/)).toBeInTheDocument();
    expect(screen.getByText("Idle")).toBeInTheDocument();
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

  it("shows a short lane title and a readable generated file name", () => {
    mockUseCraftProject.mockReturnValue({
      data: {
        ...project,
        files: [
          project.files![0],
          {
            ...project.files![0],
            id: "file-dump",
            path: "outputs/mcp/bash/1788711879701.json",
            name: "1788711879701.json",
            mime_type: "application/json",
            source: "session_output",
          },
        ],
        sessions: [
          {
            id: "session-lane",
            name: "撰写一份 GLP-1 立项深度研究报告 / literature",
            status: "ACTIVE",
            created_at: "2026-08-01T00:00:00Z",
            last_activity_at: "2026-08-01T00:00:00Z",
          },
        ],
        session_count: 1,
        file_count: 2,
      },
      error: undefined,
      isLoading: false,
      refresh: mockRefresh,
    });
    render(<CraftProjectDetailPage projectId="proj-tax" />);

    expect(screen.getByText("1788711879701.json")).toBeInTheDocument();
    expect(screen.getByText("outputs/mcp/bash")).toBeInTheDocument();
    expect(screen.getByText(/From chat/)).toBeInTheDocument();
    expect(screen.getByText("Literature")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(
      screen.queryByText(/撰写一份 GLP-1 立项深度研究报告 \/ literature/)
    ).not.toBeInTheDocument();
  });

  it("shortens a long job project name and hides blackboard", () => {
    mockUseCraftProject.mockReturnValue({
      data: {
        ...project,
        name: "撰写一份 GLP-1 受体激动剂创新药立项深度研究报告，覆盖文献、临床、专利自由实施与 CMC 质量。 blackboard",
        description: "",
      },
      error: undefined,
      isLoading: false,
      refresh: mockRefresh,
    });
    render(<CraftProjectDetailPage projectId="proj-tax" />);

    const header = screen.getByLabelText("admin-page-title");
    expect(header).toHaveTextContent(
      "撰写一份 GLP-1 受体激动剂创新药立项深度研究报告"
    );
    expect(header).not.toHaveTextContent("blackboard");
    expect(header).toHaveTextContent(
      "撰写一份 GLP-1 受体激动剂创新药立项深度研究报告，覆盖文献、临床、专利自由实施与 CMC 质量。"
    );
  });

  it("opens a preview for a file and hides type filters", async () => {
    const user = setupUser();
    render(<CraftProjectDetailPage projectId="proj-tax" />);

    expect(screen.queryByRole("button", { name: "Tables" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Markdown" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "All" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /rates\.xlsx/ }));
    const preview = await screen.findByTestId("craft-project-file-preview");
    expect(preview).toBeInTheDocument();
    expect(
      screen.getByText(
        "This file type cannot be previewed. Download it to view the contents."
      )
    ).toBeInTheDocument();
    expect(
      screen.getAllByRole("link", { name: "Download" }).length
    ).toBeGreaterThan(0);
  });

  it("renders markdown body text in the preview", async () => {
    const user = setupUser();
    mockUseCraftProject.mockReturnValue({
      data: {
        ...project,
        files: [
          {
            ...project.files![0],
            id: "file-md",
            path: "research/fto/claim-map.md",
            name: "claim-map.md",
            mime_type: "text/markdown",
            source: "session_output",
          },
        ],
        file_count: 1,
      },
      error: undefined,
      isLoading: false,
      refresh: mockRefresh,
    });
    render(<CraftProjectDetailPage projectId="proj-tax" />);

    await user.click(screen.getByRole("button", { name: /claim-map\.md/ }));
    const preview = await screen.findByTestId("craft-project-file-preview");
    expect(preview).toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { name: "Claim map" })
    ).toBeInTheDocument();
    expect(screen.getByText("Patent families follow.")).toBeInTheDocument();
  });

  it("filters the file list by search", async () => {
    const user = setupUser();
    mockUseCraftProject.mockReturnValue({
      data: {
        ...project,
        files: [
          project.files![0],
          {
            ...project.files![0],
            id: "file-md",
            path: "outputs/markdown/claim-map.md",
            name: "claim-map.md",
            mime_type: "text/markdown",
            source: "session_output",
          },
        ],
        file_count: 2,
      },
      error: undefined,
      isLoading: false,
      refresh: mockRefresh,
    });
    render(<CraftProjectDetailPage projectId="proj-tax" />);

    expect(screen.getByText("rates.xlsx")).toBeInTheDocument();
    expect(screen.getByText("claim-map.md")).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText("Search files"), "claim");
    expect(screen.queryByText("rates.xlsx")).not.toBeInTheDocument();
    expect(screen.getByText("claim-map.md")).toBeInTheDocument();
  });
});
