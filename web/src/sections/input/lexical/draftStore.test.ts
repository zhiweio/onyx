/**
 * @jest-environment jsdom
 */
import {
  clearComposerDraft,
  persistComposerDraft,
  readComposerDraft,
} from "@/sections/input/lexical/draftStore";

const SURFACE = "craft";
const SCOPE = "session-1";

describe("composer draft store", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("returns null when nothing was persisted", () => {
    expect(readComposerDraft(SURFACE, SCOPE)).toBeNull();
  });

  it("round-trips text and editor state", () => {
    persistComposerDraft(SURFACE, SCOPE, {
      text: "hello",
      editorStateJson: '{"root":{}}',
    });
    expect(readComposerDraft(SURFACE, SCOPE)).toEqual({
      text: "hello",
      editorStateJson: '{"root":{}}',
    });
  });

  it("keeps surfaces isolated", () => {
    persistComposerDraft(SURFACE, SCOPE, { text: "craft draft" });
    persistComposerDraft("chat", SCOPE, { text: "chat draft" });
    expect(readComposerDraft(SURFACE, SCOPE)?.text).toBe("craft draft");
    expect(readComposerDraft("chat", SCOPE)?.text).toBe("chat draft");
  });

  it("drops drafts that are empty after trimming", () => {
    persistComposerDraft(SURFACE, SCOPE, { text: "   " });
    expect(readComposerDraft(SURFACE, SCOPE)).toBeNull();
  });

  it("clear removes only the target scope", () => {
    persistComposerDraft(SURFACE, SCOPE, { text: "a" });
    persistComposerDraft(SURFACE, "session-2", { text: "b" });
    clearComposerDraft(SURFACE, SCOPE);
    expect(readComposerDraft(SURFACE, SCOPE)).toBeNull();
    expect(readComposerDraft(SURFACE, "session-2")?.text).toBe("b");
  });

  it("removing the last scope clears the storage key entirely", () => {
    persistComposerDraft(SURFACE, SCOPE, { text: "a" });
    clearComposerDraft(SURFACE, SCOPE);
    const keys = Object.keys(window.localStorage);
    expect(keys).toHaveLength(0);
  });
});
