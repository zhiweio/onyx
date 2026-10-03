"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import useSWR from "swr";
import {
  ChatPromptEditor,
  defaultEntryToMention as toMention,
  type ComposerMention,
  type LexicalPromptInputHandle,
} from "@/sections/input/lexical";
import ContextUsageMeter from "@/sections/input/ContextUsageMeter";
import ThoughtLevelSelect from "@/sections/input/ThoughtLevelSelect";
import { InputChipStrip } from "@/sections/input/InputChipStrip";
import { PlusMenuButton } from "@/sections/input/PlusMenuButton";
import { SelectButton } from "@opal/components";
import { SvgWorkflow } from "@opal/icons";
import { buildEntryMenuItems } from "@/app/craft/components/buildEntryMenuItems";
import ModelPickerButton from "@/app/craft/components/ModelPickerButton";
import {
  useUploadFilesContext,
  type BuildFile,
} from "@/app/craft/contexts/UploadFilesContext";
import useUserSkills from "@/hooks/useUserSkills";
import useUserExternalApps from "@/hooks/useUserExternalApps";
import { useCraftMcpServers } from "@/lib/tools/hooks";
import {
  COMPACT_COMMAND_SLUG,
  pickerEntriesFromSelection,
  pickerEntryConnectionPath,
  pickerEntryKey,
  toPickerSections,
  type PickerEntry,
  type SlashSelection,
} from "@/lib/skills/picker";
import { SWR_KEYS } from "@/lib/swr-keys";
import { fetchLibraryTree } from "@/app/craft/services/apiServices";
import type { QueuedMessage } from "@/app/app/interfaces";
import type { ReasoningEffortOverride } from "@/lib/languageModels/types";
import type { BuildLlmSelection } from "@/app/craft/onboarding/constants";
import { useUser } from "@/providers/UserProvider";

/**
 * Craft composer: the full form of the shared Lexical kernel.
 *
 * Slash (/) opens skills, apps, MCP servers, and the compact command; @ opens
 * user-library files. Picks become atomic chips whose markdown serializes
 * into the prompt, and skill/MCP chips also drive the structured selection
 * sent with the message. The session's persistent selection is re-armed as
 * chips after each send, matching the old chip-strip behavior.
 */

interface CraftComposerProps {
  sessionId: string | null;
  onSubmit: (
    message: string,
    files: BuildFile[],
    selection: SlashSelection
  ) => void;
  /** Absent on the welcome screen, where there is no session to queue into. */
  onQueueMessage?: (
    message: string,
    files: BuildFile[],
    selection: SlashSelection
  ) => void;
  queuedMessages?: readonly QueuedMessage[];
  onRemoveQueuedMessage?: (index: number) => void;
  /** The chat panel renders its own drag-reorderable queue panel. */
  hideQueueBar?: boolean;
  isRunning: boolean;
  isInterrupting?: boolean;
  onInterrupt?: () => void;
  disabled?: boolean;
  placeholder?: string;
  compactAvailable?: boolean;
  onCompact?: () => void;
  /** Last slash pick for this session — restored as chips after remount. */
  persistedSelection?: SlashSelection;
  /** Deep-task switch: send as a long job instead of a plain turn. */
  deepTask?: boolean;
  /** Absent hides the switch (subagent views have nothing to escalate). */
  onDeepTaskToggle?: () => void;
  contextUsage?: {
    usedTokens: number;
    contextLimit: number | null;
  } | null;
  thoughtLevel?: {
    value: ReasoningEffortOverride | null;
    onChange: (effort: ReasoningEffortOverride) => void;
    supportsReasoning: boolean;
    supportedEfforts?: ReasoningEffortOverride[];
    effortMax?: ReasoningEffortOverride | null;
    fallback?: ReasoningEffortOverride | null;
  } | null;
  modelSelection: BuildLlmSelection | null;
  onModelChange: (selection: BuildLlmSelection) => void;
  /** Exposed for tests and programmatic prefill. */
  editorHandleRef?: RefObject<LexicalPromptInputHandle | null>;
  trailingExtras?: ReactNode;
}

function selectionFromMentions(
  mentions: readonly ComposerMention[]
): SlashSelection {
  const skillIds: string[] = [];
  const mcpServerIds: number[] = [];
  for (const mention of mentions) {
    if (mention.category === "skills") {
      skillIds.push(mention.value);
    } else if (mention.category === "mcp" && /^\d+$/.test(mention.value)) {
      mcpServerIds.push(Number(mention.value));
    }
  }
  return { skillIds, mcpServerIds };
}

function CraftComposer({
  sessionId,
  onSubmit,
  onQueueMessage,
  queuedMessages,
  onRemoveQueuedMessage,
  hideQueueBar = false,
  isRunning,
  isInterrupting = false,
  onInterrupt,
  disabled = false,
  placeholder,
  compactAvailable = false,
  onCompact,
  persistedSelection,
  deepTask = false,
  onDeepTaskToggle,
  contextUsage,
  thoughtLevel,
  modelSelection,
  onModelChange,
  editorHandleRef,
  trailingExtras,
}: CraftComposerProps) {
  const t = useTranslations("craft.inputBar");
  const entryMenuT = useTranslations("craft.entryMenu");
  const router = useRouter();
  const { user } = useUser();
  const localEditorRef = useRef<LexicalPromptInputHandle | null>(null);
  const editorRef = editorHandleRef ?? localEditorRef;
  const fileInputRef = useRef<HTMLInputElement>(null);

  const {
    currentMessageFiles,
    uploadFiles,
    removeFile,
    clearFiles,
    hasUploadingFiles,
  } = useUploadFilesContext();

  const { data: skillsData } = useUserSkills();
  const { data: appsData } = useUserExternalApps();
  const { data: craftMcpData } = useCraftMcpServers();

  const pickerSections = useMemo(
    () => ({
      ...toPickerSections(skillsData, appsData, craftMcpData?.mcp_servers),
      commands: compactAvailable
        ? [
            {
              kind: "command" as const,
              slug: COMPACT_COMMAND_SLUG,
              name: t("compact.name"),
              description: t("compact.description"),
            },
          ]
        : [],
    }),
    [skillsData, appsData, craftMcpData, compactAvailable, t]
  );

  const { data: libraryTree } = useSWR(
    SWR_KEYS.buildUserLibraryTree,
    fetchLibraryTree
  );
  const libraryFileEntries = useMemo(
    () =>
      (libraryTree ?? [])
        .filter((entry) => !entry.is_directory)
        .map((entry) => ({
          kind: "file" as const,
          fileId: entry.id,
          name: entry.name,
          path: entry.path,
          source: "library" as const,
        })),
    [libraryTree]
  );

  const fileMentionSections = useMemo(
    () => ({
      commands: [],
      skills: [],
      apps: [],
      mcpServers: [],
      files: libraryFileEntries,
    }),
    [libraryFileEntries]
  );

  const slashTrigger = useMemo(
    () => ({
      id: "craft-slash",
      triggerChars: ["/"] as const,
      sections: pickerSections,
      onPick: (entry: PickerEntry) => {
        if (entry.kind === "command" && entry.slug === COMPACT_COMMAND_SLUG) {
          onCompact?.();
          return true;
        }
        const connectionPath = pickerEntryConnectionPath(entry);
        if (connectionPath) {
          router.push(connectionPath);
          return true;
        }
        return false;
      },
    }),
    [pickerSections, onCompact, router]
  );

  const fileMentionTrigger = useMemo(
    () => ({
      id: "craft-file-mention",
      triggerChars: ["@"] as const,
      sections: fileMentionSections,
      // Show the popover's empty state when the library has no files yet.
      showWhenEmpty: true,
      emptyMessage: entryMenuT("library.empty"),
    }),
    [fileMentionSections, entryMenuT]
  );

  // Restore the session's persistent slash selection as chips once the entry
  // data has loaded and the editor has no draft of its own.
  const restoreKeyRef = useRef<string | null>(null);
  useEffect(() => {
    if (!persistedSelection || !editorRef.current) {
      return;
    }
    const key = `${sessionId ?? "draft"}:${persistedSelection.skillIds.join(",")}:${persistedSelection.mcpServerIds.join(",")}`;
    if (restoreKeyRef.current === key) {
      return;
    }
    if (editorRef.current.getText().trim().length > 0) {
      return;
    }
    const entries = pickerEntriesFromSelection(
      pickerSections,
      persistedSelection
    );
    if (entries.length === 0) {
      return;
    }
    restoreKeyRef.current = key;
    for (const entry of entries) {
      editorRef.current.insertMention(toMention(entry, "/"));
    }
  }, [persistedSelection, pickerSections, sessionId, editorRef]);

  const [mentions, setMentions] = useState<ComposerMention[]>([]);
  const activeMentionEntries = useMemo<PickerEntry[]>(() => {
    const skillIds = new Set(
      mentions.filter((m) => m.category === "skills").map((m) => m.value)
    );
    const mcpIds = new Set(
      mentions.filter((m) => m.category === "mcp").map((m) => Number(m.value))
    );
    const active: PickerEntry[] = [];
    for (const skill of pickerSections.skills) {
      if (skillIds.has(skill.slug)) active.push(skill);
    }
    for (const mcp of pickerSections.mcpServers) {
      if (mcpIds.has(mcp.mcpServerId)) active.push(mcp);
    }
    return active;
  }, [mentions, pickerSections]);

  const rearmSelectionChips = useCallback(
    (selection: SlashSelection) => {
      const entries = pickerEntriesFromSelection(pickerSections, selection);

      // Stamp the restore key: once these chips land, the persisted-selection
      // effect must treat them as restored. Without the stamp both paths
      // insert, duplicating the /skill prefix in the next message.
      restoreKeyRef.current = `${sessionId ?? "draft"}:${selection.skillIds.join(",")}:${selection.mcpServerIds.join(",")}`;
      // Stamp the restore key: once these chips land, the persisted-selection
      // effect must treat them as restored. Without the stamp both paths
      // insert, duplicating the /skill prefix in the next message.
      requestAnimationFrame(() => {
        for (const entry of entries) {
          editorRef.current?.insertMention(toMention(entry, "/"));
        }
      });
    },
    [pickerSections, editorRef, sessionId]
  );

  const handleSubmit = useCallback(
    (text: string): boolean => {
      const mentions = editorRef.current?.getMentions() ?? [];
      const selection = selectionFromMentions(mentions);
      onSubmit(text, currentMessageFiles, selection);
      clearFiles({ suppressRefetch: true });
      // The kernel clears the editor after this returns; the session's
      // persistent selection re-arms as chips for the next message.
      rearmSelectionChips(selection);
      return true;
    },
    [clearFiles, currentMessageFiles, editorRef, onSubmit, rearmSelectionChips]
  );

  const handleQueueMessage = useCallback(
    (text: string): boolean => {
      if (!onQueueMessage) {
        return false;
      }
      const mentions = editorRef.current?.getMentions() ?? [];
      const selection = selectionFromMentions(mentions);
      onQueueMessage(text, currentMessageFiles, selection);
      clearFiles({ suppressRefetch: true });
      rearmSelectionChips(selection);
      return true;
    },
    [
      clearFiles,
      currentMessageFiles,
      editorRef,
      onQueueMessage,
      rearmSelectionChips,
    ]
  );

  const insertEntryAsChip = useCallback(
    (entry: PickerEntry) => {
      const connectionPath = pickerEntryConnectionPath(entry);
      if (connectionPath) {
        router.push(connectionPath);
        return;
      }
      editorRef.current?.insertMention(toMention(entry, "/"));
    },
    [editorRef, router]
  );

  const plusMenuItems = useMemo(
    () =>
      buildEntryMenuItems(
        pickerSections,
        {
          onAttachFiles: () => fileInputRef.current?.click(),
          onSelectEntry: insertEntryAsChip,
          onRemoveEntry: (entryKey: string) => {
            editorRef.current?.removeMention(entryKey);
          },
          activeEntries: activeMentionEntries,
          libraryFiles: libraryFileEntries.map((file) => ({
            id: file.fileId,
            name: file.name,
          })),
        },
        entryMenuT
      ),
    [
      pickerSections,
      insertEntryAsChip,
      activeMentionEntries,
      libraryFileEntries,
      entryMenuT,
      editorRef,
    ]
  );

  const topContent = (
    <InputChipStrip
      files={currentMessageFiles}
      entries={[]}
      onRemoveFile={removeFile}
      onRemoveEntry={() => undefined}
    />
  );

  const historyStorageKey = `onyx-prompt-history:craft:${user?.id ?? "anonymous"}`;

  return (
    <>
      <input
        ref={fileInputRef}
        type="file"
        className="hidden"
        multiple
        onChange={(e) => {
          const files = e.target.files;
          if (files && files.length > 0) uploadFiles(Array.from(files));
          e.target.value = "";
        }}
      />
      <ChatPromptEditor
        placeholder={placeholder ?? t("input.placeholder")}
        disabled={disabled}
        submitBlocked={hasUploadingFiles}
        isRunning={isRunning}
        isInterrupting={isInterrupting}
        onInterrupt={onInterrupt}
        onSubmit={handleSubmit}
        onQueueMessage={handleQueueMessage}
        queuedMessages={queuedMessages}
        onRemoveQueuedMessage={onRemoveQueuedMessage}
        hideQueueBar={hideQueueBar}
        historyStorageKey={historyStorageKey}
        draft={{ surface: "craft", scope: sessionId ?? "__draft__" }}
        slashTrigger={slashTrigger}
        mentionTriggers={[fileMentionTrigger]}
        onMentionsChange={setMentions}
        topContent={topContent}
        toolbarLeading={
          <>
            <PlusMenuButton
              items={plusMenuItems}
              disabled={disabled}
              tooltip={t("plusMenu.tooltip")}
            />
            {onDeepTaskToggle && (
              <SelectButton
                variant="select-light"
                icon={SvgWorkflow}
                onClick={onDeepTaskToggle}
                disabled={disabled}
                state={deepTask ? "selected" : "empty"}
                foldable={!deepTask}
                data-testid="craft-deep-task-toggle"
                aria-pressed={deepTask}
                aria-label={t("deepTask.toggleAriaLabel")}
                tooltip={
                  deepTask ? t("deepTask.onTooltip") : t("deepTask.offTooltip")
                }
              >
                {t("deepTask.label")}
              </SelectButton>
            )}
          </>
        }
        toolbarTrailing={
          <>
            {modelSelection !== null && (
              <ModelPickerButton
                selection={modelSelection}
                onChange={onModelChange}
                disabled={disabled}
              />
            )}
            {contextUsage && (
              <ContextUsageMeter
                usedTokens={contextUsage.usedTokens}
                contextLimit={contextUsage.contextLimit}
              />
            )}
            {thoughtLevel && (
              <ThoughtLevelSelect
                value={thoughtLevel.value}
                onChange={thoughtLevel.onChange}
                supportsReasoning={thoughtLevel.supportsReasoning}
                supportedEfforts={thoughtLevel.supportedEfforts}
                effortMax={thoughtLevel.effortMax}
                fallback={thoughtLevel.fallback}
                disabled={disabled}
              />
            )}
            {trailingExtras}
          </>
        }
        dragOverlayHint={t("dropFiles.hint")}
        onDropFiles={uploadFiles}
        onPasteFiles={uploadFiles}
        inputTestId="craft-message-input"
        editorRef={editorRef}
      />
    </>
  );
}

export default CraftComposer;
