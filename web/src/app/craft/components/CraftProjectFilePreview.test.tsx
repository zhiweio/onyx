import { render, screen } from "@tests/setup/test-utils";
import CraftProjectFilePreview from "@/app/craft/components/CraftProjectFilePreview";
import { fetchCraftProjectFileContent } from "@/lib/craft-projects/api";
import type { CraftProjectFile } from "@/lib/craft-projects/types";

jest.mock("@/lib/craft-projects/api", () => ({
  fetchCraftProjectFileContent: jest.fn(),
  deleteCraftProjectFile: jest.fn(),
  craftProjectFileUrl: (projectId: string, fileId: string) =>
    `/api/craft-projects/${projectId}/files/${fileId}`,
}));

jest.mock("@/sections/document-preview", () => ({
  DocumentPreview: ({ fileName }: { fileName: string }) => (
    <div>{`Document preview for ${fileName}`}</div>
  ),
  resolveDocumentPreviewMode: () => "view",
  saveCraftProjectFileBytes: jest.fn(),
}));

function file(
  overrides: Partial<CraftProjectFile> &
    Pick<CraftProjectFile, "id" | "name" | "path">
): CraftProjectFile {
  return {
    project_id: "proj-tax",
    mime_type: null,
    size_bytes: 12,
    content_hash: "abc",
    source: "session_output",
    produced_by_session_id: null,
    version: 1,
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
    ...overrides,
  };
}

const markdownFile = file({
  id: "file-md",
  path: "/君禾股份_财报解读_2026H1.md",
  name: "君禾股份_财报解读_2026H1.md",
  mime_type: "text/markdown",
});

const chartFile = file({
  id: "file-png",
  path: "/charts/revenue_q.png",
  name: "revenue_q.png",
  mime_type: "image/png",
});

const htmlFile = file({
  id: "file-html",
  path: "/君禾股份_财报解读_2026H1.html",
  name: "君禾股份_财报解读_2026H1.html",
  mime_type: "text/html",
});

describe("CraftProjectFilePreview", () => {
  beforeEach(() => {
    jest.mocked(fetchCraftProjectFileContent).mockReset();
  });

  it("resolves markdown images to project files", async () => {
    jest.mocked(fetchCraftProjectFileContent).mockResolvedValue({
      status: "text",
      text: "# Claim map\n\n![Revenue](charts/revenue_q.png)\n",
    });

    render(
      <CraftProjectFilePreview
        projectId="proj-tax"
        files={[markdownFile, chartFile]}
        file={markdownFile}
        onClose={jest.fn()}
        onSelect={jest.fn()}
        onChanged={jest.fn()}
      />
    );

    const image = await screen.findByRole("img", { name: "Revenue" });
    expect(image).toHaveAttribute(
      "src",
      "/api/craft-projects/proj-tax/files/file-png"
    );
  });

  it("previews HTML in a sandboxed iframe", async () => {
    const html = "<html><body><h1>Report</h1></body></html>";
    jest.mocked(fetchCraftProjectFileContent).mockResolvedValue({
      status: "text",
      text: html,
    });

    render(
      <CraftProjectFilePreview
        projectId="proj-tax"
        files={[htmlFile]}
        file={htmlFile}
        onClose={jest.fn()}
        onSelect={jest.fn()}
        onChanged={jest.fn()}
      />
    );

    const iframe = await screen.findByTitle(
      "HTML preview: 君禾股份_财报解读_2026H1.html"
    );
    expect(iframe.tagName).toBe("IFRAME");
    expect(iframe).toHaveAttribute("srcDoc", html);
    expect(iframe).toHaveAttribute(
      "sandbox",
      "allow-scripts allow-popups allow-popups-to-escape-sandbox"
    );
  });
});
