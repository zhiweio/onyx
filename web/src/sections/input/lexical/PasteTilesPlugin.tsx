"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useLexicalComposerContext } from "@lexical/react/LexicalComposerContext";
import {
  $createParagraphNode,
  $createTextNode,
  $getNodeByKey,
  $getRoot,
  $getSelection,
  $isElementNode,
  $isRangeSelection,
  $nodesOfType,
} from "lexical";
import PasteTilePopover from "@/sections/input/PasteTilePopover";
import {
  $createPromptTileNode,
  $isPromptTileNode,
  PromptTileNode,
} from "@/sections/input/lexical/nodes/PromptTileNode";
import { shouldCreatePasteTile } from "@/lib/richInputTile";
import { $getPromptMarkdown } from "@/sections/input/lexical/serialization";
import { PROGRAMMATIC_UPDATE_TAG } from "@/sections/input/lexical/editorUpdateTags";

/**
 * Paste tiles on the Lexical kernel, ported from the contentEditable
 * implementation with the same DOM contract ([data-rich-tile], data-text,
 * preview/meta spans, popover selectors):
 *
 * - large pastes (>200 chars or >3 lines) collapse into tiles; small pastes
 *   and file pastes fall through to the normal paths;
 * - Ctrl+Shift+V arms a one-shot plain paste (any keystroke disarms it);
 * - re-pasting a tile's exact text expands that tile back to inline text;
 * - the tile highlight is a DOM-level visual state (class + a raw DOM range
 *   over the tile), deliberately outside Lexical's selection model — the
 *   editor reconciles DOM selections over contenteditable=false spans back
 *   to a collapsed caret, which would instantly erase a model-level
 *   highlight. Arrow keys move into the tile, Enter opens the popover (and
 *   never submits), Backspace highlights then deletes, typing deselects
 *   without consuming the tile, Ctrl+A adds the blue in-selection border;
 * - copy/cut over a selection containing tiles writes the full text;
 * - Home/End drive the caret explicitly (the browser treats them as scroll
 *   keys inside contenteditable on some platforms, freezing the caret);
 * - the popover (reused verbatim) edits, expands, or clears the tile.
 */

interface PasteTilesPluginProps {
  enabled: boolean;
}

function tileElementsIn(root: HTMLElement | null): HTMLElement[] {
  if (!root) {
    return [];
  }
  return Array.from(root.querySelectorAll<HTMLElement>("[data-rich-tile]"));
}

export function PasteTilesPlugin({ enabled }: PasteTilesPluginProps) {
  const [editor] = useLexicalComposerContext();
  const [popover, setPopover] = useState<{
    key: string;
    text: string;
    element: HTMLElement | null;
  } | null>(null);
  const plainPasteArmedRef = useRef(false);
  // The highlighted ("selected") tile's node key — a DOM-level state.
  const highlightedKeyRef = useRef<string | null>(null);
  // The collapsed caret position the highlight replaced; typing restores it
  // so the keystroke lands at the caret instead of replacing the tile's DOM
  // selection.
  const parkedRangeRef = useRef<Range | null>(null);

  const clearHighlight = useCallback(() => {
    highlightedKeyRef.current = null;
    for (const el of tileElementsIn(editor.getRootElement())) {
      el.classList.remove("rich-input-tile-selected");
    }
  }, [editor]);

  /** Highlight a tile: class + a raw DOM range over its element. Lexical's
   *  own (collapsed) selection is left untouched so typing afterwards
   *  inserts at the adjacent caret instead of replacing the tile. */
  const highlightTile = useCallback(
    (key: string) => {
      const el =
        editor
          .getRootElement()
          ?.querySelector<HTMLElement>(`[data-tile-node-key="${key}"]`) ?? null;
      if (!el) {
        return;
      }
      clearHighlight();
      highlightedKeyRef.current = key;
      el.classList.add("rich-input-tile-selected");
      const domSelection = window.getSelection();
      if (domSelection) {
        if (domSelection.isCollapsed && domSelection.rangeCount > 0) {
          parkedRangeRef.current = domSelection.getRangeAt(0).cloneRange();
        }
        const range = document.createRange();
        range.selectNode(el);
        domSelection.removeAllRanges();
        domSelection.addRange(range);
      }
    },
    [clearHighlight, editor],
  );

  // ---- DOM selection watcher (deselect + Ctrl+A in-selection border) -----

  useEffect(() => {
    if (!enabled) {
      return;
    }
    const handleSelectionChange = () => {
      const root = editor.getRootElement();
      const domSelection = window.getSelection();
      if (!root || !domSelection || domSelection.rangeCount === 0) {
        clearHighlight();
        return;
      }
      const range = domSelection.getRangeAt(0);
      for (const el of tileElementsIn(root)) {
        el.classList.toggle(
          "rich-input-tile-in-selection",
          !domSelection.isCollapsed && range.intersectsNode(el),
        );
      }
      const highlighted = highlightedKeyRef.current;
      if (highlighted !== null) {
        const el = root.querySelector<HTMLElement>(
          `[data-tile-node-key="${highlighted}"]`,
        );
        const stillCovered =
          el !== null && !domSelection.isCollapsed && range.intersectsNode(el);
        if (!stillCovered) {
          clearHighlight();
        }
      }
    };
    document.addEventListener("selectionchange", handleSelectionChange);
    return () =>
      document.removeEventListener("selectionchange", handleSelectionChange);
  }, [clearHighlight, editor, enabled]);

  // ---- Paste / copy / cut / keys (document capture for priority) ---------

  useEffect(() => {
    if (!enabled) {
      return;
    }

    const inEditor = (target: EventTarget | null): boolean => {
      const root = editor.getRootElement();
      return root !== null && target instanceof Node && root.contains(target);
    };

    /** DOM-level adjacency: the collapsed DOM caret's neighboring tile
     *  element. The original contentEditable implementation used exactly
     *  this; reading the DOM (not Lexical's model) sidesteps the async
     *  selection reconciliation that races rapid keystrokes. */
    const domAdjacentTileKey = (
      direction: "before" | "after",
    ): string | null => {
      const root = editor.getRootElement();
      const sel = window.getSelection();
      if (
        !root ||
        !sel ||
        sel.rangeCount === 0 ||
        !sel.isCollapsed ||
        !sel.anchorNode ||
        !root.contains(sel.anchorNode)
      ) {
        return null;
      }
      const anchorNode = sel.anchorNode;
      let sibling: Node | null = null;
      if (anchorNode.nodeType === Node.TEXT_NODE) {
        const text = anchorNode.textContent ?? "";
        // Lexical wraps each text node in <span data-lexical-text>; the tile
        // is a sibling of the WRAPPER, so climb one level when the text's own
        // sibling is absent.
        const atStart = sel.anchorOffset === 0;
        const atEnd = sel.anchorOffset === text.length;
        const wrapper = anchorNode.parentElement;
        sibling =
          direction === "before"
            ? atStart
              ? (anchorNode.previousSibling ?? wrapper?.previousSibling ?? null)
              : null
            : atEnd
              ? (anchorNode.nextSibling ?? wrapper?.nextSibling ?? null)
              : null;
      } else if (anchorNode.nodeType === Node.ELEMENT_NODE) {
        const el = anchorNode as Element;
        const children = el.childNodes;
        sibling =
          direction === "before"
            ? children.item(sel.anchorOffset - 1)
            : children.item(sel.anchorOffset);
      }
      return sibling instanceof HTMLElement &&
        sibling.hasAttribute("data-rich-tile")
        ? sibling.getAttribute("data-tile-node-key")
        : null;
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

    /** Full text for the DOM selection when it involves tiles: the
     *  highlighted tile, or the markdown of the Lexical selection when it
     *  differs from the plain visible text (full-select covers tiles via
     *  their block wrappers). */
    const serializedSelection = (): string | null => {
      const highlighted = highlightedKeyRef.current;
      if (highlighted !== null) {
        const node = editor
          .getEditorState()
          .read(() => $getNodeByKey(highlighted));
        if ($isPromptTileNode(node)) {
          return node.getText();
        }
      }
      let out: string | null = null;
      editor.getEditorState().read(() => {
        const selection = $getSelection();
        if (!$isRangeSelection(selection) || selection.isCollapsed()) {
          return;
        }
        const nodes = selection.getNodes();
        const markdown = nodes.map((node) => $getPromptMarkdown(node)).join("");
        const plain = nodes.map((node) => node.getTextContent()).join("");
        if (!markdown || markdown === plain) {
          return;
        }
        out = markdown;
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
      // Belt-and-braces: synthetic capture-phase events don't always
      // persist through setData to the system clipboard in headless
      // browsers; the async clipboard API covers that path.
      void navigator.clipboard?.writeText(text).catch(() => undefined);
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
      void navigator.clipboard?.writeText(text).catch(() => undefined);
      const highlighted = highlightedKeyRef.current;
      if (highlighted !== null) {
        clearHighlight();
        editor.update(() => {
          const node = $getNodeByKey(highlighted);
          if ($isPromptTileNode(node)) {
            node.remove();
          }
        });
        return;
      }
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

      if (
        !event.ctrlKey &&
        !event.metaKey &&
        !event.altKey &&
        !event.isComposing
      ) {
        if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
          const key = domAdjacentTileKey(
            event.key === "ArrowLeft" ? "before" : "after",
          );
          if (key !== null) {
            event.preventDefault();
            event.stopImmediatePropagation();
            highlightTile(key);
            return;
          }
        } else if (event.key === "Backspace") {
          if (highlightedKeyRef.current !== null) {
            // Second Backspace of the pair: delete the highlighted tile.
            const key = highlightedKeyRef.current;
            event.preventDefault();
            event.stopImmediatePropagation();
            clearHighlight();
            editor.update(() => {
              const node = $getNodeByKey(key);
              if ($isPromptTileNode(node)) {
                node.remove();
              }
            });
            return;
          }
          const key = domAdjacentTileKey("before");
          if (key !== null) {
            // First Backspace: highlight instead of deleting.
            event.preventDefault();
            event.stopImmediatePropagation();
            highlightTile(key);
            return;
          }
        }
      }

      // Lexical leaves Home/End to the browser, and on some platforms (macOS
      // Chromium) the browser treats them as scroll keys inside
      // contenteditable, freezing the caret. Drive the caret ourselves so
      // arrow-tile navigation stays reachable.
      if (
        (event.key === "Home" || event.key === "End") &&
        !event.ctrlKey &&
        !event.metaKey &&
        !event.altKey
      ) {
        const target = editor.getEditorState().read(() => {
          const selection = $getSelection();
          if ($isRangeSelection(selection)) {
            const paragraph = selection.anchor.getNode().getTopLevelElement();
            if (paragraph !== null) {
              return paragraph;
            }
          }
          const root = $getRoot();
          return event.key === "Home"
            ? root.getFirstChild()
            : root.getLastChild();
        });
        if (target) {
          event.preventDefault();
          editor.update(
            () => {
              const paragraph = target.getLatest();
              if (event.key === "Home") {
                paragraph.selectStart();
              } else {
                paragraph.selectEnd();
              }
            },
            // Discrete: write the DOM selection synchronously, or the next
            // rapid keystroke reconciles the stale DOM caret back into the
            // model and the move is lost.
            { discrete: true },
          );
          return;
        }
      }

      // Typing over a highlighted tile deselects it without consuming the
      // tile: clear the highlight, restore the parked caret, and let the
      // keystroke land there.
      if (
        highlightedKeyRef.current !== null &&
        event.key.length === 1 &&
        !event.ctrlKey &&
        !event.metaKey &&
        !event.altKey &&
        !event.isComposing
      ) {
        clearHighlight();
        const parked = parkedRangeRef.current;
        const domSelection = window.getSelection();
        if (parked && domSelection) {
          domSelection.removeAllRanges();
          domSelection.addRange(parked);
        }
        return;
      }

      if (
        event.key === "Enter" &&
        !event.shiftKey &&
        !event.isComposing &&
        highlightedKeyRef.current !== null
      ) {
        // Enter over a highlighted tile opens the popover instead of
        // submitting; the popover's own textarea sits outside the editor so
        // its Enter is untouched.
        const key = highlightedKeyRef.current;
        const found = editor
          .getEditorState()
          .read((): { key: string; text: string } | null => {
            const node = $getNodeByKey(key);
            if (!$isPromptTileNode(node)) {
              return null;
            }
            return { key, text: node.getText() };
          });
        if (found) {
          event.preventDefault();
          event.stopImmediatePropagation();
          const root = editor.getRootElement();
          const element = root?.querySelector<HTMLElement>(
            `[data-tile-node-key="${found.key}"]`,
          );
          setPopover({ ...found, element: element ?? null });
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
        const found = editor
          .getEditorState()
          .read((): { key: string; text: string } | null => {
            const node = $getNodeByKey(key);
            if (!$isPromptTileNode(node)) {
              return null;
            }
            return { key, text: node.getText() };
          });
        if (found) {
          event.preventDefault();
          setPopover({ ...found, element: tileEl });
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
  }, [clearHighlight, editor, enabled]);

  // ---- Popover -------------------------------------------------------------

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
          // Clearing the text removes the tile and closes the popover.
          node.remove();
          setPopover(null);
          editor.focus();
          return;
        }
        // Mutate in place: replacing the node would mint a new key and
        // strand later popover actions (expand) on the old one.
        node.getWritable().__text = newText;
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

  if (popover === null || popover.element === null) {
    return null;
  }

  return (
    <PasteTilePopover
      text={popover.text}
      tileElement={popover.element}
      onDismiss={dismissPopover}
      onTextChange={updateTileText}
      onExpand={expandTile}
    />
  );
}

export default PasteTilesPlugin;
