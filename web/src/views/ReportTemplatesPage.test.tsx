import { render, screen, setupUser } from "@tests/setup/test-utils";
import ReportTemplatesPage from "@/views/ReportTemplatesPage";
import type { ReportTemplate } from "@/lib/report-templates/types";

const mockRouterPush = jest.fn();
const mockUseReportTemplates = jest.fn();
const mockRefresh = jest.fn();
const mockDeleteTemplate = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockRouterPush }),
}));

jest.mock("@/lib/report-templates/hooks", () => ({
  useReportTemplates: () => mockUseReportTemplates(),
}));

jest.mock("@/lib/report-templates/api", () => ({
  deleteReportTemplate: (...args: unknown[]) => mockDeleteTemplate(...args),
  ReportTemplateRequestError: class ReportTemplateRequestError extends Error {
    status: number;
    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  },
}));

function template(overrides: Partial<ReportTemplate> = {}): ReportTemplate {
  return {
    id: "tpl-compliance",
    slug: "compliance_risk",
    name: "合规风险预警",
    description: "Tax compliance",
    body: "# Body",
    kind: "MARKDOWN",
    placeholders: [],
    asset_filename: null,
    author_user_id: null,
    is_builtin: true,
    referenced_count: 1,
    can_edit: true,
    can_delete: false,
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
    ...overrides,
  };
}

describe("ReportTemplatesPage", () => {
  const compliance = template();
  const custom = template({
    id: "tpl-custom",
    slug: "my_brief",
    name: "My brief",
    description: "Personal outline",
    author_user_id: "owner-id",
    is_builtin: false,
    referenced_count: 0,
    can_delete: true,
  });

  beforeEach(() => {
    mockUseReportTemplates.mockReturnValue({
      data: [compliance, custom],
      error: undefined,
      isLoading: false,
      refresh: mockRefresh,
    });
    mockRouterPush.mockReset();
    mockRefresh.mockReset();
    mockDeleteTemplate.mockReset();
  });

  it("lists templates and opens the composer", async () => {
    const user = setupUser();
    render(<ReportTemplatesPage />);

    expect(screen.getAllByText("合规风险预警").length).toBeGreaterThan(0);
    expect(screen.getAllByText("My brief").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "New template" }));
    expect(mockRouterPush).toHaveBeenCalledWith(
      "/craft/v1/report-templates/new",
    );
  });

  it("filters by search", async () => {
    const user = setupUser();
    render(<ReportTemplatesPage />);

    await user.type(
      screen.getByPlaceholderText("Search templates..."),
      "my brief",
    );

    expect(screen.getAllByText("My brief").length).toBeGreaterThan(0);
    expect(screen.queryAllByText("合规风险预警")).toHaveLength(0);
  });
});
