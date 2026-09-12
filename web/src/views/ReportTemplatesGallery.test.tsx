import { render, screen, setupUser, waitFor } from "@tests/setup/test-utils";
import ReportTemplatesPage from "@/views/ReportTemplatesPage";
import type { ReportTemplate } from "@/lib/report-templates/types";
import type { SystemReportTemplateItem } from "@/lib/system-catalog/types";

const mockRouterPush = jest.fn();
const mockUseReportTemplates = jest.fn();
const mockRefresh = jest.fn();
const mockUseGalleryTemplates = jest.fn();
const mockForkGalleryItem = jest.fn();
const mockToastSuccess = jest.fn();
const mockToastError = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockRouterPush }),
  usePathname: () => "/craft/v1/report-templates",
}));

jest.mock("@/lib/report-templates/hooks", () => ({
  useReportTemplates: () => mockUseReportTemplates(),
}));

jest.mock("@/lib/report-templates/api", () => ({
  deleteReportTemplate: jest.fn(),
  ReportTemplateRequestError: class extends Error {
    status = 500;
  },
}));

jest.mock("@/lib/system-catalog/hooks", () => ({
  useGalleryReportTemplates: (enabled: boolean) =>
    mockUseGalleryTemplates(enabled),
  useGalleryItem: () => ({
    data: undefined,
    error: undefined,
    isLoading: true,
  }),
}));

jest.mock("@/lib/system-catalog/api", () => ({
  forkGalleryItem: (...args: unknown[]) => mockForkGalleryItem(...args),
}));

jest.mock("@opal/layouts", () => {
  const actual = jest.requireActual("@opal/layouts");
  return {
    ...actual,
    toast: {
      success: (...args: unknown[]) => mockToastSuccess(...args),
      error: (...args: unknown[]) => mockToastError(...args),
    },
  };
});

function ownedTemplate(): ReportTemplate {
  return {
    id: "tpl-mine",
    slug: "my_template",
    name: "My template",
    description: "Owned by me",
    body: "# Mine",
    kind: "MARKDOWN",
    asset_filename: null,
    author_user_id: "user-1",
    is_builtin: false,
    referenced_count: 0,
    can_edit: true,
    can_delete: true,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
  };
}

function galleryTemplate(): SystemReportTemplateItem {
  return {
    id: "cat-monthly-close",
    slug: "monthly_close",
    name: "Monthly close report",
    description: "Period close structure",
    body: "# Monthly close",
    kind: "MARKDOWN",
    asset_filename: null,
    category: "TAX",
    tags: ["close"],
    publish_status: "PUBLISHED",
    version: 3,
    changelog: "Added exceptions section",
    origin: "BUILTIN",
    published_at: "2026-09-01T00:00:00Z",
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
  };
}

describe("ReportTemplatesPage gallery tab", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseReportTemplates.mockReturnValue({
      data: [ownedTemplate()],
      error: undefined,
      isLoading: false,
      refresh: mockRefresh,
    });
    mockUseGalleryTemplates.mockReturnValue({
      data: [galleryTemplate()],
      error: undefined,
      isLoading: false,
      refresh: jest.fn(),
    });
    mockForkGalleryItem.mockResolvedValue({
      id: "tpl-copy",
      name: "Monthly close report",
    });
  });

  it("shows the user's own templates first and hides gallery entries", () => {
    render(<ReportTemplatesPage />);

    expect(screen.getAllByText("My template").length).toBeGreaterThan(0);
    expect(screen.queryAllByText("Monthly close report")).toHaveLength(0);
    // The gallery request stays unarmed until the tab is opened.
    expect(mockUseGalleryTemplates).toHaveBeenCalledWith(false);
  });

  it("switches to the gallery tab and lists published entries", async () => {
    const user = setupUser();
    render(<ReportTemplatesPage />);

    await user.click(screen.getByRole("tab", { name: "Gallery" }));

    expect(
      (await screen.findAllByText("Monthly close report")).length,
    ).toBeGreaterThan(0);
    expect(screen.queryAllByText("My template")).toHaveLength(0);
    expect(mockUseGalleryTemplates).toHaveBeenLastCalledWith(true);
  });

  it("hides the create button while the gallery tab is open", async () => {
    const user = setupUser();
    render(<ReportTemplatesPage />);

    expect(screen.getByRole("button", { name: /new template/i })).toBeVisible();

    await user.click(screen.getByRole("tab", { name: "Gallery" }));

    expect(
      screen.queryByRole("button", { name: /new template/i }),
    ).not.toBeInTheDocument();
  });

  it("forks an entry, refreshes the list and returns to the mine tab", async () => {
    const user = setupUser();
    render(<ReportTemplatesPage />);

    await user.click(screen.getByRole("tab", { name: "Gallery" }));
    await screen.findAllByText("Monthly close report");

    await user.click(
      screen.getByRole("button", { name: "Copy to my library" }),
    );

    await waitFor(() => {
      expect(mockForkGalleryItem).toHaveBeenCalledWith(
        "report-templates",
        "cat-monthly-close",
      );
    });
    await waitFor(() => expect(mockRefresh).toHaveBeenCalled());
    expect(mockToastSuccess).toHaveBeenCalled();
    // A fresh copy belongs to the user, so land them where they can edit it.
    expect((await screen.findAllByText("My template")).length).toBeGreaterThan(
      0,
    );
  });

  it("reports a failed fork and stays on the gallery tab", async () => {
    const user = setupUser();
    mockForkGalleryItem.mockRejectedValue(new Error("nope"));
    render(<ReportTemplatesPage />);

    await user.click(screen.getByRole("tab", { name: "Gallery" }));
    await screen.findAllByText("Monthly close report");

    await user.click(
      screen.getByRole("button", { name: "Copy to my library" }),
    );

    await waitFor(() => expect(mockToastError).toHaveBeenCalled());
    expect(mockRefresh).not.toHaveBeenCalled();
    expect(screen.getAllByText("Monthly close report").length).toBeGreaterThan(
      0,
    );
  });
});
