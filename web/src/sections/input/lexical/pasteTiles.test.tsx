/**
 * @jest-environment jsdom
 */
import React, { createRef } from "react";
import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { render } from "@tests/setup/test-utils";
import { ChatPromptEditor } from "@/sections/input/lexical";
import type { LexicalPromptInputHandle } from "@/sections/input/lexical";

const LARGE_TEXT = "line 1\nline 2\nline 3\nline 4";

function pastePlainText(element: HTMLElement, text: string) {
  // jsdom has no DataTransfer; a shape-compatible stub is enough for the
  // plugin's types/getData reads.
  const clipboardData = {
    types: ["text/plain"],
    getData: (type: string) => (type === "text/plain" ? text : ""),
    setData: () => undefined,
  };
  const event = new Event("paste", { bubbles: true, cancelable: true });
  Object.defineProperty(event, "clipboardData", { value: clipboardData });
  fireEvent(element, event);
}

function renderEditor(
  props: Partial<React.ComponentProps<typeof ChatPromptEditor>> = {}
) {
  const editorRef = createRef<LexicalPromptInputHandle | null>();
  const onSubmit = jest.fn((_text: string) => true);
  render(
    <ChatPromptEditor
      pasteTilesEnabled
      inputId="tile-input"
      editorRef={editorRef}
      onSubmit={onSubmit}
      {...props}
    />
  );
  return { editorRef, onSubmit };
}

function input(): HTMLElement {
  return document.getElementById("tile-input")!;
}

describe("paste tiles on the lexical kernel", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("collapses a large paste into a tile with data-text and preview", async () => {
    renderEditor();
    pastePlainText(input(), LARGE_TEXT);
    await waitFor(() => {
      expect(document.querySelector("[data-rich-tile]")).not.toBeNull();
    });
    const tile = document.querySelector<HTMLElement>("[data-rich-tile]");
    expect(tile!.getAttribute("data-text")).toBe(LARGE_TEXT);
    expect(
      tile!.querySelector(".rich-input-tile-preview")?.textContent
    ).toContain("line 1");
    expect(tile!.querySelector(".rich-input-tile-meta")?.textContent).toContain(
      "4 lines"
    );
  });

  it("keeps small pastes as plain text", () => {
    // jsdom does not run Lexical's default paste insertion; asserting the
    // tile path stays closed is the jsdom-verifiable half (the inline half
    // is covered by the browser e2e).
    renderEditor();
    pastePlainText(input(), "short text");
    expect(document.querySelector("[data-rich-tile]")).toBeNull();
  });

  it("serializes the full tile text on submit", async () => {
    const { editorRef, onSubmit } = renderEditor();
    pastePlainText(input(), LARGE_TEXT);
    await waitFor(() => {
      expect(document.querySelector("[data-rich-tile]")).not.toBeNull();
    });
    fireEvent.keyDown(input(), { key: "Enter", keyCode: 13 });
    const submitted: string = onSubmit.mock.calls[0]?.[0] ?? "";
    expect(submitted).toContain("line 1");
    expect(submitted).toContain("line 4");
    expect(editorRef.current?.getText()).toBe("");
  });

  it("expands a tile when the same text is pasted again", async () => {
    renderEditor();
    pastePlainText(input(), LARGE_TEXT);
    await waitFor(() => {
      expect(document.querySelector("[data-rich-tile]")).not.toBeNull();
    });
    pastePlainText(input(), LARGE_TEXT);
    await waitFor(() => {
      expect(document.querySelectorAll("[data-rich-tile]")).toHaveLength(0);
    });
    expect(screen.getByText(/line 1/)).toBeInTheDocument();
    expect(screen.getByText(/line 4/)).toBeInTheDocument();
  });

  it("creates a second tile for different large text", async () => {
    renderEditor();
    pastePlainText(input(), LARGE_TEXT);
    await waitFor(() => {
      expect(document.querySelectorAll("[data-rich-tile]")).toHaveLength(1);
    });
    pastePlainText(input(), "other a\nother b\nother c\nother d");
    await waitFor(() => {
      expect(document.querySelectorAll("[data-rich-tile]")).toHaveLength(2);
    });
  });

  it("removes the tile through its inline remove button", async () => {
    renderEditor();
    pastePlainText(input(), LARGE_TEXT);
    await waitFor(() => {
      expect(document.querySelector("[data-rich-tile]")).not.toBeNull();
    });
    const remove = document.querySelector<HTMLElement>(
      "[data-rich-tile-remove]"
    );
    expect(remove).not.toBeNull();
    fireEvent.click(remove!);
    await waitFor(() => {
      expect(document.querySelector("[data-rich-tile]")).toBeNull();
    });
  });

  it("marks the editable empty with data-empty and clears it on input", async () => {
    const { editorRef } = renderEditor();
    expect(input().hasAttribute("data-empty")).toBe(true);
    act(() => {
      editorRef.current?.setText("hello");
    });
    await waitFor(() => {
      expect(input().hasAttribute("data-empty")).toBe(false);
    });
  });

  it("arms a one-shot plain paste via Ctrl+Shift+V", async () => {
    renderEditor();
    fireEvent.keyDown(input(), {
      key: "V",
      code: "KeyV",
      ctrlKey: true,
      shiftKey: true,
    });
    pastePlainText(input(), LARGE_TEXT);
    // Armed: the tiling path stays closed (the inline insertion itself is
    // Lexical's default paste, exercised in the browser e2e).
    expect(document.querySelector("[data-rich-tile]")).toBeNull();
  });

  it("disarms the plain paste after any keystroke", async () => {
    renderEditor();
    fireEvent.keyDown(input(), {
      key: "V",
      code: "KeyV",
      ctrlKey: true,
      shiftKey: true,
    });
    fireEvent.keyDown(input(), { key: "x" });
    pastePlainText(input(), LARGE_TEXT);
    await waitFor(() => {
      expect(document.querySelector("[data-rich-tile]")).not.toBeNull();
    });
  });

  it("does not tile when the feature is disabled", () => {
    renderEditor({ pasteTilesEnabled: false });
    pastePlainText(input(), LARGE_TEXT);
    expect(document.querySelector("[data-rich-tile]")).toBeNull();
  });
});
