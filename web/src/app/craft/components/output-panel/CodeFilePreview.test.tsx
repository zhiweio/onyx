import { render, screen, waitFor } from "@tests/setup/test-utils";
import CodeFilePreview from "@/app/craft/components/output-panel/CodeFilePreview";

jest.mock("next/navigation", () => ({
  useRouter: () => ({ back: jest.fn(), push: jest.fn() }),
  usePathname: () => "/craft/v1",
  useSearchParams: () => ({ get: () => null, has: () => false }),
}));

const PYTHON = 'import json\n\ndef main():\n    return json.dumps({})\n';

describe("CodeFilePreview", () => {
  it("renders a line gutter and highlights a known language", async () => {
    render(<CodeFilePreview content={PYTHON} fileName="build.py"
        filePath="outputs/build.py"
        mimeType="text/x-python" isImage={false} />);

    // Gutter: 1-based line numbers for all four lines.
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();

    // The lazy highlighter colors python keywords once the chunk resolves.
    await waitFor(
      () => {
        expect(document.querySelector(".hljs-keyword")).not.toBeNull();
      },
      { timeout: 4000 }
    );
  });

  it("renders plain lines for an unregistered language", () => {
    render(<CodeFilePreview content={"just text\n"} fileName="notes.weird"
        filePath="outputs/notes.weird"
        mimeType="text/plain" isImage={false} />);

    expect(screen.getByText("just text")).toBeInTheDocument();
    expect(document.querySelector(".hljs-keyword")).toBeNull();
  });
});
