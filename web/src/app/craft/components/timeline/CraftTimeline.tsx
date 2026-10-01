"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import useSWR from "swr";
import { useTranslations } from "next-intl";
import { useVirtualizer } from "@tanstack/react-virtual";
import { Button, CopyButton } from "@opal/components";
import { Hoverable } from "@opal/core";
import { SvgAlertCircle, SvgEdit, SvgRefreshCw } from "@opal/icons";
import { AnimatePresence, motion } from "motion/react";
import { Logo } from "@/lib/app/components";
import SetupCard from "@/app/craft/components/setup-requests/SetupCard";
import { ExternalAppUserResponse } from "@/app/craft/v1/apps/registry";
import { errorHandlingFetcher } from "@/lib/fetcher";
import { SWR_KEYS } from "@/lib/swr-keys";
import TextChunk from "@/app/craft/components/TextChunk";
import { BlinkingBar } from "@/app/app/message/BlinkingBar";
import { ErrorBanner } from "@/app/app/message/Resubmit";
import { RATE_LIMITED_ERROR_CODE } from "@/app/app/interfaces";
import { convertMarkdownTablesToTsv } from "@/app/app/message/copyingUtils";
import CompactionMarker from "@/app/craft/components/CompactionMarker";
import TodoListCard from "@/app/craft/components/TodoListCard";
import {
  PlanningNextRow,
  StepSummary,
  ThoughtRow,
} from "@/app/craft/components/turn-activity/PhaseRow";
import { ToolGroupRow } from "@/app/craft/components/tool-blocks/ToolGroupRow";
import { TurnStatusHeader } from "@/app/craft/components/timeline/TurnStatusHeader";
import HumanMessage from "@/app/app/message/HumanMessage";
import CraftMessageAttachments from "@/app/craft/components/CraftMessageAttachments";
import { BuildMessage } from "@/app/craft/types/streamingTypes";
import { StreamItem, TodoListState } from "@/app/craft/types/displayTypes";
import {
  isHiddenJobTool,
  isHostContinueMessage,
} from "@/lib/craft-jobs/display";
import { foldTurnStream, stepSummary } from "@/lib/craft/foldTurnStream";

interface CraftTimelineProps {
  sessionId: string | null;
  attachmentRefreshKey?: number;
  messages: BuildMessage[];
  streamItems: StreamItem[];
  isStreaming?: boolean;
  /**
   * Scrollable container wrapping this timeline. Auto-scroll moves it
   * directly rather than via scrollIntoView, which scrolls every ancestor.
   */
  scrollContainerRef: React.RefObject<HTMLDivElement | null>;
  /** Trailing content attached to the last assistant block (approvals). */
  trailingAssistantSlot?: React.ReactNode;
  /** Retry the last turn; shown on the final saved agent message when idle. */
  onRetry?: () => void;
  /** Edit-resend the last user message (inline editor on that message). */
  onEditResend?: (content: string) => void;
}

/**
 * CraftTimeline — ZCode ConversationTimeline pattern for craft:
 *
 * Saved history renders in a virtualized list (one item per message, dynamic
 * heights) so long sessions with hundreds of tool-heavy turns stay smooth;
 * the running turn renders below it as a non-virtualized "live tail" so
 * streaming never re-measures the virtual window.
 */
export default function CraftTimeline({
  sessionId,
  attachmentRefreshKey = 0,
  messages,
  streamItems,
  isStreaming = false,
  scrollContainerRef,
  trailingAssistantSlot,
  onRetry,
  onEditResend,
}: CraftTimelineProps) {
  const t = useTranslations("craft.timeline");
  // Resolve a connect card's app (oauth-vs-form, credential fields) by ID.
  const { data: connectableApps } = useSWR<ExternalAppUserResponse[]>(
    SWR_KEYS.buildExternalApps,
    errorHandlingFetcher,
  );
  const appsById = useMemo(
    () => new Map((connectableApps ?? []).map((app) => [app.id, app])),
    [connectableApps],
  );

  const hasStreamItems = streamItems.length > 0;
  const lastMessage = messages[messages.length - 1];
  const lastMessageIsUser = lastMessage?.type === "user";
  const showStreamingArea =
    hasStreamItems ||
    (isStreaming && (lastMessageIsUser || messages.length === 0));

  // ---- History items (virtualized) ----------------------------------------

  const historyItems = useMemo(() => {
    const items: { key: string; message: BuildMessage; index: number }[] = [];
    messages.forEach((message, index) => {
      if (
        message.type === "user" &&
        isHostContinueMessage(message.message_metadata)
      ) {
        return;
      }
      if (message.type !== "user" && message.type !== "assistant") {
        return;
      }
      items.push({ key: message.id, message, index });
    });
    return items;
  }, [messages]);

  const virtualizer = useVirtualizer({
    count: historyItems.length,
    getScrollElement: () => scrollContainerRef.current,
    estimateSize: () => 200,
    overscan: 8,
    getItemKey: (index) => historyItems[index]?.key ?? `row-${index}`,
    // jsdom (unit tests) reports a zero-sized scroll element and never fires
    // resize observers; seed a viewport so history rows still render there.
    initialRect: { width: 720, height: 600 },
  });

  // Content growth still needs to extend the virtual container's measured
  // heights; measure on message-count changes.
  useEffect(() => {
    virtualizer.measure();
  }, [messages.length, virtualizer]);

  // ---- Turn rendering (shared with the live tail) --------------------------

  const renderStreamItems = (
    rawItems: StreamItem[],
    opts: {
      isCurrentStream: boolean;
      extractLatestTodo: boolean;
    },
  ): { nodes: React.ReactNode[]; pinnedTodo: TodoListState | null } => {
    let latestTodoIdx = -1;
    rawItems.forEach((it, idx) => {
      if (it.type === "todo_list") latestTodoIdx = idx;
    });

    const items = rawItems.filter((it, idx) => {
      if (it.type === "todo_list" && idx !== latestTodoIdx) {
        return false;
      }
      if (opts.extractLatestTodo && it.type === "todo_list") {
        return false;
      }
      if (it.type === "question_ask") {
        return false;
      }
      if (it.type === "tool_call" && isHiddenJobTool(it.toolCall)) {
        return false;
      }
      return true;
    });

    const pinnedTodo =
      opts.extractLatestTodo && latestTodoIdx !== -1
        ? (
            rawItems[latestTodoIdx] as {
              type: "todo_list";
              todoList: TodoListState;
            }
          ).todoList
        : null;

    const folded = foldTurnStream(items, {
      isStreaming: opts.isCurrentStream,
    });
    const hasAnswer = folded.answer != null;

    const nodes = [
      ...folded.rows.map((row) => {
        switch (row.kind) {
          case "thought":
            return (
              <motion.div
                key={row.id}
                initial={
                  opts.isCurrentStream
                    ? { opacity: 0, y: -4, height: 0 }
                    : false
                }
                // oxlint-disable-next-line react-doctor/no-layout-property-animation -- height 0/auto must reflow the message list, transform cannot
                animate={{ opacity: 1, y: 0, height: "auto" }}
                // oxlint-disable-next-line react-doctor/no-layout-property-animation -- height/marginTop collapse must reflow the message list, transform cannot
                exit={{ opacity: 0, y: -6, height: 0, marginTop: 0 }}
                transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
              >
                <ThoughtRow
                  content={row.content}
                  isStreaming={row.isStreaming}
                  durationMs={row.durationMs}
                  summary={row.summary}
                />
              </motion.div>
            );
          case "tools":
            return (
              <ToolGroupRow
                key={row.id}
                phase={row.phase}
                tools={row.tools}
                autoCollapse={hasAnswer}
                summary={row.summary}
              />
            );
          case "text":
            return <StepSummary key={row.id} text={stepSummary(row.content)} />;
          case "todo_list":
            return (
              <div key={row.id}>
                <TodoListCard
                  todoList={row.todoList}
                  defaultOpen={row.todoList.isOpen}
                />
              </div>
            );
          case "connect_app_request":
            return (
              <div key={row.id}>
                <SetupCard
                  requestId={row.requestId}
                  externalAppId={row.externalAppId}
                  reason={row.reason}
                  userApp={appsById.get(row.externalAppId)}
                />
              </div>
            );
          case "compaction":
            return (
              <div key={row.id}>
                <CompactionMarker summary={row.summary} />
              </div>
            );
          case "error":
            if (row.rateLimit) {
              return (
                <div key={row.id}>
                  <ErrorBanner
                    error={row.content}
                    errorCode={RATE_LIMITED_ERROR_CODE}
                    isRetryable={false}
                    details={row.rateLimit}
                  />
                </div>
              );
            }
            return (
              <div
                key={row.id}
                className="flex items-start gap-2 rounded-08 border border-status-error-02 bg-status-error-00 px-3 py-2 text-sm text-status-error-05"
                role="alert"
              >
                <SvgAlertCircle className="mt-0.5 size-4 shrink-0 stroke-status-error-05" />
                <span className="min-w-0 break-words">{row.content}</span>
              </div>
            );
          default: {
            const _exhaustive: never = row;
            return _exhaustive;
          }
        }
      }),
      folded.showPlanningNext ? <PlanningNextRow key="planning-next" /> : null,
      folded.answer ? (
        <div key={folded.answer.id} className="mt-4">
          <TextChunk
            content={folded.answer.content}
            isStreaming={opts.isCurrentStream && folded.answer.isStreaming}
          />
        </div>
      ) : null,
    ];

    return { nodes, pinnedTodo };
  };

  const renderAgentMessage = (
    message: BuildMessage,
    trailing?: React.ReactNode,
    actionsExtra?: React.ReactNode,
  ) => {
    const savedStreamItems = message.message_metadata?.streamItems as
      | StreamItem[]
      | undefined;
    const savedRender =
      savedStreamItems && savedStreamItems.length > 0
        ? renderStreamItems(savedStreamItems, {
            isCurrentStream: false,
            extractLatestTodo: true,
          })
        : null;
    const visibleSavedRender =
      savedRender && (savedRender.pinnedTodo || savedRender.nodes.length > 0)
        ? savedRender
        : null;

    return (
      <Hoverable.Root group="craftAgentMessage" width="full">
        <div className="flex items-start gap-3 py-4">
          <div className="shrink-0 h-9 flex items-center">
            <Logo onyxBranded folded size={24} />
          </div>
          <div className="flex-1 flex flex-col gap-2 min-w-0">
            {visibleSavedRender ? (
              <>
                {visibleSavedRender.pinnedTodo && (
                  <div>
                    <TodoListCard
                      todoList={visibleSavedRender.pinnedTodo}
                      defaultOpen={visibleSavedRender.pinnedTodo.isOpen}
                    />
                  </div>
                )}
                {visibleSavedRender.nodes}
              </>
            ) : (
              <TextChunk content={message.content} />
            )}
            {message.content.trim() && (
              <Hoverable.Item
                group="craftAgentMessage"
                variant="appear-on-hover"
              >
                <div className="flex flex-row -ms-1">
                  <CopyButton
                    getCopyText={() =>
                      convertMarkdownTablesToTsv(message.content)
                    }
                    prominence="tertiary"
                    data-testid="CraftAgentMessage/copy-button"
                  />
                  {actionsExtra}
                </div>
              </Hoverable.Item>
            )}
            {trailing}
          </div>
        </div>
      </Hoverable.Root>
    );
  };

  const lastAssistantIndex = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i]?.type === "assistant") return i;
    }
    return -1;
  }, [messages]);

  // The last real user message owns edit-resend: the retry endpoint replaces
  // and re-runs the latest turn only.
  const lastUserIndex = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const message = messages[i];
      if (
        message?.type === "user" &&
        !isHostContinueMessage(message.message_metadata)
      ) {
        return i;
      }
    }
    return -1;
  }, [messages]);

  const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState("");
  const editDisabled = showStreamingArea;
  const startEdit = (message: BuildMessage) => {
    setEditDraft(message.content);
    setEditingMessageId(message.id);
  };
  const submitEdit = () => {
    const next = editDraft.trim();
    if (next && onEditResend) {
      onEditResend(next);
    }
    setEditingMessageId(null);
    setEditDraft("");
  };

  const streamRender = hasStreamItems
    ? renderStreamItems(streamItems, {
        isCurrentStream: isStreaming,
        extractLatestTodo: true,
      })
    : null;

  // The running turn started when the latest user message was sent; falls
  // back to mount time for restored sessions still marked running.
  const turnStartedAtMs = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const message = messages[i];
      if (message?.type === "user" && message.timestamp) {
        return new Date(message.timestamp).getTime();
      }
    }
    return Date.now();
    // Mount-time fallback must not re-derive on every stream item.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages.length]);

  const liveTailRef = useRef<HTMLDivElement | null>(null);

  return (
    <div className="flex flex-col items-center px-4 pb-4">
      <div className="w-full max-w-[720px] rounded-16 p-4">
        {/* Virtualized history: offscreen turns unmount, keeping long
            sessions cheap. Live streaming never enters this window. */}
        <div
          style={{
            height: virtualizer.getTotalSize(),
            width: "100%",
            position: "relative",
          }}
        >
          {virtualizer.getVirtualItems().map((virtualRow) => {
            const item = historyItems[virtualRow.index];
            if (!item) {
              return null;
            }
            const { message, index } = item;
            return (
              <div
                key={virtualRow.key}
                data-index={virtualRow.index}
                ref={virtualizer.measureElement}
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  width: "100%",
                  transform: `translateY(${virtualRow.start}px)`,
                }}
              >
                {message.type === "user" ? (
                  <Hoverable.Root group="craftUserMessage" width="full">
                    <div className="py-4">
                      {sessionId && message.attachments && (
                        <CraftMessageAttachments
                          sessionId={sessionId}
                          attachments={message.attachments}
                          refreshKey={attachmentRefreshKey}
                        />
                      )}
                      {editingMessageId === message.id ? (
                        <EditResendEditor
                          value={editDraft}
                          onChange={setEditDraft}
                          onSubmit={submitEdit}
                          onCancel={() => setEditingMessageId(null)}
                          submitLabel={t("editResend.submit")}
                          cancelLabel={t("editResend.cancel")}
                        />
                      ) : (
                        <>
                          <HumanMessage
                            content={message.content}
                            nodeId={index}
                          />
                          {!editDisabled &&
                            index === lastUserIndex &&
                            onEditResend && (
                              <Hoverable.Item
                                group="craftUserMessage"
                                variant="appear-on-hover"
                              >
                                <div className="flex flex-row -ms-1">
                                  <Button
                                    icon={SvgEdit}
                                    prominence="tertiary"
                                    tooltip={t("editResend.tooltip")}
                                    aria-label={t("editResend.tooltip")}
                                    data-testid="CraftUserMessage/edit-button"
                                    onClick={() => startEdit(message)}
                                  />
                                </div>
                              </Hoverable.Item>
                            )}
                        </>
                      )}
                    </div>
                  </Hoverable.Root>
                ) : (
                  renderAgentMessage(
                    message,
                    !showStreamingArea && index === lastAssistantIndex
                      ? trailingAssistantSlot
                      : null,
                    !showStreamingArea &&
                      index === lastAssistantIndex &&
                      onRetry ? (
                      <Button
                        icon={SvgRefreshCw}
                        prominence="tertiary"
                        tooltip={t("retryAction.tooltip")}
                        aria-label={t("retryAction.tooltip")}
                        data-testid="CraftAgentMessage/retry-button"
                        onClick={onRetry}
                      />
                    ) : null,
                  )
                )}
              </div>
            );
          })}
        </div>

        {/* Live tail: the running turn renders outside the virtual window so
            streaming updates never invalidate virtual measurements. */}
        {showStreamingArea && (
          <div ref={liveTailRef} data-craft-live-tail>
            <TurnStatusHeader
              startedAtMs={turnStartedAtMs}
              running={isStreaming}
            />
            <div className="flex items-start gap-3 py-4">
              <div className="shrink-0 mt-2">
                <Logo onyxBranded folded size={24} />
              </div>
              <div className="flex-1 flex flex-col gap-2 min-w-0">
                {streamRender?.pinnedTodo && (
                  <div>
                    <TodoListCard
                      todoList={streamRender.pinnedTodo}
                      defaultOpen={streamRender.pinnedTodo.isOpen}
                    />
                  </div>
                )}
                {!hasStreamItems ? (
                  <div className="h-9 flex items-center">
                    <BlinkingBar />
                  </div>
                ) : (
                  <AnimatePresence initial={false}>
                    {streamRender?.nodes}
                  </AnimatePresence>
                )}
                {trailingAssistantSlot}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

interface EditResendEditorProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onCancel: () => void;
  submitLabel: string;
  cancelLabel: string;
}

/** Inline editor for edit-resend: multiline textarea, Enter submits
 *  (Shift+Enter newlines), Escape cancels. */
function EditResendEditor({
  value,
  onChange,
  onSubmit,
  onCancel,
  submitLabel,
  cancelLabel,
}: EditResendEditorProps) {
  return (
    <div
      className="flex w-full flex-col gap-2 rounded-16 border border-border-02 bg-background-neutral-00 p-3"
      data-testid="CraftUserMessage/edit-editor"
    >
      <textarea
        autoFocus
        dir="auto"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            event.stopPropagation();
            onCancel();
            return;
          }
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            onSubmit();
          }
        }}
        rows={3}
        className="w-full resize-none bg-transparent text-text-05 outline-hidden"
      />
      <div className="flex flex-row justify-end gap-2">
        <Button prominence="tertiary" onClick={onCancel}>
          {cancelLabel}
        </Button>
        <Button
          prominence="primary"
          onClick={onSubmit}
          disabled={!value.trim()}
        >
          {submitLabel}
        </Button>
      </div>
    </div>
  );
}
