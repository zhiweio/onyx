import { useBuildSessionStore } from "@/app/craft/hooks/useBuildSessionStore";

describe("openDiffPreview panel tabs", () => {
  beforeEach(() => {
    useBuildSessionStore.setState({
      currentSessionId: null,
      sessions: new Map(),
    });
  });

  const SESSION = "session-1";
  const diffPayload = {
    path: "outputs/report.md",
    fileName: "report.md",
    toolCallId: "tc-1",
    oldContent: "a\nb",
    newContent: "a\nc",
    added: 1,
    removed: 1,
    isNewFile: false,
  };

  function seed() {
    useBuildSessionStore.getState().createSession(SESSION, {
      outputPanelOpen: false,
    });
  }

  function sessionState() {
    return useBuildSessionStore.getState().sessions.get(SESSION)!;
  }

  it("opens the panel, records the edit, and activates the file tab", () => {
    seed();
    useBuildSessionStore.getState().openDiffPreview(SESSION, diffPayload);

    const session = sessionState();
    expect(session.outputPanelOpen).toBe(true);
    expect(session.panelTabs).toHaveLength(1);
    expect(session.panelTabs[0]).toEqual({
      kind: "file",
      path: "outputs/report.md",
      fileName: "report.md",
    });
    expect(session.activePanelTabId).toBe("file:outputs/report.md");
    // The pane defaults to the diff view for a chip click.
    expect(session.fileEdits["outputs/report.md"]).toMatchObject({
      toolCallId: "tc-1",
    });
    expect(session.fileViewModes["outputs/report.md"]).toBe("diff");
  });

  it("keeps one tab per file: a later edit refreshes the payload in place", () => {
    seed();
    const store = useBuildSessionStore.getState();
    store.openDiffPreview(SESSION, diffPayload);
    useBuildSessionStore.getState().openDiffPreview(SESSION, {
      ...diffPayload,
      toolCallId: "tc-2",
      newContent: "a\nb\nd",
      added: 2,
    });

    const session = sessionState();
    expect(session.panelTabs).toHaveLength(1);
    expect(session.fileEdits["outputs/report.md"]).toMatchObject({
      toolCallId: "tc-2",
      added: 2,
    });
  });

  it("a sidebar open keeps the user's view but defaults an edited file to diff", () => {
    seed();
    const store = useBuildSessionStore.getState();
    // Edited file: first open via the Files tab lands on the diff.
    store.openDiffPreview(SESSION, diffPayload);
    store.setFileViewMode(SESSION, "outputs/report.md", "source");
    // An explicit source choice survives re-opens.
    store.openFilePreview(SESSION, "outputs/report.md", "report.md");
    expect(sessionState().fileViewModes["outputs/report.md"]).toBe("source");

    // A never-edited file has no mode; the pane derives "source".
    store.openFilePreview(SESSION, "outputs/other.md", "other.md");
    expect(sessionState().fileViewModes["outputs/other.md"]).toBeUndefined();
    expect(sessionState().fileEdits["outputs/other.md"]).toBeUndefined();
    expect(sessionState().panelTabs).toHaveLength(2);
  });
});
