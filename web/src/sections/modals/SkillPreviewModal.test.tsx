import {
  fireEvent,
  render,
  screen,
  setupUser,
  waitFor,
} from "@tests/setup/test-utils";
import SkillPreviewModal from "@/sections/modals/SkillPreviewModal";
import type { SkillDetail } from "@/lib/skills/types";

const mockUseSWR = jest.fn();
const mockDownloadSkillBundle = jest.fn();
const mockReplaceUserSkillBundle = jest.fn();
const mockToastError = jest.fn();
const mockToastSuccess = jest.fn();

jest.mock("swr", () => ({
  __esModule: true,
  ...jest.requireActual("swr"),
  default: (...args: unknown[]) => mockUseSWR(...args),
}));

jest.mock("@/lib/skills/api", () => ({
  ...jest.requireActual("@/lib/skills/api"),
  downloadSkillBundle: (...args: unknown[]) => mockDownloadSkillBundle(...args),
  replaceUserSkillBundle: (...args: unknown[]) =>
    mockReplaceUserSkillBundle(...args),
}));

jest.mock("@opal/layouts/toast/store", () => ({
  toast: {
    error: (...args: unknown[]) => mockToastError(...args),
    success: (...args: unknown[]) => mockToastSuccess(...args),
  },
}));

function detail(overrides: Partial<SkillDetail> = {}): SkillDetail {
  return {
    source: "custom",
    id: "skill-id",
    name: "CRM lookup",
    description: "Looks up CRM records",
    is_available: null,
    unavailable_reason: null,
    is_valid: true,
    is_personal: false,
    enabled: true,
    can_toggle: true,
    author_user_id: "owner-id",
    author_email: "owner@example.com",
    owner: { id: "owner-id", email: "owner@example.com" },
    ownership_vacant: false,
    created_at: "2026-10-01T10:00:00Z",
    updated_at: "2026-10-02T10:00:00Z",
    user_shares: [],
    group_shares: [],
    public_permission: "VIEWER",
    user_permission: "VIEWER",
    external_app: null,
    instructions_markdown: "Look up the requested record.",
    files: [
      { path: "SKILL.md", size: 128 },
      { path: "scripts/run.py", size: 64 },
    ],
    ...overrides,
  };
}

function swrData(data: SkillDetail | undefined, overrides = {}) {
  return {
    data,
    error: undefined,
    isLoading: false,
    mutate: jest.fn(),
    ...overrides,
  };
}

describe("SkillPreviewModal", () => {
  beforeEach(() => {
    mockDownloadSkillBundle.mockReset();
    mockReplaceUserSkillBundle.mockReset();
    mockToastError.mockReset();
    mockToastSuccess.mockReset();
    mockUseSWR.mockReset();
    mockUseSWR.mockReturnValue(swrData(detail()));
  });

  it("explains when the associated external app must be connected", () => {
    mockUseSWR.mockReturnValue(
      swrData(
        detail({
          external_app: {
            external_app_id: 42,
            name: "Acme CRM",
            enabled: true,
            ready: false,
          },
        })
      )
    );

    render(<SkillPreviewModal open skillId="skill-id" onClose={jest.fn()} />);

    expect(screen.getByText("Skill unavailable")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Connect app “Acme CRM” from the Apps page to use this skill."
      )
    ).toBeInTheDocument();
  });

  it("does not warn when the associated external app is ready", () => {
    mockUseSWR.mockReturnValue(
      swrData(
        detail({
          external_app: {
            external_app_id: 42,
            name: "Acme CRM",
            enabled: true,
            ready: true,
          },
        })
      )
    );

    render(<SkillPreviewModal open skillId="skill-id" onClose={jest.fn()} />);

    expect(screen.queryByText("Skill unavailable")).not.toBeInTheDocument();
  });

  it("shows the full detail of a custom skill", () => {
    render(<SkillPreviewModal open skillId="skill-id" onClose={jest.fn()} />);

    expect(screen.getAllByText("Looks up CRM records").length).toBeGreaterThan(
      0
    );
    expect(screen.getByText("owner@example.com")).toBeInTheDocument();
    expect(
      screen.getByText("Everyone in the organization")
    ).toBeInTheDocument();
    expect(screen.getByText("Valid")).toBeInTheDocument();
    expect(
      screen.getByText("Look up the requested record.")
    ).toBeInTheDocument();
    expect(screen.getByText("SKILL.md")).toBeInTheDocument();
    // Nested files exist but stay hidden until their folder is expanded.
    expect(screen.getByText("scripts")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download ZIP" })).toBeEnabled();
    expect(
      screen.queryByRole("button", { name: "Upload new version" })
    ).not.toBeInTheDocument();
  });

  it("shows builtin skills as maintained by Onyx without edit metadata", () => {
    mockUseSWR.mockReturnValue(
      swrData(
        detail({
          source: "builtin",
          author_email: null,
          is_valid: null,
          public_permission: null,
        })
      )
    );

    render(<SkillPreviewModal open skillId="skill-id" onClose={jest.fn()} />);

    expect(screen.getByText("Onyx")).toBeInTheDocument();
    expect(screen.queryByText("Valid")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Everyone in the organization")
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Upload new version" })
    ).not.toBeInTheDocument();
  });

  it("downloads the skill bundle", async () => {
    const user = setupUser();
    mockDownloadSkillBundle.mockResolvedValueOnce(undefined);

    render(<SkillPreviewModal open skillId="skill-id" onClose={jest.fn()} />);

    await user.click(
      await screen.findByRole("button", { name: "Download ZIP" })
    );

    await waitFor(() =>
      expect(mockDownloadSkillBundle).toHaveBeenCalledWith(
        expect.objectContaining({ id: "skill-id", name: "CRM lookup" })
      )
    );
    expect(mockToastError).not.toHaveBeenCalled();
  });

  it("reports download failures", async () => {
    const user = setupUser();
    mockDownloadSkillBundle.mockRejectedValueOnce(new Error("Download broke"));

    render(<SkillPreviewModal open skillId="skill-id" onClose={jest.fn()} />);

    await user.click(
      await screen.findByRole("button", { name: "Download ZIP" })
    );

    await waitFor(() =>
      expect(mockToastError).toHaveBeenCalledWith("Download broke")
    );
  });

  it("lets editors replace the bundle with an uploaded ZIP", async () => {
    const mutate = jest.fn();
    const onUpdated = jest.fn();
    mockUseSWR.mockReturnValue(
      swrData(detail({ user_permission: "OWNER" }), { mutate })
    );
    mockReplaceUserSkillBundle.mockResolvedValueOnce(detail());
    const user = setupUser();
    render(
      <SkillPreviewModal
        open
        skillId="skill-id"
        onClose={jest.fn()}
        onUpdated={onUpdated}
      />
    );

    await user.click(
      await screen.findByRole("button", { name: "Upload new version" })
    );
    const file = new File(["zip"], "crm-lookup.zip");
    fireEvent.change(document.querySelector('input[type="file"]')!, {
      target: { files: [file] },
    });

    await waitFor(() =>
      expect(mockReplaceUserSkillBundle).toHaveBeenCalledWith("skill-id", file)
    );
    await waitFor(() =>
      expect(mockToastSuccess).toHaveBeenCalledWith(
        "Skill “CRM lookup” updated."
      )
    );
    await waitFor(() => expect(onUpdated).toHaveBeenCalledTimes(1));
  });

  it("reports bundle replacement failures", async () => {
    mockUseSWR.mockReturnValue(swrData(detail({ user_permission: "EDITOR" })));
    mockReplaceUserSkillBundle.mockRejectedValueOnce(
      new Error("Name mismatch")
    );
    const user = setupUser();
    render(<SkillPreviewModal open skillId="skill-id" onClose={jest.fn()} />);

    await user.click(
      await screen.findByRole("button", { name: "Upload new version" })
    );
    fireEvent.change(document.querySelector('input[type="file"]')!, {
      target: { files: [new File(["zip"], "crm-lookup.zip")] },
    });

    await waitFor(() =>
      expect(mockToastError).toHaveBeenCalledWith("Name mismatch")
    );
  });
});
