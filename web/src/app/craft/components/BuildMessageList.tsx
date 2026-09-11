"use client";

import { useEffect, useMemo } from "react";
import useSWR from "swr";
import { CopyButton } from "@opal/components";
import { Hoverable } from "@opal/core";
import { SvgAlertCircle } from "@opal/icons";
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
  ToolPhaseRow,
} from "@/app/craft/components/turn-activity/PhaseRow";
import HumanMessage from "@/app/app/message/HumanMessage";
import CraftMessageAttachments from "@/app/craft/components/CraftMessageAttachments";
import { BuildMessage } from "@/app/craft/types/streamingTypes";
import { StreamItem, TodoListState } from "@/app/craft/types/displayTypes";
import {
  isHiddenJobTool,
  isHostContinueMessage,
} from "@/lib/craft-jobs/display";
import { foldTurnStream, stepSummary } from "@/lib/craft/foldTurnStream";

interface BuildMessageListProps {
  sessionId: string | null;
  attachmentRefreshKey?: number;
  messages: BuildMessage[];
  streamItems: StreamItem[];
  isStreaming?: boolean;
  /** Whether auto-scroll is enabled (user is at bottom) */
  autoScrollEnabled?: boolean;
  /**
   * Scrollable container wrapping this list. Auto-scroll moves it directly
   * rather than via scrollIntoView, which scrolls every ancestor.
   */
  scrollContainerRef: React.RefObject<HTMLDivElement | null>;
  /**
   * Trailing content attached to the last assistant block — either the
   * in-progress streaming area (if visible) or the last saved assistant
   * message. Used to render the approval cards inline so they read as
   * part of the agent's last turn instead of a separate message.
   */
  trailingAssistantSlot?: React.ReactNode;
}

/**
 * BuildMessageList - Displays the conversation history with FIFO rendering.
 *
 * Per-turn structure after filtering:
 *   phase rows (Thought / Explored / Edited / Ran), optional planning gap,
 *   then the answer. The in-progress turn pins the latest TodoListCard.
 */
export default function BuildMessageList({
  sessionId,
  attachmentRefreshKey = 0,
  messages,
  streamItems,
  isStreaming = false,
  autoScrollEnabled = true,
  scrollContainerRef,
  trailingAssistantSlot,
}: BuildMessageListProps) {
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (autoScrollEnabled && container) {
      container.scrollTo({ top: container.scrollHeight, behavior: "smooth" });
    }
  }, [
    messages.length,
    streamItems.length,
    autoScrollEnabled,
    scrollContainerRef,
  ]);

  // Resolve a connect card's app (oauth-vs-form, credential fields) by ID.
  const { data: connectableApps } = useSWR<ExternalAppUserResponse[]>(
    SWR_KEYS.buildExternalApps,
    errorHandlingFetcher
  );
  const appsById = useMemo(
    () => new Map((connectableApps ?? []).map((app) => [app.id, app])),
    [connectableApps]
  );

  const hasStreamItems = streamItems.length > 0;
  const lastMessage = messages[messages.length - 1];
  const lastMessageIsUser = lastMessage?.type === "user";
  const showStreamingArea =
    hasStreamItems ||
    (isStreaming && (lastMessageIsUser || messages.length === 0));

  const renderStreamItems = (
    rawItems: StreamItem[],
    opts: {
      isCurrentStream: boolean;
      extractLatestTodo: boolean;
    }
  ): { nodes: React.ReactNode[]; pinnedTodo: TodoListState | null } => {
    // Render items in stream order (tools, text, thinking interleaved).
    //
    // Filtering rules that apply first:
    // - Only the LATEST todo_list is kept (either pinned via extractLatestTodo
    //   or rendered inline at its original position).
    // - Thinking remains as a collapsed transcript row so users have a durable
    //   signal that the model spent time reasoning without opening by default.
    let latestTodoIdx = -1;
    rawItems.forEach((it, idx) => {
      if (it.type === "todo_list") latestTodoIdx = idx;
    });

    const items = rawItems.filter((it, idx) => {
      // Collapse to one todo_list per turn.
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
                  opts.isCurrentStream ? { opacity: 0, y: -4, height: 0 } : false
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
              <ToolPhaseRow
                key={row.id}
                phase={row.phase}
                tools={row.tools}
                autoCollapse={hasAnswer}
                summary={row.summary}
              />
            );
          case "text":
            return (
              <StepSummary key={row.id} text={stepSummary(row.content)} />
            );
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
      folded.showPlanningNext ? (
        <PlanningNextRow key="planning-next" />
      ) : null,
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
    trailing?: React.ReactNode
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
      <Hoverable.Root key={message.id} group="craftAgentMessage" width="full">
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
                </div>
              </Hoverable.Item>
            )}
            {trailing}
          </div>
        </div>
      </Hoverable.Root>
    );
  };

  // Index of the last saved assistant message — used to anchor the
  // trailingAssistantSlot (e.g. approval cards) when no streaming
  // response is currently in-flight. When streaming, the slot rides
  // along with the streaming area instead.
  const lastAssistantIndex = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i]?.type === "assistant") return i;
    }
    return -1;
  }, [messages]);

  const streamRender = hasStreamItems
    ? renderStreamItems(streamItems, {
        isCurrentStream: true,
        extractLatestTodo: true,
      })
    : null;

  return (
    <div className="flex flex-col items-center px-4 pb-4">
      <div className="w-full max-w-[720px] rounded-16 p-4">
        {messages.map((message, idx) => {
          if (message.type === "user") {
            if (isHostContinueMessage(message.message_metadata)) {
              return null;
            }
            return (
              <div key={message.id} className="py-4">
                {sessionId && message.attachments && (
                  <CraftMessageAttachments
                    sessionId={sessionId}
                    attachments={message.attachments}
                    refreshKey={attachmentRefreshKey}
                  />
                )}
                <HumanMessage content={message.content} nodeId={idx} />
              </div>
            );
          }
          if (message.type === "assistant") {
            // Anchor the trailing slot (e.g. approval cards) under the
            // last saved assistant message — but only when there's no
            // live streaming area, since that case has its own anchor
            // below.
            const trailing =
              !showStreamingArea && idx === lastAssistantIndex
                ? trailingAssistantSlot
                : null;
            return renderAgentMessage(message, trailing);
          }
          return null;
        })}

        {showStreamingArea && (
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
        )}
      </div>
    </div>
  );
}
