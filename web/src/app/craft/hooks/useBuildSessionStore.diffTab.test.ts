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

  it("opens the panel, creates and activates the diff tab", () => {
    seed();
    useBuildSessionStore.getState().openDiffPreview(SESSION, diffPayload);

    const session = useBuildSessionStore.getState().sessions.get(SESSION)!;
    expect(session.outputPanelOpen).toBe(true);
    expect(session.panelTabs).toHaveLength(1);
    expect(session.panelTabs[0]).toMatchObject({
      kind: "diff",
      path: "outputs/report.md",
    });
    expect(session.activePanelTabId).toContain("diff:outputs/report.md:");
  });

  it("dedupes by content: the same patch focuses the existing tab", () => {
    seed();
    const store = useBuildSessionStore.getState();
    store.openDiffPreview(SESSION, diffPayload);
    useBuildSessionStore.getState().openDiffPreview(SESSION, diffPayload);

    const session = useBuildSessionStore.getState().sessions.get(SESSION)!;
    expect(session.panelTabs).toHaveLength(1);
  });

  it("a different patch to the same file opens a sibling tab", () => {
    seed();
    const store = useBuildSessionStore.getState();
    store.openDiffPreview(SESSION, diffPayload);
    useBuildSessionStore.getState().openDiffPreview(SESSION, {
      ...diffPayload,
      newContent: "a\nb\nd",
      added: 2,
    });

    const session = useBuildSessionStore.getState().sessions.get(SESSION)!;
    expect(session.panelTabs).toHaveLength(2);
    expect(
      new Set(session.panelTabs.map((t) => t.kind === "diff" && t.contentHash))
        .size
    ).toBe(2);
  });
});
