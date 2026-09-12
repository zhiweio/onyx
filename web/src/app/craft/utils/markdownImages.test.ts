import { buildArtifactUrl } from "@/app/craft/services/apiServices";
import {
  makeMarkdownPreviewUrlTransform,
  resolveWorkspaceMarkdownPath,
} from "@/app/craft/utils/markdownImages";

const MD = "outputs/markdown/clinical-initiation-report.md";

describe("resolveWorkspaceMarkdownPath", () => {
  it("resolves a sibling figure path", () => {
    expect(
      resolveWorkspaceMarkdownPath("figures/competitor_timeline.png", MD)
    ).toBe("outputs/markdown/figures/competitor_timeline.png");
  });

  it("resolves a sandbox:// URI", () => {
    expect(
      resolveWorkspaceMarkdownPath(
        "sandbox://outputs/markdown/figures/competitor_timeline.png",
        MD
      )
    ).toBe("outputs/markdown/figures/competitor_timeline.png");
  });

  it("keeps a workspace-rooted path", () => {
    expect(
      resolveWorkspaceMarkdownPath(
        "outputs/markdown/figures/competitor_timeline.png",
        MD
      )
    ).toBe("outputs/markdown/figures/competitor_timeline.png");
  });

  it("rejects remote URLs and workspace escapes", () => {
    expect(
      resolveWorkspaceMarkdownPath("https://example.com/a.png", MD)
    ).toBeNull();
    expect(resolveWorkspaceMarkdownPath("../../../etc/passwd", MD)).toBeNull();
  });
});

describe("makeMarkdownPreviewUrlTransform", () => {
  it("rewrites local images to the artifact URL", () => {
    const transform = makeMarkdownPreviewUrlTransform("sess-1", MD);
    expect(transform("figures/competitor_timeline.png")).toBe(
      buildArtifactUrl(
        "sess-1",
        "outputs/markdown/figures/competitor_timeline.png"
      )
    );
    expect(
      transform("sandbox://outputs/markdown/figures/competitor_timeline.png")
    ).toBe(
      buildArtifactUrl(
        "sess-1",
        "outputs/markdown/figures/competitor_timeline.png"
      )
    );
  });

  it("still blocks javascript URLs", () => {
    const transform = makeMarkdownPreviewUrlTransform("sess-1", MD);
    expect(transform("javascript:alert(1)")).toBeNull();
  });

  it("keeps https links", () => {
    const transform = makeMarkdownPreviewUrlTransform("sess-1", MD);
    expect(transform("https://example.com/a.png")).toBe(
      "https://example.com/a.png"
    );
  });
});
