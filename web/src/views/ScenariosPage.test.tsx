import { render, screen, setupUser, waitFor } from "@tests/setup/test-utils";
import ScenariosPage from "@/views/ScenariosPage";
import type { Scenario } from "@/lib/scenarios/types";
import type { SkillsList } from "@/lib/skills/types";

const mockRouterPush = jest.fn();
const mockUseScenarios = jest.fn();
const mockUseUserSkills = jest.fn();
const mockStartScenarioRun = jest.fn();
const mockRefreshHistory = jest.fn();
const mockRefresh = jest.fn();
const mockDuplicateScenario = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockRouterPush }),
}));

jest.mock("@/hooks/useScenarios", () => ({
  __esModule: true,
  default: () => mockUseScenarios(),
}));

jest.mock("@/hooks/useUserSkills", () => ({
  __esModule: true,
  default: () => mockUseUserSkills(),
}));

jest.mock("@/lib/scenarios/run", () => ({
  startScenarioRun: (...args: unknown[]) => mockStartScenarioRun(...args),
}));

jest.mock("@/lib/scenarios/api", () => ({
  deleteScenario: jest.fn(),
  duplicateScenario: (...args: unknown[]) => mockDuplicateScenario(...args),
}));

jest.mock("@/app/craft/hooks/useBuildSessionStore", () => ({
  useBuildSessionStore: (
    selector: (state: { refreshSessionHistory: () => Promise<void> }) => unknown
  ) => selector({ refreshSessionHistory: mockRefreshHistory }),
}));

jest.mock("@/sections/modals/scenarios/ShareScenarioModal", () => ({
  __esModule: true,
  default: () => null,
}));

function pack(overrides: Partial<Scenario> = {}): Scenario {
  return {
    id: "pack-tax",
    name: "合规风险预警",
    description: "Tax compliance pack",
    author_user_id: "owner-id",
    public_permission: "VIEWER",
    rules: { domain: "tax" },
    report_template: "compliance_risk",
    skill_ids: ["skill-tax-1", "skill-tax-2"],
    skills: [
      { skill_id: "skill-tax-1", sort_order: 0 },
      { skill_id: "skill-tax-2", sort_order: 1 },
    ],
    access_level: "OWNER",
    shared_user_ids: [],
    shared_group_ids: [],
    ...overrides,
  };
}

function skills(): SkillsList {
  return {
    builtins: [
      {
        source: "builtin",
        id: "skill-tax-1",
        name: "tax-compliance",
        description: "Tax compliance",
        is_available: true,
        unavailable_reason: null,
        is_valid: true,
        is_personal: false,
        enabled: true,
        can_toggle: false,
        author_user_id: null,
        author_email: null,
        owner: null,
        ownership_vacant: false,
        created_at: null,
        updated_at: null,
        user_shares: [],
        group_shares: [],
        public_permission: "VIEWER",
        user_permission: null,
        external_app: null,
      },
      {
        source: "builtin",
        id: "skill-lit",
        name: "biomed-literature",
        description: "Literature",
        is_available: true,
        unavailable_reason: null,
        is_valid: true,
        is_personal: false,
        enabled: true,
        can_toggle: false,
        author_user_id: null,
        author_email: null,
        owner: null,
        ownership_vacant: false,
        created_at: null,
        updated_at: null,
        user_shares: [],
        group_shares: [],
        public_permission: "VIEWER",
        user_permission: null,
        external_app: null,
      },
    ],
    customs: [],
  };
}

describe("ScenariosPage", () => {
  const taxPack = pack();
  const biomedPack = pack({
    id: "pack-biomed",
    name: "靶点文献与竞争格局",
    description: "Target landscape pack",
    rules: { domain: "biomed" },
    report_template: "target_landscape",
    skill_ids: ["skill-lit", "skill-tax-1"],
  });

  beforeEach(() => {
    mockUseScenarios.mockReturnValue({
      data: [taxPack, biomedPack],
      error: undefined,
      isLoading: false,
      refresh: mockRefresh,
    });
    mockUseUserSkills.mockReturnValue({
      data: skills(),
      error: undefined,
      isLoading: false,
      refresh: jest.fn(),
    });
    mockRouterPush.mockReset();
    mockStartScenarioRun.mockReset();
    mockRefreshHistory.mockReset();
    mockRefreshHistory.mockResolvedValue(undefined);
  });

  it("lists packs and opens the composer", async () => {
    const user = setupUser();
    render(<ScenariosPage />);

    expect(screen.getAllByText("合规风险预警").length).toBeGreaterThan(0);
    expect(screen.getAllByText("靶点文献与竞争格局").length).toBeGreaterThan(0);
    expect(screen.getAllByText("tax-compliance").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "New pack" }));
    expect(mockRouterPush).toHaveBeenCalledWith("/craft/v1/scenarios/new");
  });

  it("filters packs by domain and search", async () => {
    const user = setupUser();
    render(<ScenariosPage />);

    await user.click(screen.getByRole("button", { name: "Biomedicine" }));
    expect(screen.getAllByText("靶点文献与竞争格局").length).toBeGreaterThan(0);
    expect(screen.queryByText("合规风险预警")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "All" }));
    await user.type(screen.getByPlaceholderText("Search packs..."), "target");
    expect(screen.getAllByText("靶点文献与竞争格局").length).toBeGreaterThan(0);
    expect(screen.queryByText("合规风险预警")).not.toBeInTheDocument();
  });

  it("starts a Craft run with sessionId", async () => {
    const user = setupUser();
    mockStartScenarioRun.mockResolvedValue("session-123");
    render(<ScenariosPage />);

    const startButtons = screen.getAllByRole("button", { name: "Start run" });
    await user.click(startButtons[0]!);

    await waitFor(() =>
      expect(mockStartScenarioRun).toHaveBeenCalledWith(taxPack)
    );
    await waitFor(() =>
      expect(mockRouterPush).toHaveBeenCalledWith(
        "/craft/v1?sessionId=session-123"
      )
    );
    expect(mockRefreshHistory).toHaveBeenCalled();
  });

  it("opens the editor from the always-visible edit action", async () => {
    const user = setupUser();
    render(<ScenariosPage />);

    await user.click(screen.getAllByRole("button", { name: "Edit pack" })[0]!);

    expect(mockRouterPush).toHaveBeenCalledWith(
      "/craft/v1/scenarios/edit/pack-tax"
    );
  });
});
