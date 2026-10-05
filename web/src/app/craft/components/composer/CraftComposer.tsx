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
import { buildEntryMenuItems } from "@/sections/input/buildEntryMenuItems";
import ModelPickerButton from "@/app/craft/components/ModelPickerButton";
import {
  useUploadFilesContext,
  type BuildFile,
} from "@/app/craft/contexts/UploadFilesContext";
import useUserSkills from "@/hooks/useUserSkills";
import useUserExternalApps from "@/hooks/useUserExternalApps";
import useScenarios from "@/hooks/useScenarios";
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
 * Slash (/) opens scenarios, skills, apps, and the compact command; @ opens
 * user-library files. Picks become atomic chips whose markdown serializes
 * into the prompt, and skill/scenario chips also drive the structured
 * selection sent with the message. The session's persistent selection is
 * re-armed as chips after each send, matching the old chip-strip behavior.
 * MCP servers are not picked here — enablement lives on /craft/v1/mcp-actions.
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
  let scenarioId: string | null = null;
  for (const mention of mentions) {
    if (mention.category === "skills") {
      skillIds.push(mention.value);
    } else if (mention.category === "scenarios") {
      scenarioId = mention.value;
    }
  }
  return { skillIds, scenarioId };
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
  const { data: scenarios } = useScenarios();

  const scenarioEntries = useMemo(
    () =>
      [...scenarios]
        .sort((a, b) => a.name.localeCompare(b.name))
        .map((scenario) => ({
          kind: "scenario" as const,
          scenarioId: scenario.id,
          name: scenario.name,
          description: scenario.description,
        })),
    [scenarios]
  );

  const pickerSections = useMemo(
    () => ({
      ...toPickerSections(skillsData, appsData),
      scenarios: scenarioEntries,
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
    [skillsData, appsData, scenarioEntries, compactAvailable, t]
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
      scenarios: [],
      skills: [],
      apps: [],
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

  // Skills-only menu on $ (ZCode's dedicated skills trigger; ¥/￥ for CJK
  // IMEs). Picks still insert the /slug chip — the trigger is just the menu
  // entry point.
  const skillsTrigger = useMemo(
    () => ({
      id: "craft-skills",
      triggerChars: ["$", "¥", "￥"] as const,
      sections: {
        commands: [],
        scenarios: [],
        skills: pickerSections.skills,
        apps: [],
        files: [],
      },
    }),
    [pickerSections]
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
  const selectionKey = (selection: SlashSelection): string =>
    `${sessionId ?? "draft"}:${selection.scenarioId ?? ""}:${selection.skillIds.join(",")}`;
  useEffect(() => {
    if (!persistedSelection || !editorRef.current) {
      return;
    }
    const key = selectionKey(persistedSelection);
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

  // A task carries at most one scenario (backend model is single-valued).
  // When a second scenario chip lands, drop the earlier ones, keeping the
  // most recent pick.
  useEffect(() => {
    const scenarioMentions = mentions.filter(
      (mention) => mention.category === "scenarios"
    );
    if (scenarioMentions.length <= 1) {
      return;
    }
    for (const stale of scenarioMentions.slice(0, -1)) {
      editorRef.current?.removeMention(stale.id);
    }
  }, [mentions, editorRef]);

  const activeMentionEntries = useMemo<PickerEntry[]>(() => {
    const skillIds = new Set(
      mentions.filter((m) => m.category === "skills").map((m) => m.value)
    );
    const active: PickerEntry[] = [];
    for (const skill of pickerSections.skills) {
      if (skillIds.has(skill.slug)) active.push(skill);
    }
    return active;
  }, [mentions, pickerSections]);

  const rearmSelectionChips = useCallback(
    (selection: SlashSelection) => {
      // The welcome composer goes away with the submit that created the
      // session; re-arming there would race the navigation and leak the
      // chips into the persisted `__draft__` for every future visit.
      if (sessionId === null) {
        return;
      }
      const entries = pickerEntriesFromSelection(pickerSections, selection);

      // Stamp the restore key: once these chips land, the persisted-selection
      // effect must treat them as restored. Without the stamp both paths
      // insert, duplicating the /skill prefix in the next message.
      restoreKeyRef.current = selectionKey(selection);
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

  // File chips currently in the editor drive the plus-menu library toggles:
  // checked = already attached, toggle inserts/removes the @mention chip.
  const attachedFileMentionIds = useMemo(
    () =>
      new Set(
        mentions
          .filter((mention) => mention.category === "files")
          .map((mention) => mention.value)
      ),
    [mentions]
  );

  const plusMenuItems = useMemo(
    () =>
      buildEntryMenuItems(
        {
          onAttachFiles: () => fileInputRef.current?.click(),
          libraryFiles: libraryFileEntries.map((file) => ({
            id: file.fileId,
            name: file.name,
            checked: attachedFileMentionIds.has(file.fileId),
            onToggle: (checked: boolean) => {
              if (checked) {
                editorRef.current?.insertMention(toMention(file, "@"));
              } else {
                editorRef.current?.removeMention(pickerEntryKey(file));
              }
            },
          })),
        },
        entryMenuT
      ),
    [libraryFileEntries, attachedFileMentionIds, editorRef, entryMenuT]
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
        mentionTriggers={[skillsTrigger, fileMentionTrigger]}
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
