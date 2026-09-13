import { render, screen } from "@tests/setup/test-utils";

import { FilePreviewContent } from "@/app/craft/components/output-panel/FilePreviewContent";
import { fetchFileContent } from "@/app/craft/services/apiServices";

jest.mock("@/app/craft/services/apiServices", () => ({
  ...jest.requireActual("@/app/craft/services/apiServices"),
  fetchFileContent: jest.fn(),
}));

jest.mock("@/sections/document-preview", () => ({
  DocumentPreview: ({ fileName }: { fileName: string }) => (
    <div>{`Document preview for ${fileName}`}</div>
  ),
}));

describe("FilePreviewContent", () => {
  beforeEach(() => {
    jest.mocked(fetchFileContent).mockReset();
  });

  it("routes a legacy .ppt file directly to the document preview", () => {
    const filePath = "outputs/quarterly review.ppt";

    render(<FilePreviewContent sessionId="session-1" filePath={filePath} />);

    expect(
      screen.getByText("Document preview for quarterly review.ppt")
    ).toBeInTheDocument();
    expect(fetchFileContent).not.toHaveBeenCalled();
  });

  it("routes a Word file to the document preview", () => {
    const filePath = "outputs/君禾泵业报告.docx";

    render(<FilePreviewContent sessionId="session-1" filePath={filePath} />);

    expect(
      screen.getByText("Document preview for 君禾泵业报告.docx")
    ).toBeInTheDocument();
    expect(fetchFileContent).not.toHaveBeenCalled();
  });

  it("renders an HTML file in a sandboxed preview", async () => {
    const html = "<html><body><h1>Report</h1></body></html>";
    jest.mocked(fetchFileContent).mockResolvedValue({
      content: html,
      mimeType: "text/html",
      isImage: false,
    });

    render(
      <FilePreviewContent
        sessionId="session-1"
        filePath="outputs/君禾股份_财报解读_2026H1.html"
      />
    );

    const iframe = await screen.findByTitle(
      "HTML preview: 君禾股份_财报解读_2026H1.html"
    );
    expect(iframe).toHaveAttribute("srcDoc", html);
    expect(fetchFileContent).toHaveBeenCalledWith(
      "session-1",
      "outputs/君禾股份_财报解读_2026H1.html"
    );
  });

  it("does not mistake a compound extension for a presentation", async () => {
    jest.mocked(fetchFileContent).mockResolvedValue({
      content: "plain text",
      mimeType: "text/plain",
      isImage: false,
    });

    render(
      <FilePreviewContent
        sessionId="session-1"
        filePath="outputs/notes.ppt.txt"
      />
    );

    expect(await screen.findByText("plain text")).toBeInTheDocument();
    expect(fetchFileContent).toHaveBeenCalledWith(
      "session-1",
      "outputs/notes.ppt.txt"
    );
  });
});
