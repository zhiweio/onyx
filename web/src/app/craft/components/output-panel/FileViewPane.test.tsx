import { render, screen, setupUser, waitFor } from "@tests/setup/test-utils";
import { FileViewPane } from "@/app/craft/components/output-panel/FileViewPane";
import { fetchFileContent } from "@/app/craft/services/apiServices";

jest.mock("next/navigation", () => ({
  useRouter: () => ({ back: jest.fn(), push: jest.fn() }),
  usePathname: () => "/craft/v1",
  useSearchParams: () => ({ get: () => null, has: () => false }),
}));

jest.mock("@/app/craft/services/apiServices", () => ({
  ...jest.requireActual("@/app/craft/services/apiServices"),
  fetchFileContent: jest.fn(),
}));

const EDIT = {
  path: "outputs/_build_tax_health.py",
  fileName: "_build_tax_health.py",
  toolCallId: "tc-1",
  oldContent: "",
  newContent: "import json\n\nDATA = {}\n",
  added: 3,
  removed: 0,
  isNewFile: true,
};

describe("FileViewPane", () => {
  beforeEach(() => {
    jest.mocked(fetchFileContent).mockReset();
  });

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
    // The all-additions diff body renders the task-written content.
    expect(screen.getByText(/DATA = /)).toBeInTheDocument();
  });

  it("flipping to Source swaps the diff for the live file preview", async () => {
    const user = setupUser();
    const onViewModeChange = jest.fn();
    jest.mocked(fetchFileContent).mockResolvedValue({
      content: "import json\n",
      mimeType: "text/x-python",
      isImage: false,
    });
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

  it("a 404 source falls back to the task-written snapshot with a notice", async () => {
    const user = setupUser();
    jest
      .mocked(fetchFileContent)
      .mockRejectedValue(new Error("Failed to fetch file content: 404"));
    render(
      <FileViewPane
        path={EDIT.path}
        edit={EDIT}
        viewMode="source"
        onViewModeChange={jest.fn()}
        sessionId="s1"
        refreshKey={0}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId("snapshot-notice")).toBeInTheDocument();
    });
    // The snapshot renders the task-written content, highlighted.
    await waitFor(() => {
      expect(document.querySelector(".hljs-keyword")).not.toBeNull();
    });
  });

  it("a never-edited file renders source-only with no toggle", () => {
    jest.mocked(fetchFileContent).mockResolvedValue({
      content: "plain note\n",
      mimeType: "text/plain",
      isImage: false,
    });
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
  });
});
