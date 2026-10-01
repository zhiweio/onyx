"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useLexicalComposerContext } from "@lexical/react/LexicalComposerContext";
import {
  $createParagraphNode,
  $createRangeSelection,
  $createTextNode,
  $getNodeByKey,
  $getRoot,
  $getSelection,
  $isRangeSelection,
  $setSelection,
  COMMAND_PRIORITY_HIGH,
  KEY_ARROW_LEFT_COMMAND,
  KEY_ARROW_RIGHT_COMMAND,
  KEY_BACKSPACE_COMMAND,
  $nodesOfType,
  type NodeKey,
} from "lexical";
import PasteTilePopover from "@/sections/input/PasteTilePopover";
import {
  $createPromptTileNode,
  $isPromptTileNode,
  PromptTileNode,
  selectionCoversExactly,
} from "@/sections/input/lexical/nodes/PromptTileNode";
import { shouldCreatePasteTile } from "@/lib/richInputTile";
import { $getPromptMarkdown } from "@/sections/input/lexical/serialization";
import { PROGRAMMATIC_UPDATE_TAG } from "@/sections/input/lexical/editorUpdateTags";

/**
 * Paste tiles on the Lexical kernel, ported from the contentEditable
 * implementation with the same DOM contract ([data-rich-tile], data-text,
 * preview/meta spans, popover selectors):
 *
 * - large pastes (>200 chars or >3 lines) collapse into a tile; small pastes
 *   and file pastes fall through to the normal paths;
 * - Ctrl+Shift+V arms a one-shot plain paste (any keystroke disarms it);
 * - re-pasting a tile's exact text expands that tile back to inline text;
 * - the tile "highlight" is a selection covering exactly the tile: arrow keys
 *   move into it, Enter opens the popover (and never submits), Backspace
 *   highlights then deletes, typing collapses the selection (deselects),
 *   Ctrl+A adds the in-selection (blue border) class;
 * - copy/cut over a selection containing tiles writes the full text;
 * - the popover (reused verbatim) edits, expands, or clears the tile.
 */

interface PasteTilesPluginProps {
  enabled: boolean;
}

export function PasteTilesPlugin({ enabled }: PasteTilesPluginProps) {
  const [editor] = useLexicalComposerContext();
  const [popover, setPopover] = useState<{
    key: NodeKey;
    text: string;
  } | null>(null);
  const plainPasteArmedRef = useRef(false);

  // ---- Selection-driven tile classes (selected / in-selection) -----------

  useEffect(() => {
    return editor.registerUpdateListener(({ editorState }) => {
      const rootElement = editor.getRootElement();
      if (!rootElement) {
        return;
      }
      const selectedKeys = new Set<string>();
      const inSelectionKeys = new Set<string>();
      editorState.read(() => {
        const selection = $getSelection();
        if (!$isRangeSelection(selection) || selection.isCollapsed()) {
          return;
        }
        for (const node of selection.getNodes()) {
          if (!$isPromptTileNode(node)) {
            continue;
          }
          inSelectionKeys.add(node.getKey());
          if (selectionCoversExactly(selection, node)) {
            selectedKeys.add(node.getKey());
          }
        }
      });
      rootElement
        .querySelectorAll<HTMLElement>("[data-rich-tile]")
        .forEach((el) => {
          const key = el.getAttribute("data-tile-node-key") ?? "";
          el.classList.toggle(
            "rich-input-tile-selected",
            selectedKeys.has(key),
          );
          el.classList.toggle(
            "rich-input-tile-in-selection",
            inSelectionKeys.has(key),
          );
        });
    });
  }, [editor]);

  // ---- Keyboard commands (arrow / backspace over tiles) ------------------

  const coverTileSelection = useCallback(
    (key: string) => {
      editor.update(
        () => {
          const node = $getNodeByKey(key);
          if (!$isPromptTileNode(node)) {
            return;
          }
          const parent = node.getParent();
          if (parent === null) {
            return;
          }
          const index = node.getIndexWithinParent();
          const range = $createRangeSelection();
          range.anchor.set(parent.getKey(), index, "element");
          range.focus.set(parent.getKey(), index + 1, "element");
          $setSelection(range);
        },
        { tag: PROGRAMMATIC_UPDATE_TAG },
      );
    },
    [editor],
  );

  useEffect(() => {
    const unregisterLeft = editor.registerCommand(
      KEY_ARROW_LEFT_COMMAND,
      (event) => {
        if (!enabled) {
          return false;
        }
        const state = editor.getEditorState();
        return state.read(() => {
          const selection = $getSelection();
          if (!$isRangeSelection(selection) || !selection.isCollapsed()) {
            return false;
          }
          const anchor = selection.anchor;
          const previousSibling =
            anchor.type === "text"
              ? anchor.offset === 0
                ? anchor.getNode().getPreviousSibling()
                : null
              : anchor.getNode().getChildAtIndex(anchor.offset - 1);
          if (!$isPromptTileNode(previousSibling)) {
            return false;
          }
          event?.preventDefault();
          coverTileSelection(previousSibling.getKey());
          return true;
        });
      },
      COMMAND_PRIORITY_HIGH,
    );

    const unregisterRight = editor.registerCommand(
      KEY_ARROW_RIGHT_COMMAND,
      (event) => {
        if (!enabled) {
          return false;
        }
        const state = editor.getEditorState();
        return state.read(() => {
          const selection = $getSelection();
          if (!$isRangeSelection(selection) || !selection.isCollapsed()) {
            return false;
          }
          const anchor = selection.anchor;
          const nextSibling =
            anchor.type === "text"
              ? anchor.offset === anchor.getNode().getTextContentSize()
                ? anchor.getNode().getNextSibling()
                : null
              : anchor.getNode().getChildAtIndex(anchor.offset);
          if (!$isPromptTileNode(nextSibling)) {
            return false;
          }
          event?.preventDefault();
          coverTileSelection(nextSibling.getKey());
          return true;
        });
      },
      COMMAND_PRIORITY_HIGH,
    );

    const unregisterBackspace = editor.registerCommand(
      KEY_BACKSPACE_COMMAND,
      (event) => {
        if (!enabled) {
          return false;
        }
        const state = editor.getEditorState();
        return state.read(() => {
          const selection = $getSelection();
          if (!$isRangeSelection(selection) || !selection.isCollapsed()) {
            // A covering selection (highlight) deletes through the default
            // path — the second Backspace of the highlight-then-delete pair.
            return false;
          }
          const anchor = selection.anchor;
          const previousSibling =
            anchor.type === "text"
              ? anchor.offset === 0
                ? anchor.getNode().getPreviousSibling()
                : null
              : anchor.getNode().getChildAtIndex(anchor.offset - 1);
          if (!$isPromptTileNode(previousSibling)) {
            return false;
          }
          event?.preventDefault();
          coverTileSelection(previousSibling.getKey());
          return true;
        });
      },
      COMMAND_PRIORITY_HIGH,
    );

    return () => {
      unregisterLeft();
      unregisterRight();
      unregisterBackspace();
    };
  }, [coverTileSelection, editor, enabled]);

  // ---- Paste / copy / cut / Enter (document capture for priority) --------

  useEffect(() => {
    if (!enabled) {
      return;
    }

    const inEditor = (target: EventTarget | null): boolean => {
      const root = editor.getRootElement();
      return root !== null && target instanceof Node && root.contains(target);
    };

    const handlePaste = (event: ClipboardEvent) => {
      if (!inEditor(event.target) || event.defaultPrevented) {
        return;
      }
      if (
        event.clipboardData &&
        Array.from(event.clipboardData.types).includes("Files")
      ) {
        return;
      }
      // Consume the one-shot plain-paste arm; everything else disarms below.
      const plainArmed = plainPasteArmedRef.current;
      plainPasteArmedRef.current = false;

      const text = event.clipboardData?.getData("text/plain") ?? "";
      if (!text || plainArmed || !shouldCreatePasteTile(text)) {
        return;
      }
      event.preventDefault();
      event.stopImmediatePropagation();

      editor.update(
        () => {
          // Re-pasting a tile's exact text expands it instead of stacking.
          for (const node of $nodesOfType(PromptTileNode)) {
            if (node.getText() === text) {
              node.replace($createTextNode(text));
              return;
            }
          }
          const tile = $createPromptTileNode(text);
          const trailing = $createTextNode("");
          const selection = $getSelection();
          if ($isRangeSelection(selection)) {
            // insertNodes replaces the selected range itself; extracting
            // first would orphan the selection and abort the update.
            selection.insertNodes([tile, trailing]);
          } else {
            $getRoot().append($createParagraphNode().append(tile, trailing));
          }
          trailing.selectEnd();
        },
        { tag: PROGRAMMATIC_UPDATE_TAG },
      );
    };

    const serializedSelection = (): string | null => {
      let out: string | null = null;
      editor.getEditorState().read(() => {
        const selection = $getSelection();
        if (!$isRangeSelection(selection) || selection.isCollapsed()) {
          return;
        }
        const nodes = selection.getNodes();
        if (!nodes.some($isPromptTileNode)) {
          return;
        }
        out = nodes.map((node) => $getPromptMarkdown(node)).join("");
      });
      return out;
    };

    const handleCopy = (event: ClipboardEvent) => {
      if (!inEditor(event.target)) {
        return;
      }
      const text = serializedSelection();
      if (text === null || !event.clipboardData) {
        return;
      }
      event.preventDefault();
      event.clipboardData.setData("text/plain", text);
    };

    const handleCut = (event: ClipboardEvent) => {
      if (!inEditor(event.target)) {
        return;
      }
      const text = serializedSelection();
      if (text === null || !event.clipboardData) {
        return;
      }
      event.preventDefault();
      event.clipboardData.setData("text/plain", text);
      editor.update(() => {
        const selection = $getSelection();
        if ($isRangeSelection(selection) && !selection.isCollapsed()) {
          selection.deleteCharacter(false);
        }
      });
    };

    const handleKeyDownCapture = (event: KeyboardEvent) => {
      if (!inEditor(event.target)) {
        return;
      }
      const isPlainPasteArm =
        event.key.toLowerCase() === "v" &&
        (event.ctrlKey || event.metaKey) &&
        event.shiftKey;
      if (isPlainPasteArm) {
        plainPasteArmedRef.current = true;
        return;
      }
      // Any other keystroke disarms a pending plain paste.
      plainPasteArmedRef.current = false;

      if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
        // Enter over a highlighted tile opens the popover instead of
        // submitting; the popover's own textarea sits outside the editor so
        // its Enter is untouched.
        const coversTile = editor.getEditorState().read(() => {
          const selection = $getSelection();
          if (!$isRangeSelection(selection)) {
            return null;
          }
          for (const node of selection.getNodes()) {
            if (
              $isPromptTileNode(node) &&
              selectionCoversExactly(selection, node)
            ) {
              return node;
            }
          }
          return null;
        });
        if (coversTile) {
          event.preventDefault();
          event.stopImmediatePropagation();
          setPopover({ key: coversTile.getKey(), text: coversTile.getText() });
        }
      }
    };

    const handleClick = (event: MouseEvent) => {
      if (!inEditor(event.target)) {
        return;
      }
      const target = event.target;
      if (!(target instanceof Element)) {
        return;
      }
      const removeButton = target.closest("[data-rich-tile-remove]");
      if (removeButton) {
        const tileEl = removeButton.closest<HTMLElement>("[data-rich-tile]");
        const key = tileEl?.getAttribute("data-tile-node-key") ?? "";
        if (key) {
          event.preventDefault();
          editor.update(() => {
            const node = $getNodeByKey(key);
            if ($isPromptTileNode(node)) {
              node.remove();
            }
          });
        }
        return;
      }
      const tileEl = target.closest<HTMLElement>("[data-rich-tile]");
      const key = tileEl?.getAttribute("data-tile-node-key") ?? "";
      if (key) {
        const node = editor.getEditorState().read(() => $getNodeByKey(key));
        if ($isPromptTileNode(node)) {
          event.preventDefault();
          setPopover({ key, text: node.getText() });
        }
      }
    };

    document.addEventListener("paste", handlePaste, true);
    document.addEventListener("copy", handleCopy, true);
    document.addEventListener("cut", handleCut, true);
    document.addEventListener("keydown", handleKeyDownCapture, true);
    document.addEventListener("click", handleClick, true);
    return () => {
      document.removeEventListener("paste", handlePaste, true);
      document.removeEventListener("copy", handleCopy, true);
      document.removeEventListener("cut", handleCut, true);
      document.removeEventListener("keydown", handleKeyDownCapture, true);
      document.removeEventListener("click", handleClick, true);
    };
  }, [editor, enabled]);

  // ---- Popover -------------------------------------------------------------

  const tileElement =
    popover !== null ? (editor.getElementByKey(popover.key) ?? null) : null;

  const updateTileText = useCallback(
    (newText: string) => {
      const key = popover?.key;
      setPopover((current) =>
        current ? { ...current, text: newText } : current,
      );
      if (key === undefined) {
        return;
      }
      editor.update(() => {
        const node = $getNodeByKey(key);
        if (!$isPromptTileNode(node)) {
          return;
        }
        if (newText.trim() === "") {
          node.remove();
          return;
        }
        node.replace($createPromptTileNode(newText));
      });
    },
    [editor, popover?.key],
  );

  const expandTile = useCallback(() => {
    const key = popover?.key;
    setPopover(null);
    if (key === undefined) {
      return;
    }
    editor.update(
      () => {
        const node = $getNodeByKey(key);
        if (!$isPromptTileNode(node)) {
          return;
        }
        node.replace($createTextNode(node.getText()));
        editor.focus();
      },
      { tag: PROGRAMMATIC_UPDATE_TAG },
    );
  }, [editor, popover?.key]);

  const dismissPopover = useCallback(() => {
    setPopover(null);
    editor.focus();
  }, [editor]);

  if (popover === null || tileElement === null) {
    return null;
  }

  return (
    <PasteTilePopover
      text={popover.text}
      tileElement={tileElement}
      onDismiss={dismissPopover}
      onTextChange={updateTileText}
      onExpand={expandTile}
    />
  );
}

export default PasteTilesPlugin;
