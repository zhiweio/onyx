"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useLexicalComposerContext } from "@lexical/react/LexicalComposerContext";
import {
  $createTextNode,
  $getSelection,
  $getRoot,
  $isRangeSelection,
  $isTextNode,
} from "lexical";
import EntryPickerPopover from "@/sections/input/EntryPickerPopover";
import {
  $createPromptMentionNode,
  $isPromptMentionNode,
} from "@/sections/input/lexical/nodes/PromptMentionNode";
import {
  pickerEntryKey,
  pickerEntryPromptPrefix,
  type PickerEntry,
} from "@/lib/skills/picker";
import {
  HISTORY_NAVIGATION_UPDATE_TAG,
  PROGRAMMATIC_UPDATE_TAG,
} from "@/sections/input/lexical/editorUpdateTags";
import type {
  ComposerMention,
  TriggerMenuConfig,
} from "@/sections/input/lexical/types";

/**
 * Slash / mention trigger menus for the Lexical kernel.
 *
 * One update listener detects an active trigger token (trigger char at a word
 * start directly before the caret) across every registered config, and the
 * shared `EntryPickerPopover` renders the matching entries with its built-in
 * keyboard navigation. Picking either runs the config's `onPick` (commands)
 * or replaces the typed token with an atomic chip.
 */

interface ActiveTrigger {
  configId: string;
  triggerChar: string;
  query: string;
  anchorRect: DOMRect;
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

interface Detection {
  configId: string;
  triggerChar: string;
  query: string;
}

function $detectTrigger(
  configs: readonly TriggerMenuConfig[]
): Detection | null {
  const selection = $getSelection();
  if (!$isRangeSelection(selection) || !selection.isCollapsed()) {
    return null;
  }
  const anchor = selection.anchor;
  if (anchor.type !== "text") {
    return null;
  }
  const node = anchor.getNode();
  if ($isPromptMentionNode(node)) {
    return null;
  }
  const textBeforeCaret = node.getTextContent().slice(0, anchor.offset);
  return detectTriggerInText(configs, textBeforeCaret);
}

/** Pure text-level trigger detection (exported for tests): a trigger char at
 *  a word start directly before the caret opens its menu. */
export function detectTriggerInText(
  configs: readonly TriggerMenuConfig[],
  textBeforeCaret: string
): Detection | null {
  if (!textBeforeCaret) {
    return null;
  }
  for (const config of configs) {
    for (const triggerChar of config.triggerChars) {
      const match = new RegExp(
        `(?:^|\\s)(${escapeRegExp(triggerChar)})([^\\s]*)$`
      ).exec(textBeforeCaret);
      if (match) {
        return {
          configId: config.id,
          triggerChar: match[1] ?? triggerChar,
          query: match[2] ?? "",
        };
      }
    }
  }
  return null;
}

function sectionsHaveEntries(config: TriggerMenuConfig): boolean {
  const { sections } = config;
  return (
    sections.commands.length > 0 ||
    sections.scenarios.length > 0 ||
    sections.skills.length > 0 ||
    sections.apps.length > 0 ||
    (sections.files?.length ?? 0) > 0
  );
}

/**
 * Whether typing this menu's trigger char should open the popover. Menus
 * without entries stay closed unless they opt in with `showWhenEmpty` (e.g.
 * "@" with an empty library still shows the empty state).
 */
export function shouldOpenTriggerMenu(config: TriggerMenuConfig): boolean {
  return config.showWhenEmpty === true || sectionsHaveEntries(config);
}

/** Default chip payload for a picked entry; markdown follows the prompt-prefix
 * conventions the agent already understands. */
export function defaultEntryToMention(
  entry: PickerEntry,
  _triggerChar: string
): ComposerMention {
  const markdown = pickerEntryPromptPrefix(entry);
  switch (entry.kind) {
    case "skill":
      return {
        id: pickerEntryKey(entry),
        category: "skills",
        label: `/${entry.slug}`,
        value: entry.slug,
        markdown,
        description: entry.description,
      };
    case "command":
      return {
        id: pickerEntryKey(entry),
        category: "commands",
        label: `/${entry.slug}`,
        value: entry.slug,
        markdown,
        description: entry.description,
      };
    case "app":
      return {
        id: pickerEntryKey(entry),
        category: "apps",
        label: entry.name,
        value: String(entry.externalAppId),
        markdown,
      };
    case "file":
      return {
        id: pickerEntryKey(entry),
        category: "files",
        label: `@${entry.name}`,
        value: entry.fileId,
        markdown,
        data: {
          fileId: entry.fileId,
          path: entry.path,
          scope: entry.source === "sandbox" ? "sandbox" : "library",
        },
      };
    case "scenario":
      return {
        id: pickerEntryKey(entry),
        category: "scenarios",
        label: entry.name,
        value: entry.scenarioId,
        markdown,
        description: entry.description,
      };
  }
}

function caretAnchorRect(
  editor: ReturnType<typeof useLexicalComposerContext>[0]
): DOMRect | null {
  const rootElement = editor.getRootElement();
  const domSelection = window.getSelection();
  if (!rootElement || !domSelection || domSelection.rangeCount === 0) {
    return null;
  }
  const range = domSelection.getRangeAt(0).cloneRange();
  let rect = range.getBoundingClientRect();
  if (rect.width === 0 && rect.height === 0) {
    rect = range.startContainer.parentElement?.getBoundingClientRect() ?? rect;
  }
  if (rect.width === 0 && rect.height === 0) {
    return null;
  }
  // Match the panel width to the editor so it lines up with the composer.
  return new DOMRect(
    rect.left,
    rect.top,
    rootElement.getBoundingClientRect().width,
    1
  );
}

function TriggerMenusPlugin({
  configs,
  disabled,
}: {
  configs: readonly TriggerMenuConfig[];
  disabled?: boolean;
}) {
  const [editor] = useLexicalComposerContext();
  const [active, setActive] = useState<ActiveTrigger | null>(null);
  const configsRef = useRef(configs);
  const activeRef = useRef(active);
  // ZCode dismissedSignature: Escape records the trigger+query signature so
  // the same token does not instantly reopen the menu; editing the token
  // invalidates it.
  const dismissedSignatureRef = useRef<string | null>(null);

  // Mirror the latest props/state into refs for the update listener; effects
  // (not render) so React can safely replay render work.
  useEffect(() => {
    configsRef.current = configs;
  });
  useEffect(() => {
    activeRef.current = active;
  });

  useEffect(() => {
    if (disabled) {
      setActive(null);
      return;
    }
    return editor.registerUpdateListener(
      ({ dirtyElements, dirtyLeaves, editorState, tags }) => {
        // Programmatic rewrites (chip insert, draft restore) and history
        // navigation must not (re)open a menu.
        if (
          tags.has(PROGRAMMATIC_UPDATE_TAG) ||
          tags.has(HISTORY_NAVIGATION_UPDATE_TAG)
        ) {
          return;
        }
        if (
          dirtyElements.size === 0 &&
          dirtyLeaves.size === 0 &&
          !activeRef.current
        ) {
          return;
        }

        const detection = editorState.read(() =>
          $detectTrigger(configsRef.current)
        );
        if (!detection) {
          if (activeRef.current) {
            setActive(null);
          }
          return;
        }
        const config = configsRef.current.find(
          (candidate) => candidate.id === detection.configId
        );
        if (!config || !shouldOpenTriggerMenu(config)) {
          if (activeRef.current) {
            setActive(null);
          }
          return;
        }

        const signature = `${detection.configId}|${detection.triggerChar}|${detection.query}`;
        if (dismissedSignatureRef.current !== null) {
          if (dismissedSignatureRef.current === signature) {
            // Same token the user just dismissed with Escape: stay closed.
            if (activeRef.current) {
              setActive(null);
            }
            return;
          }
          dismissedSignatureRef.current = null;
        }

        setActive((previous) => {
          const anchorRect = caretAnchorRect(editor);
          if (!anchorRect) {
            return null;
          }
          if (
            previous &&
            previous.configId === detection.configId &&
            previous.triggerChar === detection.triggerChar &&
            previous.query === detection.query
          ) {
            return previous;
          }
          return {
            configId: detection.configId,
            triggerChar: detection.triggerChar,
            query: detection.query,
            anchorRect,
          };
        });
      }
    );
  }, [disabled, editor]);

  const activeConfig = active
    ? (configs.find((config) => config.id === active.configId) ?? null)
    : null;

  const closeMenu = useCallback(() => {
    const current = activeRef.current;
    if (current) {
      dismissedSignatureRef.current = `${current.configId}|${current.triggerChar}|${current.query}`;
    }
    setActive(null);
    editor.focus();
  }, [editor]);

  const handleSelect = useCallback(
    (entry: PickerEntry) => {
      const current = activeRef.current;
      dismissedSignatureRef.current = null;
      setActive(null);
      if (!current) {
        return;
      }
      const config = configsRef.current.find(
        (candidate) => candidate.id === current.configId
      );
      if (!config) {
        return;
      }
      editor.focus();
      if (config.onPick?.(entry, current.triggerChar)) {
        return;
      }
      const mention =
        config.entryToMention?.(entry, current.triggerChar) ??
        defaultEntryToMention(entry, current.triggerChar);

      editor.update(
        () => {
          const initialSelection = $getSelection();
          if (
            $isRangeSelection(initialSelection) &&
            initialSelection.anchor.type === "text"
          ) {
            const anchor = initialSelection.anchor;
            const node = anchor.getNode();
            const content = node.getTextContent();
            // Delete whatever trigger token the editor actually holds (the
            // search input can drive queries longer than the typed token).
            const match = new RegExp(
              `(?:^|\\s)(${escapeRegExp(current.triggerChar)})([^\\s]*)$`
            ).exec(content.slice(0, anchor.offset));
            if (match) {
              const tokenStart = anchor.offset - match[0].length;
              node.setTextContent(
                content.slice(0, tokenStart) + content.slice(anchor.offset)
              );
              node.select(tokenStart, tokenStart);
            }
          }
          let target = $getSelection();
          if (!$isRangeSelection(target)) {
            target = $getRoot().selectEnd();
          }
          const trailing = $createTextNode(" ");
          target.insertNodes([$createPromptMentionNode(mention), trailing]);
          trailing.selectEnd();
        },
        { tag: PROGRAMMATIC_UPDATE_TAG }
      );
    },
    [editor]
  );

  /** Search-input edits: update the filtered query and mirror it into the
   *  editor token so selection replacement stays aligned (space-containing
   *  queries filter locally only — editor tokens cannot hold spaces). */
  const handleQueryChange = useCallback(
    (nextQuery: string) => {
      setActive((current) =>
        current ? { ...current, query: nextQuery } : current
      );
      if (/\s/.test(nextQuery)) {
        return;
      }
      const current = activeRef.current;
      if (!current) {
        return;
      }
      editor.update(
        () => {
          const selection = $getSelection();
          if (
            !$isRangeSelection(selection) ||
            !selection.isCollapsed() ||
            selection.anchor.type !== "text"
          ) {
            return;
          }
          const anchor = selection.anchor;
          const node = anchor.getNode();
          if ($isPromptMentionNode(node)) {
            return;
          }
          const content = node.getTextContent();
          const match = new RegExp(
            `(?:^|\\s)(${escapeRegExp(current.triggerChar)})([^\\s]*)$`
          ).exec(content.slice(0, anchor.offset));
          if (!match) {
            return;
          }
          const tokenStart = anchor.offset - match[0].length;
          node.setTextContent(
            content.slice(0, tokenStart) +
              current.triggerChar +
              nextQuery +
              content.slice(anchor.offset)
          );
          const caretOffset =
            tokenStart + current.triggerChar.length + nextQuery.length;
          node.select(caretOffset, caretOffset);
        },
        { tag: PROGRAMMATIC_UPDATE_TAG }
      );
    },
    [editor]
  );

  return (
    <EntryPickerPopover
      open={active !== null && activeConfig !== null}
      anchorRect={active?.anchorRect ?? null}
      query={active?.query ?? ""}
      sections={
        activeConfig?.sections ?? {
          commands: [],
          scenarios: [],
          skills: [],
          apps: [],
        }
      }
      emptyMessage={activeConfig?.emptyMessage}
      onSelect={handleSelect}
      onClose={closeMenu}
      searchable
      onQueryChange={handleQueryChange}
    />
  );
}

export default TriggerMenusPlugin;
