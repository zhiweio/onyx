import { craftProjectFileUrl } from "@/lib/craft-projects/api";
import {
  catalogPathCandidates,
  findProjectFileForWorkspacePath,
  makeProjectMarkdownPreviewUrlTransform,
  rewriteProjectHtmlForPreview,
} from "@/lib/craft-projects/previewUrls";
import type { CraftProjectFile } from "@/lib/craft-projects/types";

function file(
  overrides: Partial<CraftProjectFile> & Pick<CraftProjectFile, "id" | "path">
): CraftProjectFile {
  return {
    project_id: "proj",
    name: overrides.path.split("/").pop() ?? overrides.path,
    mime_type: null,
    size_bytes: 1,
    content_hash: null,
    source: "session_output",
    produced_by_session_id: null,
    version: 1,
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
    ...overrides,
  };
}

const chart = file({ id: "chart-1", path: "/charts/revenue_q.png" });

describe("project preview asset paths", () => {
  it("maps workspace-rooted outputs onto the project catalog", () => {
    expect(catalogPathCandidates("outputs/charts/revenue_q.png")).toEqual([
      "outputs/charts/revenue_q.png",
      "charts/revenue_q.png",
    ]);
    expect(
      findProjectFileForWorkspacePath(
        [chart],
        "outputs/charts/revenue_q.png"
      )?.id
    ).toBe("chart-1");
  });

  it("rewrites markdown images to the project file URL", () => {
    const transform = makeProjectMarkdownPreviewUrlTransform(
      "proj",
      "/君禾股份_财报解读_2026H1.md",
      [chart]
    );
    expect(transform("charts/revenue_q.png")).toBe(
      craftProjectFileUrl("proj", "chart-1")
    );
    expect(transform("https://example.com/a.png")).toBe(
      "https://example.com/a.png"
    );
  });

  it("rewrites relative HTML images to object URLs", async () => {
    const blob = new Blob(["png"], { type: "image/png" });
    const result = await rewriteProjectHtmlForPreview(
      '<html><body><img src="charts/revenue_q.png"></body></html>',
      "/君禾股份_财报解读_2026H1.html",
      "proj",
      [chart],
      async () => blob
    );
    expect(result.html).toContain("blob:");
    expect(result.html).not.toContain("charts/revenue_q.png");
    result.revoke();
  });

  it("leaves self-contained HTML unchanged", async () => {
    const html = '<html><body><img src="data:image/png;base64,AAA"></body></html>';
    const result = await rewriteProjectHtmlForPreview(
      html,
      "/report.html",
      "proj",
      [chart]
    );
    expect(result.html).toBe(html);
    result.revoke();
  });

  it("rewrites the same HTML more than once", async () => {
    const blob = new Blob(["png"], { type: "image/png" });
    const source = '<html><body><img src="charts/revenue_q.png"></body></html>';
    const first = await rewriteProjectHtmlForPreview(
      source,
      "/report.html",
      "proj",
      [chart],
      async () => blob
    );
    const second = await rewriteProjectHtmlForPreview(
      source,
      "/report.html",
      "proj",
      [chart],
      async () => blob
    );
    expect(first.html).toContain("blob:");
    expect(second.html).toContain("blob:");
    first.revoke();
    second.revoke();
  });
});
