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
  configs: readonly TriggerMenuConfig[],
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
  if (!textBeforeCaret) {
    return null;
  }
  for (const config of configs) {
    for (const triggerChar of config.triggerChars) {
      const match = new RegExp(
        `(?:^|\\s)(${escapeRegExp(triggerChar)})([^\\s]*)$`,
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
    sections.skills.length > 0 ||
    sections.apps.length > 0 ||
    sections.mcpServers.length > 0 ||
    (sections.files?.length ?? 0) > 0
  );
}

/** Default chip payload for a picked entry; markdown follows the prompt-prefix
 * conventions the agent already understands. */
export function defaultEntryToMention(
  entry: PickerEntry,
  _triggerChar: string,
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
    case "mcp":
      return {
        id: pickerEntryKey(entry),
        category: "mcp",
        label: entry.name,
        value: String(entry.mcpServerId),
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
  }
}

function caretAnchorRect(
  editor: ReturnType<typeof useLexicalComposerContext>[0],
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
    1,
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
          $detectTrigger(configsRef.current),
        );
        if (!detection) {
          if (activeRef.current) {
            setActive(null);
          }
          return;
        }
        const config = configsRef.current.find(
          (candidate) => candidate.id === detection.configId,
        );
        if (!config || !sectionsHaveEntries(config)) {
          if (activeRef.current) {
            setActive(null);
          }
          return;
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
      },
    );
  }, [disabled, editor]);

  const activeConfig = active
    ? (configs.find((config) => config.id === active.configId) ?? null)
    : null;

  const closeMenu = useCallback(() => {
    setActive(null);
  }, []);

  const handleSelect = useCallback(
    (entry: PickerEntry) => {
      const current = activeRef.current;
      setActive(null);
      if (!current) {
        return;
      }
      const config = configsRef.current.find(
        (candidate) => candidate.id === current.configId,
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
            const tokenLength =
              current.triggerChar.length + current.query.length;
            const start = Math.max(0, anchor.offset - tokenLength);
            const token = content.slice(start, anchor.offset);
            // Delete the typed token only when it still matches what opened
            // the menu; a stale draft must not eat unrelated characters.
            if (token === `${current.triggerChar}${current.query}`) {
              node.setTextContent(
                content.slice(0, start) + content.slice(anchor.offset),
              );
              node.select(start, start);
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
        { tag: PROGRAMMATIC_UPDATE_TAG },
      );
    },
    [editor],
  );

  return (
    <EntryPickerPopover
      open={active !== null && activeConfig !== null}
      anchorRect={active?.anchorRect ?? null}
      query={active?.query ?? ""}
      sections={
        activeConfig?.sections ?? {
          commands: [],
          skills: [],
          apps: [],
          mcpServers: [],
        }
      }
      onSelect={handleSelect}
      onClose={closeMenu}
    />
  );
}

export default TriggerMenusPlugin;
