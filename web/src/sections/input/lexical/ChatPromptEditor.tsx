"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type DragEvent,
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
  type RefObject,
} from "react";
import { useTranslations } from "next-intl";
import { Button, Text } from "@opal/components";
import { SvgArrowUp, SvgLoader, SvgStop } from "@opal/icons";
import { cn } from "@opal/utils";
import Keycap from "@/refresh-components/Keycap";
import {
  EMPTY_QUEUED_MESSAGES,
  MAX_QUEUED_MESSAGES,
  type QueuedMessage,
} from "@/app/app/interfaces";
import QueuedMessageBar from "@/sections/input/QueuedMessageBar";
import InterruptHint from "@/sections/input/InterruptHint";
import { resolveComposerPrimaryAction } from "@/sections/input/composerPrimaryAction";
import { getPastedFilesIfNoText } from "@/lib/clipboard";
import LexicalChatInput from "@/sections/input/lexical/LexicalChatInput";
import {
  appendStoredPromptHistory,
  readStoredPromptHistory,
} from "@/sections/input/lexical/promptHistory";
import {
  clearComposerDraft,
  persistComposerDraft,
  readComposerDraft,
} from "@/sections/input/lexical/draftStore";
import type {
  ComposerMention,
  LexicalPasteEvent,
  LexicalPromptInputHandle,
  TriggerMenuConfig,
} from "@/sections/input/lexical/types";

/**
 * Shell around the Lexical kernel: Onyx composer chrome (surface, drag
 * overlay, toolbar row, primary action) plus the ZCode-style behaviors that
 * live above the editor — prompt history recording, draft persistence, the
 * send/queue/stop state machine, and slots for surface-specific content.
 */

interface ChatPromptEditorProps {
  placeholder?: string;
  disabled?: boolean;
  /** Blocks submit (e.g. uploads in flight) without the disabled visual. */
  submitBlocked?: boolean;
  isRunning?: boolean;
  isInterrupting?: boolean;
  /** Spinner state that is not a stoppable interrupt (e.g. query
   * classification); defaults to isInterrupting. */
  isBusy?: boolean;
  onInterrupt?: () => void;

  onSubmit: (text: string) => boolean | void;
  /** Providing this enables queueing follow-ups while a turn runs. */
  onQueueMessage?: (text: string) => boolean | void;
  queuedMessages?: readonly QueuedMessage[];
  onRemoveQueuedMessage?: (index: number) => void;
  /** Surfaces rendering their own queue UI hide the built-in bar. */
  hideQueueBar?: boolean;

  /** Esc while not composing: cancel (inline edit mode). */
  onCancel?: () => void;
  onChange?: (text: string) => void;
  /** Fires whenever the set of chips in the editor changes. */
  onMentionsChange?: (mentions: ComposerMention[]) => void;
  onFocus?: () => void;

  /** Prompt history: entries to browse plus the storage key that records
   * submitted prompts (per user + surface). */
  promptHistory?: readonly string[];
  historyStorageKey?: string | null;

  /** Draft persistence scope; null disables drafts. */
  draft?: { surface: string; scope: string } | null;

  slashTrigger?: TriggerMenuConfig | null;
  mentionTriggers?: readonly TriggerMenuConfig[] | null;

  topContent?: ReactNode;
  toolbarLeading?: ReactNode;
  /** Rendered in the right control group, left of the primary action. */
  toolbarTrailing?: ReactNode;
  submitControl?: ReactNode;

  /** Collapse large pastes into editable tiles (the paste_as_tile pref). */
  pasteTilesEnabled?: boolean;

  /** External-file drag overlay; requires onDropFiles. */
  dragOverlayHint?: string;
  onDropFiles?: (files: File[]) => void;
  onPasteFiles?: (files: File[]) => void;

  inputTestId?: string;
  /** DOM id for the editable element (e2e continuity). */
  inputId?: string;
  /** DOM id for the primary-action button (e2e continuity). */
  submitButtonId?: string;
  editorRef?: RefObject<LexicalPromptInputHandle | null>;
  /** One-shot text sync on mount (inline edit prefill); skipped when a draft
   * for the scope exists. */
  initialValue?: string;
  className?: string;
}

const DRAFT_SAVE_DEBOUNCE_MS = 500;

function noopHighlight(_index: number | null) {}

function ChatPromptEditor({
  placeholder,
  disabled = false,
  submitBlocked = false,
  isRunning = false,
  isInterrupting = false,
  isBusy,
  onInterrupt,
  onSubmit,
  onQueueMessage,
  queuedMessages,
  onRemoveQueuedMessage,
  hideQueueBar = false,
  onCancel,
  onChange,
  onMentionsChange,
  onFocus,
  promptHistory,
  historyStorageKey = null,
  draft = null,
  slashTrigger = null,
  mentionTriggers = null,
  topContent,
  toolbarLeading,
  toolbarTrailing,
  submitControl,
  dragOverlayHint,
  onDropFiles,
  onPasteFiles,
  inputTestId,
  inputId,
  submitButtonId,
  pasteTilesEnabled = false,
  editorRef,
  initialValue,
  className,
}: ChatPromptEditorProps) {
  const t = useTranslations("chat.promptEditor");
  const localEditorRef = useRef<LexicalPromptInputHandle | null>(null);
  const resolvedEditorRef = editorRef ?? localEditorRef;

  const [text, setText] = useState(initialValue ?? "");
  const [isDraggingOver, setIsDraggingOver] = useState(false);
  const [historyEntries, setHistoryEntries] = useState<readonly string[]>(() =>
    historyStorageKey ? readStoredPromptHistory(historyStorageKey) : [],
  );

  const effectiveHistory = promptHistory ?? historyEntries;

  const queue = queuedMessages ?? EMPTY_QUEUED_MESSAGES;
  const queueEnabled = !!onQueueMessage;
  const canQueue = queueEnabled && queue.length < MAX_QUEUED_MESSAGES;
  const interruptible = !!onInterrupt && isRunning;
  const primaryAction = resolveComposerPrimaryAction({
    isRunning,
    hasText: text.trim().length > 0,
    canQueue,
    isBusy: isBusy ?? isInterrupting,
    canStop: interruptible,
  });
  const actionDisabled =
    disabled ||
    submitBlocked ||
    primaryAction === "busy" ||
    (primaryAction === "send" && (!text.trim() || isRunning)) ||
    (primaryAction === "queue" && (!text.trim() || !canQueue));

  // ---- Draft persistence -------------------------------------------------

  const draftScopeKey = draft ? `${draft.surface}:${draft.scope}` : null;
  const draftRestoreDoneRef = useRef<string | null>(null);
  const draftSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const handle = resolvedEditorRef.current;
    if (!handle || !draft || !draftScopeKey) {
      return;
    }
    if (draftRestoreDoneRef.current === draftScopeKey) {
      return;
    }
    draftRestoreDoneRef.current = draftScopeKey;

    const snapshot = readComposerDraft(draft.surface, draft.scope);
    if (!snapshot) {
      if (initialValue !== undefined) {
        setText(initialValue);
        handle.setText(initialValue);
      }
      return;
    }
    setText(snapshot.text);
    if (
      !snapshot.editorStateJson ||
      !handle.setEditorStateJson(snapshot.editorStateJson)
    ) {
      handle.setText(snapshot.text);
    }
    // Only the onChange listener after restore keeps the draft in sync.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft, draftScopeKey]);

  const scheduleDraftSave = useCallback(
    (nextText: string) => {
      if (!draft || !draftScopeKey) {
        return;
      }
      if (draftSaveTimerRef.current) {
        clearTimeout(draftSaveTimerRef.current);
      }
      const surface = draft.surface;
      const scope = draft.scope;
      draftSaveTimerRef.current = setTimeout(() => {
        const editorStateJson = nextText.trim()
          ? resolvedEditorRef.current?.getEditorStateJson()
          : undefined;
        persistComposerDraft(surface, scope, {
          text: nextText,
          editorStateJson,
        });
      }, DRAFT_SAVE_DEBOUNCE_MS);
    },
    [draft, draftScopeKey, resolvedEditorRef],
  );

  useEffect(() => {
    return () => {
      if (draftSaveTimerRef.current) {
        clearTimeout(draftSaveTimerRef.current);
      }
    };
  }, []);

  // ---- Submit chain ------------------------------------------------------

  const recordHistory = useCallback(
    (submittedText: string) => {
      if (!historyStorageKey) {
        return;
      }
      setHistoryEntries(
        appendStoredPromptHistory(historyStorageKey, submittedText),
      );
    },
    [historyStorageKey],
  );

  // Reads the live editor text (not React state) so programmatic fills —
  // draft restore, prefilled chips — submit correctly on the same tick.
  const submitDraft = useCallback((): boolean => {
    const handle = resolvedEditorRef.current;
    const currentText = handle?.getText() ?? "";
    if (!currentText.trim()) {
      return false;
    }

    const shouldQueue = isRunning && canQueue;
    if (shouldQueue && onQueueMessage) {
      const queueResult = onQueueMessage(currentText);
      if (queueResult === false) {
        return false;
      }
      recordHistory(currentText);
      handle?.clear();
      setText("");
      if (draft && draftScopeKey) {
        clearComposerDraft(draft.surface, draft.scope);
      }
      return true;
    }

    const submitResult = onSubmit(currentText);
    if (submitResult === false) {
      // The surface rejected the submit; keep the draft in the editor.
      return false;
    }
    recordHistory(currentText);
    handle?.clear();
    setText("");
    if (draft && draftScopeKey) {
      clearComposerDraft(draft.surface, draft.scope);
    }
    return true;
  }, [
    canQueue,
    draft,
    draftScopeKey,
    isRunning,
    onQueueMessage,
    onSubmit,
    recordHistory,
    resolvedEditorRef,
  ]);

  const handleFormSubmit = useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      if (actionDisabled || primaryAction === "stop") {
        return;
      }
      submitDraft();
    },
    [actionDisabled, primaryAction, submitDraft],
  );

  const handlePrimaryAction = useCallback(() => {
    if (primaryAction === "stop") {
      if (interruptible && !isInterrupting) {
        onInterrupt?.();
      }
      return;
    }
    submitDraft();
  }, [interruptible, isInterrupting, onInterrupt, primaryAction, submitDraft]);

  const handleEditorSubmit = useCallback(() => {
    // Enter never interrupts a run: with an empty draft submitDraft is a
    // no-op, and with text it queues or sends depending on canQueue.
    return submitDraft();
  }, [submitDraft]);

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLFormElement>) => {
      if (event.key !== "Escape") {
        return;
      }
      // A dialog consuming the Escape (Radix portals) must not also cancel
      // the composer.
      if (
        event.defaultPrevented ||
        (event.target instanceof Element &&
          event.target.closest('[role="dialog"]'))
      ) {
        return;
      }
      if (onCancel) {
        event.preventDefault();
        onCancel();
        return;
      }
      if (interruptible && !isInterrupting) {
        event.preventDefault();
        onInterrupt?.();
      }
    },
    [interruptible, isInterrupting, onCancel, onInterrupt],
  );

  // ---- Editor callbacks ---------------------------------------------------

  const handleChange = useCallback(
    (nextText: string) => {
      setText(nextText);
      onChange?.(nextText);
      scheduleDraftSave(nextText);
    },
    [onChange, scheduleDraftSave],
  );

  const handlePaste = useCallback(
    (event: LexicalPasteEvent) => {
      if (!event.clipboardData || !onPasteFiles) {
        return;
      }
      const files = getPastedFilesIfNoText(event.clipboardData);
      if (files.length > 0) {
        event.preventDefault();
        onPasteFiles(files);
      }
    },
    [onPasteFiles],
  );

  // ---- Drag & drop overlay ------------------------------------------------

  const handleDragOver = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      if (
        onDropFiles &&
        Array.from(event.dataTransfer.types).includes("Files")
      ) {
        event.preventDefault();
        event.dataTransfer.dropEffect = "copy";
        setIsDraggingOver(true);
      }
    },
    [onDropFiles],
  );

  const handleDragLeave = useCallback((event: DragEvent<HTMLDivElement>) => {
    const nextTarget = event.relatedTarget;
    if (
      nextTarget instanceof Node &&
      event.currentTarget.contains(nextTarget)
    ) {
      return;
    }
    setIsDraggingOver(false);
  }, []);

  const handleDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      setIsDraggingOver(false);
      if (!onDropFiles) {
        return;
      }
      const files = Array.from(event.dataTransfer.files);
      if (files.length === 0) {
        return;
      }
      event.preventDefault();
      onDropFiles(files);
    },
    [onDropFiles],
  );

  const showQueueHint =
    !text && queueEnabled && queue.length > 0 && primaryAction !== "busy";

  return (
    // Escape = cancel (inline edit) or interrupt. Kept on the form, not the
    // document, so the picker popover's capture-phase Escape (close menu)
    // stops propagation before it ever reaches this handler.
    // oxlint-disable-next-line jsx-a11y/no-noninteractive-element-interactions
    <form
      onSubmit={handleFormSubmit}
      onKeyDown={handleKeyDown}
      className={cn("relative", className)}
    >
      {queueEnabled && !hideQueueBar && (
        <QueuedMessageBar
          messages={queue}
          highlightedIndex={null}
          onDiscard={(index) => onRemoveQueuedMessage?.(index)}
          onHighlight={noopHighlight}
        />
      )}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={cn(
          "relative flex w-full flex-col bg-background-neutral-00 shadow-box-01 rounded-16",
          isDraggingOver && "ring-1 ring-border-03",
        )}
      >
        {isDraggingOver && dragOverlayHint ? (
          <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center rounded-16 bg-background-tint-02">
            <div className="flex items-center rounded-08 border border-border-02 bg-background-neutral-00 px-4 py-2">
              <Text font="secondary-body" color="text-02">
                {dragOverlayHint}
              </Text>
            </div>
          </div>
        ) : null}

        {topContent}
        <LexicalChatInput
          placeholder={placeholder}
          disabled={disabled}
          submitDisabled={submitBlocked || (isRunning && !canQueue)}
          onSubmit={handleEditorSubmit}
          onChange={handleChange}
          onMentionsChange={onMentionsChange}
          onFocus={onFocus}
          inputTestId={inputTestId}
          inputId={inputId}
          pasteTilesEnabled={pasteTilesEnabled}
          editorApiRef={resolvedEditorRef}
          promptHistory={effectiveHistory}
          slashTrigger={slashTrigger}
          mentionTriggers={mentionTriggers}
          onPaste={handlePaste}
        />
        <div className="flex min-h-10 w-full items-center justify-between p-1">
          <div className="flex flex-row items-center gap-2">
            {toolbarLeading}
            {interruptible && <InterruptHint interrupting={isInterrupting} />}
            {showQueueHint ? (
              <div className="flex select-none items-center gap-1">
                <Keycap>↑</Keycap>
                <Text font="secondary-body" color="text-02">
                  {t("queuedMessagesHint.text")}
                </Text>
              </div>
            ) : null}
          </div>
          <div className="flex flex-row items-center gap-1">
            {toolbarTrailing}
            {submitControl ?? (
              <Button
                id={submitButtonId}
                data-testid="composer-primary-action"
                icon={
                  primaryAction === "busy"
                    ? ({ className, style }) => (
                        <SvgLoader
                          className={cn(className, "animate-spin")}
                          style={style}
                        />
                      )
                    : primaryAction === "stop"
                      ? SvgStop
                      : SvgArrowUp
                }
                onClick={handlePrimaryAction}
                disabled={actionDisabled}
                tooltip={
                  primaryAction === "stop"
                    ? t("stopButton.tooltip")
                    : primaryAction === "queue"
                      ? t("sendButton.queueLabel")
                      : t("sendButton.sendLabel")
                }
                aria-label={
                  primaryAction === "stop"
                    ? t("stopButton.ariaLabel")
                    : primaryAction === "queue"
                      ? t("sendButton.queueLabel")
                      : t("sendButton.sendLabel")
                }
              />
            )}
          </div>
        </div>
      </div>
    </form>
  );
}

export default ChatPromptEditor;
