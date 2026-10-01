"use client";

import { useCallback, useEffect, useMemo, useRef, type RefObject } from "react";
import { LexicalComposer } from "@lexical/react/LexicalComposer";
import { PlainTextPlugin } from "@lexical/react/LexicalPlainTextPlugin";
import { ContentEditable } from "@lexical/react/LexicalContentEditable";
import { HistoryPlugin } from "@lexical/react/LexicalHistoryPlugin";
import { useLexicalComposerContext } from "@lexical/react/LexicalComposerContext";
import {
  $createParagraphNode,
  $createTextNode,
  $getRoot,
  $getSelection,
  $isParagraphNode,
  $isRangeSelection,
  $isTextNode,
  COMMAND_PRIORITY_HIGH,
  KEY_ARROW_DOWN_COMMAND,
  KEY_ARROW_UP_COMMAND,
  KEY_BACKSPACE_COMMAND,
  KEY_ENTER_COMMAND,
  type EditorState,
  type LexicalEditor,
} from "lexical";
import { navigatePromptHistory } from "@/sections/input/lexical/promptHistory";
import { $getPromptMarkdown } from "@/sections/input/lexical/serialization";
import {
  $createPromptMentionNode,
  $isPromptMentionNode,
  PromptMentionNode,
} from "@/sections/input/lexical/nodes/PromptMentionNode";
import {
  HISTORY_NAVIGATION_UPDATE_TAG,
  PROGRAMMATIC_UPDATE_TAG,
} from "@/sections/input/lexical/editorUpdateTags";
import type {
  ComposerMention,
  LexicalPasteEvent,
  LexicalPromptInputHandle,
  LexicalSubmitResult,
  TriggerMenuConfig,
} from "@/sections/input/lexical/types";
import TriggerMenusPlugin from "@/sections/input/lexical/TriggerMenusPlugin";

/**
 * Core Lexical editor for the prompt-input kernel (ported from ZCode's
 * LexicalChatInput, trimmed to Onyx's needs):
 * - Enter submits, Shift+Enter newlines, Ctrl/Cmd+Enter submits
 * - IME composition guards on every submit path
 * - auto-height (grows to ~6 lines, then scrolls)
 * - prompt-history navigation (↑/↓) while empty or browsing history
 * - backspace deletes a chip plus its padding space in one stroke
 */

interface LexicalChatInputProps {
  placeholder?: string;
  disabled?: boolean;
  /** Blocks submit (e.g. uploads in flight); Enter falls back to newline so
   * the draft stays editable. */
  submitDisabled?: boolean;
  onSubmit: (text: string) => LexicalSubmitResult;
  onChange?: (text: string) => void;
  /** Fires whenever the set of chips in the editor changes. */
  onMentionsChange?: (mentions: ComposerMention[]) => void;
  onFocus?: () => void;
  inputTestId?: string;
  editorApiRef?: RefObject<LexicalPromptInputHandle | null>;
  promptHistory?: readonly string[];
  slashTrigger?: TriggerMenuConfig | null;
  mentionTriggers?: readonly TriggerMenuConfig[] | null;
  onPaste?: (event: LexicalPasteEvent) => void;
}

function getEditorMarkdown(editorState: EditorState): string {
  let text = "";
  editorState.read(() => {
    text = $getPromptMarkdown();
  });
  return text;
}

function resetEditor(editor: LexicalEditor) {
  replaceEditorText(editor, "");
}

function replaceEditorText(editor: LexicalEditor, text: string) {
  editor.update(
    () => {
      const root = $getRoot();
      root.clear();
      // Lexical joins paragraphs with "\n\n"; split symmetrically so newlines
      // do not double up when text round-trips through the editor.
      for (const line of text.split("\n\n")) {
        const paragraph = $createParagraphNode();
        if (line) {
          paragraph.append($createTextNode(line));
        }
        root.append(paragraph);
      }
      root.getLastChild()?.selectEnd();
    },
    { discrete: true, tag: PROGRAMMATIC_UPDATE_TAG },
  );
}

function appendEditorText(editor: LexicalEditor, text: string) {
  editor.update(
    () => {
      const root = $getRoot();
      const lastChild = root.getLastChild();
      const paragraph = $isParagraphNode(lastChild)
        ? lastChild
        : $createParagraphNode();
      if (!$isParagraphNode(lastChild)) {
        root.append(paragraph);
      }
      const currentText = paragraph.getTextContent();
      if (currentText.length > 0 && !/\s$/.test(currentText)) {
        paragraph.append($createTextNode(" "));
      }
      paragraph.append($createTextNode(text));
      paragraph.selectEnd();
    },
    { discrete: true, tag: PROGRAMMATIC_UPDATE_TAG },
  );
}

function insertEditorMention(
  editor: LexicalEditor,
  mention: Parameters<typeof $createPromptMentionNode>[0],
) {
  editor.update(
    () => {
      let selection = $getSelection();
      if (!$isRangeSelection(selection)) {
        selection = $getRoot().selectEnd();
      }
      const trailing = $createTextNode(" ");
      selection.insertNodes([$createPromptMentionNode(mention), trailing]);
      trailing.selectEnd();
    },
    { discrete: true, tag: PROGRAMMATIC_UPDATE_TAG },
  );
}

function collectEditorMentions(
  editor: LexicalEditor,
): Parameters<typeof $createPromptMentionNode>[0][] {
  return collectEditorMentionsFromState(editor.getEditorState());
}

function collectEditorMentionsFromState(
  editorState: EditorState,
): Parameters<typeof $createPromptMentionNode>[0][] {
  return editorState.read(() =>
    $getRoot()
      .getAllTextNodes()
      .filter($isPromptMentionNode)
      .map((node) => node.getMention()),
  );
}

function removeEditorMention(editor: LexicalEditor, id: string): boolean {
  let removed = false;
  editor.getEditorState().read(() => {
    const node = $getRoot()
      .getAllTextNodes()
      .find(
        (candidate) =>
          $isPromptMentionNode(candidate) && candidate.getMention().id === id,
      );
    if (!node) {
      return;
    }
    editor.update(
      () => {
        const latest = node.getLatest();
        const nextSibling = latest.getNextSibling();
        latest.remove();
        if (
          $isTextNode(nextSibling) &&
          /^\s$/.test(nextSibling.getTextContent())
        ) {
          nextSibling.remove();
        }
      },
      { discrete: true, tag: PROGRAMMATIC_UPDATE_TAG },
    );
    removed = true;
  });
  return removed;
}

function KeyboardPlugin({
  onSubmit,
  disabled,
  submitDisabled,
}: {
  onSubmit: (text: string) => LexicalSubmitResult;
  disabled?: boolean;
  submitDisabled?: boolean;
}) {
  const [editor] = useLexicalComposerContext();

  useEffect(() => {
    const unregisterEnter = editor.registerCommand(
      KEY_ENTER_COMMAND,
      (event: KeyboardEvent | null) => {
        if (!event) return false;

        if (disabled) {
          event.preventDefault();
          return true;
        }

        // IME composition (e.g. Chinese pinyin) must confirm the composition,
        // never submit.
        if (event.isComposing) {
          return false;
        }

        const text = getEditorMarkdown(editor.getEditorState());

        // Shift+Enter (and plain Ctrl/Cmd+Enter when the draft is empty)
        // newline; Ctrl/Cmd+Enter with content submits as an explicit
        // multiline-friendly send.
        if (event.shiftKey) {
          return false;
        }
        const modifiedSubmit =
          (event.ctrlKey || event.metaKey) && text.trim().length > 0;
        if (!modifiedSubmit && (event.ctrlKey || event.metaKey)) {
          return false;
        }

        // Submit blocked: keep the draft editable, Enter inserts a newline.
        if (submitDisabled) {
          return false;
        }

        event.preventDefault();
        if (text.trim().length > 0) {
          const submitResult = onSubmit(text);
          if (submitResult !== false) {
            resetEditor(editor);
          }
        }
        return true;
      },
      COMMAND_PRIORITY_HIGH,
    );

    const unregisterBackspace = editor.registerCommand(
      KEY_BACKSPACE_COMMAND,
      (event: KeyboardEvent | null) => {
        const selection = $getSelection();
        if (!$isRangeSelection(selection) || !selection.isCollapsed()) {
          return false;
        }
        const anchor = selection.anchor;
        if (anchor.type !== "text") {
          return false;
        }
        const node = anchor.getNode();
        if (!$isTextNode(node)) {
          return false;
        }
        const text = node.getTextContent();
        if (anchor.offset !== 1 || text !== " ") {
          return false;
        }
        const previousSibling = node.getPreviousSibling();
        if (!$isPromptMentionNode(previousSibling)) {
          return false;
        }

        // Chips are inserted with a padding space so typing can continue
        // after them; delete the space and the chip together so removing a
        // chip is one keystroke.
        event?.preventDefault();
        previousSibling.remove();
        node.remove();
        node.getParent()?.selectEnd();
        return true;
      },
      COMMAND_PRIORITY_HIGH,
    );

    return () => {
      unregisterEnter();
      unregisterBackspace();
    };
  }, [disabled, editor, onSubmit, submitDisabled]);

  return null;
}

function TextContentPlugin({
  onChange,
  onMentionsChange,
}: {
  onChange?: (text: string) => void;
  onMentionsChange?: (mentions: ComposerMention[]) => void;
}) {
  const [editor] = useLexicalComposerContext();

  useEffect(() => {
    if (!onChange && !onMentionsChange) {
      return;
    }
    return editor.registerUpdateListener(
      ({ dirtyElements, dirtyLeaves, editorState, prevEditorState }) => {
        if (dirtyElements.size === 0 && dirtyLeaves.size === 0) {
          return;
        }
        const nextText = getEditorMarkdown(editorState);
        const previousText = getEditorMarkdown(prevEditorState);
        if (nextText !== previousText) {
          onChange?.(nextText);
        }
        if (onMentionsChange) {
          const previousMentions =
            collectEditorMentionsFromState(prevEditorState);
          const nextMentions = collectEditorMentionsFromState(editorState);
          const changed =
            previousMentions.length !== nextMentions.length ||
            previousMentions.some(
              (mention, index) =>
                nextMentions[index]?.id !== mention.id ||
                nextMentions[index]?.markdown !== mention.markdown,
            );
          if (changed) {
            onMentionsChange(nextMentions);
          }
        }
      },
    );
  }, [editor, onChange, onMentionsChange]);

  return null;
}

function EditablePlugin({ editable }: { editable: boolean }) {
  const [editor] = useLexicalComposerContext();

  useEffect(() => {
    editor.setEditable(editable);
  }, [editor, editable]);

  return null;
}

function PromptHistoryPlugin({
  entries,
  disabled,
}: {
  entries: readonly string[];
  disabled?: boolean;
}) {
  const [editor] = useLexicalComposerContext();
  const historyIndexRef = useRef<number | null>(null);
  const applyingHistoryRef = useRef(false);

  useEffect(() => {
    if (
      historyIndexRef.current !== null &&
      entries[historyIndexRef.current] === undefined
    ) {
      historyIndexRef.current = null;
    }
  }, [entries]);

  useEffect(() => {
    return editor.registerUpdateListener(
      ({ dirtyElements, dirtyLeaves, editorState }) => {
        if (dirtyElements.size === 0 && dirtyLeaves.size === 0) {
          return;
        }
        if (applyingHistoryRef.current) {
          applyingHistoryRef.current = false;
          return;
        }
        const currentIndex = historyIndexRef.current;
        if (currentIndex === null) {
          return;
        }
        if (entries[currentIndex] === undefined) {
          historyIndexRef.current = null;
          return;
        }
        if (getEditorMarkdown(editorState) !== entries[currentIndex]) {
          // The user edited away from the browsed entry; exit history mode.
          historyIndexRef.current = null;
        }
      },
    );
  }, [editor, entries]);

  const applyHistoryEntry = useCallback(
    (nextIndex: number | null, nextValue: string) => {
      historyIndexRef.current = nextIndex;
      applyingHistoryRef.current = true;
      editor.update(
        () => {
          const root = $getRoot();
          root.clear();
          for (const line of nextValue.split("\n\n")) {
            const paragraph = $createParagraphNode();
            if (line) {
              paragraph.append($createTextNode(line));
            }
            root.append(paragraph);
          }
          root.getLastChild()?.selectEnd();
        },
        { tag: HISTORY_NAVIGATION_UPDATE_TAG },
      );
    },
    [editor],
  );

  const handleHistoryNavigation = useCallback(
    (direction: "up" | "down") => (event: KeyboardEvent | null) => {
      if (!event) return false;
      if (
        disabled ||
        event.shiftKey ||
        event.ctrlKey ||
        event.metaKey ||
        event.altKey ||
        event.isComposing
      ) {
        return false;
      }

      const text = getEditorMarkdown(editor.getEditorState());
      const currentIndex = historyIndexRef.current;
      // Only take over the arrow keys while empty or already browsing, so
      // multi-line cursor movement keeps working.
      if (currentIndex === null && text.length > 0) {
        return false;
      }

      const result = navigatePromptHistory(entries, currentIndex, direction);
      if (!result.shouldHandle) {
        return false;
      }

      event.preventDefault();
      applyHistoryEntry(result.nextIndex, result.nextValue);
      return true;
    },
    [applyHistoryEntry, disabled, editor, entries],
  );

  useEffect(() => {
    const unregisterUp = editor.registerCommand(
      KEY_ARROW_UP_COMMAND,
      handleHistoryNavigation("up"),
      COMMAND_PRIORITY_HIGH,
    );
    const unregisterDown = editor.registerCommand(
      KEY_ARROW_DOWN_COMMAND,
      handleHistoryNavigation("down"),
      COMMAND_PRIORITY_HIGH,
    );
    return () => {
      unregisterUp();
      unregisterDown();
    };
  }, [editor, handleHistoryNavigation]);

  return null;
}

function isCollapsedSelectionAtEditorStart(): boolean {
  const selection = $getSelection();
  if (!$isRangeSelection(selection) || !selection.isCollapsed()) {
    return false;
  }
  const [startPoint] = selection.getStartEndPoints() ?? [];
  if (!startPoint || startPoint.offset !== 0) {
    return false;
  }
  const root = $getRoot();
  const startNode = startPoint.getNode();
  if (startPoint.type === "text") {
    const firstTextNode = root.getAllTextNodes()[0] ?? null;
    return firstTextNode?.is(startNode) ?? root.getTextContentSize() === 0;
  }
  if (startNode.is(root)) {
    return true;
  }
  const firstDescendant = root.getFirstDescendant();
  return firstDescendant?.is(startNode) ?? root.getTextContentSize() === 0;
}

/** Normalizes a leading Chinese enumeration comma (、) into `/` so IME users
 * can still open the slash menu. Only active when a slash trigger exists. */
function ChineseSlashAliasPlugin({ disabled }: { disabled?: boolean }) {
  const [editor] = useLexicalComposerContext();

  useEffect(() => {
    if (disabled) {
      return;
    }

    const handleBeforeInput = (event: InputEvent) => {
      const shouldNormalize =
        event.data === "、" &&
        event.inputType === "insertText" &&
        !event.isComposing;
      if (!shouldNormalize) {
        return;
      }
      let atStart = false;
      editor.getEditorState().read(() => {
        atStart = isCollapsedSelectionAtEditorStart();
      });
      if (!atStart) {
        return;
      }

      event.preventDefault();
      editor.update(
        () => {
          if (!isCollapsedSelectionAtEditorStart()) {
            return;
          }
          const selection = $getSelection();
          if (!$isRangeSelection(selection)) {
            return;
          }
          selection.insertText("/");
        },
        { tag: PROGRAMMATIC_UPDATE_TAG },
      );
    };

    return editor.registerRootListener((rootElement, previousRootElement) => {
      previousRootElement?.removeEventListener(
        "beforeinput",
        handleBeforeInput as EventListener,
      );
      rootElement?.addEventListener(
        "beforeinput",
        handleBeforeInput as EventListener,
      );
    });
  }, [disabled, editor]);

  return null;
}

function PasteCapturePlugin({
  disabled,
  onPaste,
}: {
  disabled?: boolean;
  onPaste?: (event: LexicalPasteEvent) => void;
}) {
  const [editor] = useLexicalComposerContext();

  useEffect(() => {
    if (!onPaste) {
      return;
    }
    const handlePaste = (event: ClipboardEvent) => {
      if (disabled) {
        return;
      }
      const wasDefaultPrevented = event.defaultPrevented;
      onPaste(event);
      if (event.defaultPrevented && !wasDefaultPrevented) {
        // The integrator turned the paste into something else (e.g. an
        // attachment); keep Lexical from also inserting the text.
        event.stopImmediatePropagation();
      }
    };
    return editor.registerRootListener((rootElement, previousRootElement) => {
      previousRootElement?.removeEventListener("paste", handlePaste, {
        capture: true,
      });
      rootElement?.addEventListener("paste", handlePaste, { capture: true });
    });
  }, [disabled, editor, onPaste]);

  return null;
}

function EditorApiPlugin({
  editorApiRef,
}: {
  editorApiRef?: RefObject<LexicalPromptInputHandle | null>;
}) {
  const [editor] = useLexicalComposerContext();

  useEffect(() => {
    if (!editorApiRef) {
      return;
    }
    editorApiRef.current = {
      clear: () => resetEditor(editor),
      focus: () => editor.focus(),
      getText: () => getEditorMarkdown(editor.getEditorState()),
      setText: (text: string) => replaceEditorText(editor, text),
      appendText: (text: string) => appendEditorText(editor, text),
      insertMention: (mention) => insertEditorMention(editor, mention),
      getMentions: () => collectEditorMentions(editor),
      removeMention: (id) => removeEditorMention(editor, id),
      getEditorStateJson: () =>
        JSON.stringify(editor.getEditorState().toJSON()),
      setEditorStateJson: (editorStateJson: string) => {
        try {
          const editorState = editor.parseEditorState(editorStateJson);
          editor.setEditorState(editorState, { tag: PROGRAMMATIC_UPDATE_TAG });
          return true;
        } catch {
          return false;
        }
      },
    };
    return () => {
      editorApiRef.current = null;
    };
  }, [editor, editorApiRef]);

  return null;
}

function LexicalErrorBoundary({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

const EDITOR_THEME = {
  paragraph: "m-0",
};

function LexicalChatInput({
  placeholder,
  disabled = false,
  submitDisabled = false,
  onSubmit,
  onChange,
  onMentionsChange,
  onFocus,
  inputTestId,
  editorApiRef,
  promptHistory = [],
  slashTrigger = null,
  mentionTriggers = null,
  onPaste,
}: LexicalChatInputProps) {
  const handleSubmit = useCallback(
    (text: string) => {
      const submitResult = onSubmit(text);
      requestAnimationFrame(() => {
        editorApiRef?.current?.focus();
      });
      return submitResult;
    },
    [editorApiRef, onSubmit],
  );

  const initialConfig = useMemo(
    () => ({
      namespace: "OnyxPromptInput",
      theme: EDITOR_THEME,
      nodes: [PromptMentionNode],
      onError: (error: Error) => {
        console.error("[LexicalChatInput] editor error:", error);
      },
    }),
    [],
  );

  // Lexical's ContentEditable props form a mutually exclusive union: an
  // aria-placeholder requires placeholder to be present too.
  const contentEditableProps: React.ComponentProps<typeof ContentEditable> =
    placeholder
      ? {
          "aria-placeholder": placeholder,
          placeholder: (
            <div className="pointer-events-none absolute inset-x-3 top-3 font-secondary-body text-text-03">
              {placeholder}
            </div>
          ),
        }
      : { placeholder: null };

  const contentEditable = (
    <ContentEditable
      dir="auto"
      className="w-full min-h-[44px] max-h-40 overflow-y-auto bg-transparent px-3 pb-2 pt-3 whitespace-pre-wrap wrap-break-word outline-hidden overscroll-contain"
      data-testid={inputTestId}
      onFocus={onFocus}
      {...contentEditableProps}
    />
  );

  return (
    <div className="relative flex-1">
      <LexicalComposer initialConfig={initialConfig}>
        <div className="relative">
          <PlainTextPlugin
            contentEditable={contentEditable}
            ErrorBoundary={LexicalErrorBoundary}
          />
          <HistoryPlugin />
          <TextContentPlugin
            onChange={onChange}
            onMentionsChange={onMentionsChange}
          />
          <KeyboardPlugin
            onSubmit={handleSubmit}
            disabled={disabled}
            submitDisabled={submitDisabled}
          />
          <PromptHistoryPlugin entries={promptHistory} disabled={disabled} />
          <EditablePlugin editable={!disabled} />
          <EditorApiPlugin editorApiRef={editorApiRef} />
          <ChineseSlashAliasPlugin disabled={disabled || !slashTrigger} />
          <PasteCapturePlugin disabled={disabled} onPaste={onPaste} />
        </div>
        <TriggerMenusPlugin
          configs={
            slashTrigger
              ? [slashTrigger, ...(mentionTriggers ?? [])]
              : [...(mentionTriggers ?? [])]
          }
          disabled={disabled}
        />
      </LexicalComposer>
    </div>
  );
}

export default LexicalChatInput;
