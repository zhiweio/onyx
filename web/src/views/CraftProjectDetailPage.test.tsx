import {
  render,
  screen,
  setupUser,
  waitFor,
  within,
} from "@tests/setup/test-utils";
import CraftProjectDetailPage from "@/views/CraftProjectDetailPage";
import type { CraftProject } from "@/lib/craft-projects/types";

const mockRouterPush = jest.fn();
const mockUseCraftProject = jest.fn();
const mockStartSession = jest.fn();
const mockRefreshHistory = jest.fn();
const mockRefresh = jest.fn();
const mockRefreshProjects = jest.fn();
const mockUpdateProject = jest.fn();
const mockResetSandbox = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockRouterPush }),
  usePathname: () => "/craft/v1/projects/proj-tax",
}));

jest.mock("@/lib/craft-projects/hooks", () => ({
  useCraftProject: () => mockUseCraftProject(),
  useRefreshCraftProjects: () => mockRefreshProjects,
}));

jest.mock("@/lib/craft-projects/api", () => ({
  startCraftProjectSession: (...args: unknown[]) => mockStartSession(...args),
  updateCraftProject: (...args: unknown[]) => mockUpdateProject(...args),
  resetCraftProjectSandbox: (...args: unknown[]) => mockResetSandbox(...args),
  deleteCraftProject: jest.fn(),
  deleteCraftProjectFile: jest.fn(),
  uploadCraftProjectFile: jest.fn(),
  fetchCraftProjectFileContent: jest.fn(async (_projectId, file) => {
    if (String(file?.name ?? "").endsWith(".md")) {
      return {
        status: "text",
        text: "# Claim map\n\n![Revenue](charts/revenue_q.png)\n\nPatent families follow.",
      };
    }
    if (String(file?.name ?? "").endsWith(".html")) {
      return {
        status: "text",
        text: "<html><body><h1>Report</h1></body></html>",
      };
    }
    return { status: "unsupported" };
  }),
  craftProjectFileUrl: (projectId: string, fileId: string) =>
    `/api/craft-projects/${projectId}/files/${fileId}`,
}));

jest.mock("@/sections/extend/file-upload", () => ({
  FileUpload: () => <div data-testid="file-upload" />,
}));

jest.mock("@/sections/document-preview", () => ({
  DocumentPreview: ({ fileName }: { fileName: string }) => (
    <div>{`Document preview for ${fileName}`}</div>
  ),
  resolveDocumentPreviewMode: () => "view",
  saveCraftProjectFileBytes: jest.fn(),
}));

jest.mock("@/sections/extend/file-system", () => ({
  FileSystem: ({
    items,
    onFileOpen,
  }: {
    items: Array<{
      kind: string;
      name: string;
      path: string;
      metadata?: { id?: string };
    }>;
    onFileOpen: (file: {
      kind: string;
      name: string;
      path: string;
      metadata?: { id?: string };
    }) => void;
  }) => {
    const { useState } = jest.requireActual("react") as typeof import("react");
    const [query, setQuery] = useState("");
    const visible = items.filter(
      (item) =>
        item.kind === "file" &&
        item.name.toLowerCase().includes(query.toLowerCase())
    );
    return (
      <div>
        <input
          placeholder="Search files"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        {visible.map((item) => {
          const folder = item.path.includes("/")
            ? item.path.split("/").slice(0, -1).join("/")
            : "";
          return (
            <div key={`${item.path}:${item.metadata?.id ?? item.name}`}>
              {folder ? <span>{folder}</span> : null}
              <button type="button" onClick={() => onFileOpen(item)}>
                {item.name}
              </button>
            </div>
          );
        })}
      </div>
    );
  },
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
    mockRefreshProjects.mockReset();
    mockUpdateProject.mockReset();
    mockResetSandbox.mockReset();
    mockRefreshHistory.mockResolvedValue(undefined);
    mockResetSandbox.mockResolvedValue({ ...project });
    mockRefreshProjects.mockResolvedValue(undefined);
    mockRefresh.mockResolvedValue(undefined);
    mockUpdateProject.mockResolvedValue({ ...project });
  });

  it("shows files, chats, and starts a new chat", async () => {
    const user = setupUser();
    mockStartSession.mockResolvedValue({ id: "session-new" });
    render(<CraftProjectDetailPage projectId="proj-tax" />);

    expect(screen.getAllByText("年报税务复核").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Tax review files").length).toBeGreaterThan(0);
    expect(screen.getByText("rates.xlsx")).toBeInTheDocument();
    expect(screen.getByText("Sandbox")).toBeInTheDocument();
    expect(screen.getByText("Not started")).toBeInTheDocument();
    expect(
      screen.getByText("The agent follows these rules in every chat in this project.")
    ).toBeInTheDocument();
    expect(
      screen.getByText("This text appears under the project name.")
    ).toBeInTheDocument();
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

    expect(
      screen.getByRole("button", { name: "Start chat" })
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "New chat" })
    ).not.toBeInTheDocument();
    expect(
      screen.getByText("Start a chat to work in this project.")
    ).toBeInTheDocument();
    expect(screen.queryByText("No chats yet")).not.toBeInTheDocument();
  });

  it("shows sandbox status between files and chats", () => {
    mockUseCraftProject.mockReturnValue({
      data: {
        ...project,
        sandbox: {
          id: "sandbox-1",
          status: "running",
          last_heartbeat: "2026-08-01T00:00:00Z",
          created_at: "2026-08-01T00:00:00Z",
        },
      },
      error: undefined,
      isLoading: false,
      refresh: mockRefresh,
    });
    render(<CraftProjectDetailPage projectId="proj-tax" />);

    const sandbox = screen.getByTestId("craft-project-sandbox");
    expect(sandbox).toHaveTextContent("Sandbox");
    expect(sandbox).toHaveTextContent("Running");
    expect(sandbox).toHaveTextContent("Ready for chats in this project.");
    expect(screen.getByRole("button", { name: "Reset" })).toBeInTheDocument();
  });

  it("resets the sandbox after confirmation", async () => {
    const user = setupUser();
    mockUseCraftProject.mockReturnValue({
      data: {
        ...project,
        sandbox: {
          id: "sandbox-old",
          status: "running",
          last_heartbeat: "2026-08-01T00:00:00Z",
          created_at: "2026-08-01T00:00:00Z",
        },
      },
      error: undefined,
      isLoading: false,
      refresh: mockRefresh,
    });
    render(<CraftProjectDetailPage projectId="proj-tax" />);

    await user.click(screen.getByRole("button", { name: "Reset" }));
    expect(
      screen.getByRole("dialog", { name: /Reset the sandbox/ })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("checkbox", {
        name: "Also copy every output file from the old sandbox",
      })
    ).not.toBeChecked();
    expect(mockResetSandbox).not.toHaveBeenCalled();

    await user.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Reset" })
    );
    await waitFor(() =>
      expect(mockResetSandbox).toHaveBeenCalledWith("proj-tax", false)
    );
    expect(
      screen.queryByRole("dialog", { name: /Reset the sandbox/ })
    ).not.toBeInTheDocument();
    await waitFor(() => expect(mockRefresh).toHaveBeenCalled());
  });

  it("closes the reset dialog while the sandbox is still starting", async () => {
    const user = setupUser();
    let finishReset: ((value: CraftProject) => void) | undefined;
    mockResetSandbox.mockImplementation(
      () =>
        new Promise<CraftProject>((resolve) => {
          finishReset = resolve;
        })
    );
    mockUseCraftProject.mockReturnValue({
      data: {
        ...project,
        sandbox: {
          id: "sandbox-old",
          status: "running",
          last_heartbeat: "2026-08-01T00:00:00Z",
          created_at: "2026-08-01T00:00:00Z",
        },
      },
      error: undefined,
      isLoading: false,
      refresh: mockRefresh,
    });
    render(<CraftProjectDetailPage projectId="proj-tax" />);

    await user.click(screen.getByRole("button", { name: "Reset" }));
    await user.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Reset" })
    );

    await waitFor(() =>
      expect(mockResetSandbox).toHaveBeenCalledWith("proj-tax", false)
    );
    expect(
      screen.queryByRole("dialog", { name: /Reset the sandbox/ })
    ).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(
      "Starting a new workspace. You can keep using this page."
    );
    expect(screen.getByRole("button", { name: "Resetting" })).toBeDisabled();

    finishReset?.({ ...project });
    await waitFor(() => expect(mockRefresh).toHaveBeenCalled());
  });

  it("can copy old sandbox outputs when the reset box is checked", async () => {
    const user = setupUser();
    mockUseCraftProject.mockReturnValue({
      data: {
        ...project,
        sandbox: {
          id: "sandbox-old",
          status: "running",
          last_heartbeat: "2026-08-01T00:00:00Z",
          created_at: "2026-08-01T00:00:00Z",
        },
      },
      error: undefined,
      isLoading: false,
      refresh: mockRefresh,
    });
    render(<CraftProjectDetailPage projectId="proj-tax" />);

    await user.click(screen.getByRole("button", { name: "Reset" }));
    await user.click(
      screen.getByRole("checkbox", {
        name: "Also copy every output file from the old sandbox",
      })
    );
    await user.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Reset" })
    );
    await waitFor(() =>
      expect(mockResetSandbox).toHaveBeenCalledWith("proj-tax", true)
    );
  });

  it("hides planned specialist chats and shows a finished job as idle", () => {
    mockUseCraftProject.mockReturnValue({
      data: {
        ...project,
        sessions: [
          {
            id: "session-main",
            name: "君禾股份财报分析",
            status: "ACTIVE",
            origin: "INTERACTIVE",
            job_status: "succeeded",
            has_active_turn: false,
            created_at: "2026-08-01T00:00:00Z",
            last_activity_at: "2026-08-02T00:00:00Z",
          },
          {
            id: "session-lane",
            name: "撰写一份 GLP-1 立项深度研究报告 / literature",
            status: "ACTIVE",
            origin: "JOB",
            job_status: null,
            has_active_turn: false,
            created_at: "2026-08-01T00:00:00Z",
            last_activity_at: "2026-08-01T00:00:00Z",
          },
        ],
        session_count: 1,
      },
      error: undefined,
      isLoading: false,
      refresh: mockRefresh,
    });
    render(<CraftProjectDetailPage projectId="proj-tax" />);

    expect(screen.getByText("君禾股份财报分析")).toBeInTheDocument();
    expect(screen.getByText("Idle")).toBeInTheDocument();
    expect(screen.queryByText("Literature")).not.toBeInTheDocument();
    expect(screen.queryByText("Active")).not.toBeInTheDocument();
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
      "撰写一份 GLP-1 受体激动剂创新药立项深度研究报告，覆盖文献、临床、专利自由实施与 CMC 质量。"
    );
    expect(header).not.toHaveTextContent("blackboard");
  });

  it("asks for confirmation before renaming from the title", async () => {
    const user = setupUser();
    render(<CraftProjectDetailPage projectId="proj-tax" />);

    await user.click(
      within(screen.getByLabelText("admin-page-title")).getByText(
        "年报税务复核"
      )
    );
    const input = screen.getByDisplayValue("年报税务复核");
    await user.clear(input);
    await user.type(input, "税务复核 2026");
    await user.keyboard("{Enter}");

    expect(
      screen.getByRole("dialog", {
        name: /Use the name "税务复核 2026"\?/,
      })
    ).toBeInTheDocument();
    expect(mockUpdateProject).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Rename" }));
    await waitFor(() =>
      expect(mockUpdateProject).toHaveBeenCalledWith("proj-tax", {
        name: "税务复核 2026",
      })
    );
  });

  it("does not rename when the confirmation is cancelled", async () => {
    const user = setupUser();
    render(<CraftProjectDetailPage projectId="proj-tax" />);

    await user.click(
      within(screen.getByLabelText("admin-page-title")).getByText(
        "年报税务复核"
      )
    );
    const input = screen.getByDisplayValue("年报税务复核");
    await user.clear(input);
    await user.type(input, "税务复核 2026");
    await user.keyboard("{Enter}");

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(mockUpdateProject).not.toHaveBeenCalled();
    expect(
      screen.queryByRole("dialog", {
        name: /Use the name "税务复核 2026"\?/,
      })
    ).not.toBeInTheDocument();
  });

  it("opens a preview for a file and hides type filters", async () => {
    const user = setupUser();
    render(<CraftProjectDetailPage projectId="proj-tax" />);

    expect(
      screen.queryByRole("button", { name: "Tables" })
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Markdown" })
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "All" })
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /rates\.xlsx/ }));
    const preview = await screen.findByTestId("craft-project-file-preview");
    expect(preview).toBeInTheDocument();
    expect(
      screen.getByText("Document preview for rates.xlsx")
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

  it("resolves markdown images to project files", async () => {
    const user = setupUser();
    mockUseCraftProject.mockReturnValue({
      data: {
        ...project,
        files: [
          {
            ...project.files![0],
            id: "file-md",
            path: "/君禾股份_财报解读_2026H1.md",
            name: "君禾股份_财报解读_2026H1.md",
            mime_type: "text/markdown",
            source: "session_output",
          },
          {
            ...project.files![0],
            id: "file-png",
            path: "/charts/revenue_q.png",
            name: "revenue_q.png",
            mime_type: "image/png",
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

    await user.click(
      screen.getByRole("button", { name: /君禾股份_财报解读_2026H1\.md/ })
    );
    const image = await screen.findByRole("img", { name: "Revenue" });
    expect(image).toHaveAttribute(
      "src",
      "/api/craft-projects/proj-tax/files/file-png"
    );
  });

  it("previews HTML in a sandboxed iframe", async () => {
    const user = setupUser();
    mockUseCraftProject.mockReturnValue({
      data: {
        ...project,
        files: [
          {
            ...project.files![0],
            id: "file-html",
            path: "/君禾股份_财报解读_2026H1.html",
            name: "君禾股份_财报解读_2026H1.html",
            mime_type: "text/html",
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

    await user.click(
      screen.getByRole("button", { name: /君禾股份_财报解读_2026H1\.html/ })
    );
    const iframe = await screen.findByTitle(
      "HTML preview: 君禾股份_财报解读_2026H1.html"
    );
    expect(iframe.tagName).toBe("IFRAME");
    expect(iframe).toHaveAttribute(
      "srcDoc",
      "<html><body><h1>Report</h1></body></html>"
    );
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
