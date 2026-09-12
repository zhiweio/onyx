import { render, screen, setupUser, waitFor } from "@tests/setup/test-utils";
import CraftProjectsPage from "@/views/CraftProjectsPage";
import type { CraftProject } from "@/lib/craft-projects/types";

const mockRouterPush = jest.fn();
const mockUseCraftProjects = jest.fn();
const mockStartSession = jest.fn();
const mockRefreshHistory = jest.fn();
const mockRefresh = jest.fn();
const mockCreateProject = jest.fn();
const mockDeleteProject = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockRouterPush }),
  usePathname: () => "/craft/v1/projects",
}));

jest.mock("@/lib/craft-projects/hooks", () => ({
  useCraftProjects: () => mockUseCraftProjects(),
}));

jest.mock("@/lib/craft-projects/api", () => ({
  createCraftProject: (...args: unknown[]) => mockCreateProject(...args),
  deleteCraftProject: (...args: unknown[]) => mockDeleteProject(...args),
  startCraftProjectSession: (...args: unknown[]) => mockStartSession(...args),
}));

jest.mock("@/app/craft/hooks/useBuildSessionStore", () => ({
  useBuildSessionStore: (
    selector: (state: { refreshSessionHistory: () => Promise<void> }) => unknown
  ) => selector({ refreshSessionHistory: mockRefreshHistory }),
}));

function project(overrides: Partial<CraftProject> = {}): CraftProject {
  return {
    id: "proj-tax",
    name: "年报税务复核",
    description: "Tax review files",
    instructions: "Keep citations.",
    file_count: 2,
    session_count: 1,
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
    ...overrides,
  };
}

describe("CraftProjectsPage", () => {
  const taxProject = project();
  const otherProject = project({
    id: "proj-biomed",
    name: "靶点文献整理",
    description: "Literature notes",
    file_count: 0,
    session_count: 0,
  });

  beforeEach(() => {
    mockUseCraftProjects.mockReturnValue({
      data: [taxProject, otherProject],
      error: undefined,
      isLoading: false,
      refresh: mockRefresh,
    });
    mockRouterPush.mockReset();
    mockStartSession.mockReset();
    mockRefreshHistory.mockReset();
    mockRefresh.mockReset();
    mockCreateProject.mockReset();
    mockDeleteProject.mockReset();
    mockRefreshHistory.mockResolvedValue(undefined);
    mockRefresh.mockResolvedValue(undefined);
  });

  it("hides implicit Untitled projects", () => {
    mockUseCraftProjects.mockReturnValue({
      data: [
        taxProject,
        project({
          id: "proj-untitled",
          name: "Untitled project",
          description: "",
          instructions: null,
        }),
      ],
      error: undefined,
      isLoading: false,
      refresh: mockRefresh,
    });
    render(<CraftProjectsPage />);
    expect(screen.getAllByText("年报税务复核").length).toBeGreaterThan(0);
    expect(screen.queryByText("Untitled project")).not.toBeInTheDocument();
  });

  it("lists projects and opens the composer", async () => {
    const user = setupUser();
    render(<CraftProjectsPage />);

    expect(screen.getAllByText("年报税务复核").length).toBeGreaterThan(0);
    expect(screen.getAllByText("靶点文献整理").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "New project" }));
    expect(screen.getByPlaceholderText("Project name")).toBeInTheDocument();
  });

  it("filters projects by search", async () => {
    const user = setupUser();
    render(<CraftProjectsPage />);

    await user.type(
      screen.getByPlaceholderText("Search projects..."),
      "literature"
    );
    expect(screen.getAllByText("靶点文献整理").length).toBeGreaterThan(0);
    expect(screen.queryByText("年报税务复核")).not.toBeInTheDocument();
  });

  it("starts a Craft chat from Continue", async () => {
    const user = setupUser();
    mockStartSession.mockResolvedValue({ id: "session-123" });
    render(<CraftProjectsPage />);

    expect(screen.getByRole("button", { name: "Continue" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start chat" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Continue" }));

    await waitFor(() =>
      expect(mockStartSession).toHaveBeenCalledWith("proj-tax", "年报税务复核")
    );
    await waitFor(() =>
      expect(mockRouterPush).toHaveBeenCalledWith(
        "/craft/v1?sessionId=session-123"
      )
    );
    expect(mockRefreshHistory).toHaveBeenCalled();
  });

  it("opens the project home from the card", async () => {
    const user = setupUser();
    render(<CraftProjectsPage />);

    await user.click(screen.getAllByText("年报税务复核")[0]!);

    expect(mockRouterPush).toHaveBeenCalledWith("/craft/v1/projects/proj-tax");
  });
});
