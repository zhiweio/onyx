import { render, screen } from "@tests/setup/test-utils";

import HtmlFilePreview from "@/app/craft/components/output-panel/HtmlFilePreview";

describe("HtmlFilePreview", () => {
  it("renders HTML in a unique-origin iframe", () => {
    const html = "<html><body><h1>Report</h1></body></html>";

    render(
      <HtmlFilePreview
        content={html}
        fileName="君禾股份_财报解读_2026H1.html"
        filePath="outputs/君禾股份_财报解读_2026H1.html"
        mimeType="text/html"
        isImage={false}
      />
    );

    const iframe = screen.getByTitle(
      "HTML preview: 君禾股份_财报解读_2026H1.html"
    );
    expect(iframe.tagName).toBe("IFRAME");
    expect(iframe).toHaveAttribute("srcDoc", html);
    expect(iframe.getAttribute("sandbox")).toContain("allow-scripts");
    expect(iframe.getAttribute("sandbox")).not.toContain("allow-same-origin");
  });
});
