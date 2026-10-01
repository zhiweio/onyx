import {
  appendPromptHistoryEntry,
  navigatePromptHistory,
} from "@/sections/input/lexical/promptHistory";

describe("appendPromptHistoryEntry", () => {
  it("appends trimmed entries", () => {
    expect(appendPromptHistoryEntry([], "  hello  ")).toEqual(["hello"]);
  });

  it("ignores empty entries", () => {
    expect(appendPromptHistoryEntry(["a"], "   ")).toEqual(["a"]);
  });

  it("suppresses only consecutive duplicates", () => {
    expect(appendPromptHistoryEntry(["a"], "a")).toEqual(["a"]);
    expect(appendPromptHistoryEntry(["a", "b"], "a")).toEqual(["a", "b", "a"]);
  });

  it("caps the history length", () => {
    const entries = appendPromptHistoryEntry(["1", "2", "3"], "4", 3);
    expect(entries).toEqual(["2", "3", "4"]);
  });
});

describe("navigatePromptHistory", () => {
  it("does nothing with an empty history", () => {
    expect(navigatePromptHistory([], null, "up").shouldHandle).toBe(false);
  });

  it("up from browsing picks the newest entry", () => {
    const result = navigatePromptHistory(["a", "b"], null, "up");
    expect(result).toEqual({
      nextIndex: 1,
      nextValue: "b",
      shouldHandle: true,
    });
  });

  it("up keeps the oldest entry", () => {
    const result = navigatePromptHistory(["a", "b"], 0, "up");
    expect(result).toEqual({
      nextIndex: 0,
      nextValue: "a",
      shouldHandle: true,
    });
  });

  it("down past the newest entry exits browsing with an empty draft", () => {
    const result = navigatePromptHistory(["a", "b"], 1, "down");
    expect(result).toEqual({
      nextIndex: null,
      nextValue: "",
      shouldHandle: true,
    });
  });

  it("down moves toward the newest entry", () => {
    const result = navigatePromptHistory(["a", "b"], 0, "down");
    expect(result).toEqual({
      nextIndex: 1,
      nextValue: "b",
      shouldHandle: true,
    });
  });
});
