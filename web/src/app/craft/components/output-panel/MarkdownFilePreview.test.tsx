import { render, screen } from "@tests/setup/test-utils";

import MarkdownFilePreview from "@/app/craft/components/output-panel/MarkdownFilePreview";
import { buildArtifactUrl } from "@/app/craft/services/apiServices";

const FILE_PATH = "outputs/markdown/clinical-initiation-report.md";

function renderPreview(content: string, sessionId?: string) {
  return render(
    <MarkdownFilePreview
      content={content}
      fileName="clinical-initiation-report.md"
      filePath={FILE_PATH}
      mimeType="text/markdown"
      isImage={false}
      sessionId={sessionId}
    />
  );
}

describe("MarkdownFilePreview", () => {
  it("rewrites a relative figure to the sandbox artifact URL", () => {
    renderPreview("![timeline](figures/competitor_timeline.png)\n", "sess-1");

    expect(screen.getByRole("img", { name: "timeline" })).toHaveAttribute(
      "src",
      buildArtifactUrl(
        "sess-1",
        "outputs/markdown/figures/competitor_timeline.png"
      )
    );
  });

  it("rewrites a sandbox:// figure URI", () => {
    renderPreview(
      "![timeline](sandbox://outputs/markdown/figures/competitor_timeline.png)\n",
      "sess-1"
    );

    expect(screen.getByRole("img", { name: "timeline" })).toHaveAttribute(
      "src",
      buildArtifactUrl(
        "sess-1",
        "outputs/markdown/figures/competitor_timeline.png"
      )
    );
  });
});
