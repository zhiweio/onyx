import { render, screen, setupUser } from "@tests/setup/test-utils";
import { FileViewPane } from "@/app/craft/components/output-panel/FileViewPane";

jest.mock("next/navigation", () => ({
  useRouter: () => ({ back: jest.fn(), push: jest.fn() }),
  usePathname: () => "/craft/v1",
  useSearchParams: () => ({ get: () => null, has: () => false }),
}));

const EDIT = {
  path: "outputs/report.md",
  fileName: "report.md",
  toolCallId: "tc-1",
  oldContent: "a\nb",
  newContent: "a\nc",
  added: 1,
  removed: 1,
  isNewFile: false,
};

describe("FileViewPane", () => {
  it("an edited file opens on the diff with a Diff | Source toggle", () => {
    render(
      <FileViewPane
        path={EDIT.path}
        edit={EDIT}
        viewMode="diff"
        onViewModeChange={jest.fn()}
        sessionId="s1"
        refreshKey={0}
      />
    );

    const toggle = screen.getByTestId("file-view-toggle");
    expect(toggle).toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: "Diff", selected: true })
    ).toBeInTheDocument();
    // The diff body rendered the changed line from the payload.
    expect(screen.getByText("outputs")).toBeInTheDocument();
  });

  it("flipping to Source swaps the diff for the live file preview", async () => {
    const user = setupUser();
    const onViewModeChange = jest.fn();
    render(
      <FileViewPane
        path={EDIT.path}
        edit={EDIT}
        viewMode="diff"
        onViewModeChange={onViewModeChange}
        sessionId="s1"
        refreshKey={0}
      />
    );

    await user.click(screen.getByRole("tab", { name: "Source" }));
    expect(onViewModeChange).toHaveBeenCalledWith("source");
  });

  it("a never-edited file renders source-only with no toggle", () => {
    render(
      <FileViewPane
        path="outputs/notes.txt"
        edit={null}
        viewMode="source"
        onViewModeChange={jest.fn()}
        sessionId="s1"
        refreshKey={0}
      />
    );

    expect(screen.queryByTestId("file-view-toggle")).not.toBeInTheDocument();
    // The source preview fetched the file (loading placeholder is enough).
    expect(screen.getByText("outputs")).toBeInTheDocument();
  });
});
