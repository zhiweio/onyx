import React, { createRef } from "react";
import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { render } from "@tests/setup/test-utils";
import { ChatPromptEditor } from "@/sections/input/lexical";
import type { LexicalPromptInputHandle } from "@/sections/input/lexical";
import { shouldOpenTriggerMenu } from "@/sections/input/lexical/TriggerMenusPlugin";

function renderEditor(
  props: Partial<React.ComponentProps<typeof ChatPromptEditor>> = {}
) {
  const editorRef = createRef<LexicalPromptInputHandle | null>();
  const onSubmit = jest.fn(() => true);
  const utils = render(
    <ChatPromptEditor
      placeholder="Ask anything"
      inputTestId="lexical-input"
      editorRef={editorRef}
      onSubmit={onSubmit}
      {...props}
    />
  );
  return { editorRef, onSubmit, ...utils };
}

describe("ChatPromptEditor", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("renders the placeholder", () => {
    renderEditor();
    expect(screen.getByTestId("lexical-input")).toBeInTheDocument();
  });

  it("opens an empty-source mention menu when showWhenEmpty is set", () => {
    expect(
      shouldOpenTriggerMenu({
        id: "files",
        triggerChars: ["@"],
        sections: {
          commands: [],
          skills: [],
          apps: [],
          mcpServers: [],
          files: [],
        },
        showWhenEmpty: true,
      })
    ).toBe(true);
  });

  it("keeps an empty mention menu closed without showWhenEmpty", () => {
    expect(
      shouldOpenTriggerMenu({
        id: "files",
        triggerChars: ["@"],
        sections: {
          commands: [],
          skills: [],
          apps: [],
          mcpServers: [],
          files: [],
        },
      })
    ).toBe(false);
    expect(
      shouldOpenTriggerMenu({
        id: "slash",
        triggerChars: ["/"],
        sections: {
          commands: [],
          skills: [],
          apps: [],
          mcpServers: [],
          files: [
            {
              kind: "file",
              fileId: "a",
              name: "a.md",
              path: "a.md",
              source: "library",
            },
          ],
        },
      })
    ).toBe(true);
  });

  it("submits the editor text on Enter", () => {
    const { editorRef, onSubmit } = renderEditor();
    act(() => {
      editorRef.current?.setText("hello world");
    });
    const input = screen.getByTestId("lexical-input");
    fireEvent.keyDown(input, { key: "Enter", keyCode: 13 });

    expect(onSubmit).toHaveBeenCalledWith("hello world");
    // A successful submit clears the editor.
    expect(editorRef.current?.getText()).toBe("");
  });

  it("keeps the draft when onSubmit returns false", () => {
    const { editorRef } = renderEditor({ onSubmit: jest.fn(() => false) });
    act(() => {
      editorRef.current?.setText("keep me");
    });
    fireEvent.keyDown(screen.getByTestId("lexical-input"), {
      key: "Enter",
      keyCode: 13,
    });

    expect(editorRef.current?.getText()).toBe("keep me");
  });

  it("Enter while blocked by running without queue sends nothing", () => {
    const { editorRef, onSubmit } = renderEditor({ isRunning: true });
    act(() => {
      editorRef.current?.setText("follow up");
    });
    fireEvent.keyDown(screen.getByTestId("lexical-input"), {
      key: "Enter",
      keyCode: 13,
    });

    expect(onSubmit).not.toHaveBeenCalled();
    expect(editorRef.current?.getText()).toBe("follow up");
  });

  it("Enter while running queues the follow-up", () => {
    const onQueueMessage = jest.fn(() => true);
    const { editorRef, onSubmit } = renderEditor({
      isRunning: true,
      onQueueMessage,
    });
    act(() => {
      editorRef.current?.setText("follow up");
    });
    fireEvent.keyDown(screen.getByTestId("lexical-input"), {
      key: "Enter",
      keyCode: 13,
    });

    expect(onQueueMessage).toHaveBeenCalledWith("follow up");
    expect(onSubmit).not.toHaveBeenCalled();
    expect(editorRef.current?.getText()).toBe("");
  });

  it("submit clears the persisted draft", async () => {
    const { editorRef } = renderEditor({
      draft: { surface: "craft", scope: "s1" },
    });
    act(() => {
      editorRef.current?.setText("drafted");
    });
    // Let the debounced save fire.
    await waitFor(
      () => {
        act(() => {
          editorRef.current?.setText("drafted more");
        });
      },
      { timeout: 800 }
    );
    fireEvent.keyDown(screen.getByTestId("lexical-input"), {
      key: "Enter",
      keyCode: 13,
    });
    expect(editorRef.current?.getText()).toBe("");
  });

  it("restores a persisted draft on mount", async () => {
    window.localStorage.setItem(
      "onyx-composer-draft:v1:craft:s1",
      JSON.stringify({
        version: 1,
        scopes: {
          s1: { text: "restored draft", updatedAt: 1 },
        },
      })
    );
    const editorRef = createRef<LexicalPromptInputHandle | null>();
    render(
      <ChatPromptEditor
        inputTestId="lexical-input"
        editorRef={editorRef}
        onSubmit={jest.fn()}
        draft={{ surface: "craft", scope: "s1" }}
      />
    );
    await waitFor(() => {
      expect(editorRef.current?.getText()).toBe("restored draft");
    });
  });

  it("shows the stop control while running with an empty draft", () => {
    const onInterrupt = jest.fn();
    renderEditor({ isRunning: true, onInterrupt });
    const stopButton = screen.getByTestId("composer-primary-action");
    expect(stopButton).toHaveAttribute("aria-label", "Stop generating");
    fireEvent.click(stopButton);
    expect(onInterrupt).toHaveBeenCalled();
  });
});
