"use client";

import { useMemo, type ReactNode } from "react";
import { useTranslations } from "next-intl";
import { Text } from "@opal/components";
import { cn } from "@opal/utils";
import { ToolLayout } from "@/app/craft/components/tool-blocks/ToolLayout";
import TaskBody from "@/app/craft/components/tool-cards/TaskBody";
import BashBody from "@/app/craft/components/tool-cards/BashBody";
import DiffBody from "@/app/craft/components/tool-cards/DiffBody";
import ReadBody from "@/app/craft/components/tool-cards/ReadBody";
import SearchBody from "@/app/craft/components/tool-cards/SearchBody";
import WebSearchBody from "@/app/craft/components/tool-cards/WebSearchBody";
import WebFetchBody from "@/app/craft/components/tool-cards/WebFetchBody";
import GenericBody from "@/app/craft/components/tool-cards/GenericBody";
import {
  getToolIcon,
  isSkillCall,
  isSkillInvocation,
} from "@/app/craft/components/tool-cards/helpers";
import type {
  ToolCallState,
  ToolCallStatus,
} from "@/app/craft/types/displayTypes";

/**
 * ToolCallBlock — one agent tool invocation on the ZCode pattern: a compact
 * summary row (tool icon, kind label, mono primary text, diff counts, status
 * word) over a collapsible body, with per-tool-call persisted open state.
 * Bodies are the existing per-tool renderers from `tool-cards/`.
 */

interface DiffCounts {
  added: number;
  removed: number;
}

function lineDiffCounts(
  oldContent: string | undefined,
  newContent: string | undefined
): DiffCounts | null {
  if (newContent === undefined) {
    return null;
  }
  const oldLines = (oldContent ?? "").split("\n");
  const newLines = newContent.split("\n");
  const oldCount = new Map<string, number>();
  for (const line of oldLines) {
    oldCount.set(line, (oldCount.get(line) ?? 0) + 1);
  }
  let added = 0;
  for (const line of newLines) {
    const remaining = oldCount.get(line) ?? 0;
    if (remaining > 0) {
      oldCount.set(line, remaining - 1);
    } else {
      added += 1;
    }
  }
  let removed = 0;
  for (const count of oldCount.values()) {
    removed += count;
  }
  if (added === 0 && removed === 0) {
    return null;
  }
  return { added, removed };
}

function statusLabelKey(status: ToolCallStatus): string | null {
  switch (status) {
    case "pending":
    case "in_progress":
      return "status.running";
    case "completed":
      return "status.done";
    case "failed":
      return "status.failed";
    case "cancelled":
      return "status.cancelled";
    default:
      return null;
  }
}

function kindLabelKey(toolCall: ToolCallState): string {
  if (toolCall.toolName === "skill") {
    return "kind.skill";
  }
  switch (toolCall.kind) {
    case "execute":
      return "kind.terminal";
    case "edit":
      return toolCall.isNewFile ? "kind.write" : "kind.edit";
    case "read":
      return "kind.read";
    case "search":
      return toolCall.toolName === "websearch"
        ? "kind.webSearch"
        : "kind.search";
    case "task":
      return "kind.agent";
    case "other":
    default:
      return toolCall.toolName === "webfetch" ? "kind.fetch" : "kind.other";
  }
}

interface FileNavProps {
  /** Open this edit's diff in the output panel (edit with a patch). */
  openDiff?: (toolCall: ToolCallState) => void;
  /** Open the file itself in the output panel (write of a new file). */
  openFile?: (path: string) => void;
}

function primaryTextFor(
  toolCall: ToolCallState,
  nav?: FileNavProps
): ReactNode {
  const text = toolCall.command || toolCall.description || toolCall.title;
  const filePath = toolCall.filePath;
  const clickable =
    nav &&
    filePath &&
    (toolCall.kind === "edit" || toolCall.toolName === "write");
  if (clickable && nav) {
    const onClick = (e: React.MouseEvent) => {
      e.stopPropagation();
      if (toolCall.toolName === "write" && !toolCall.oldContent) {
        nav.openFile?.(filePath);
      } else {
        nav.openDiff?.(toolCall);
      }
    };
    return (
      <span
        role="button"
        tabIndex={0}
        onMouseDown={(e) => e.stopPropagation()}
        onClick={onClick}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") onClick(e as never);
        }}
        className="group/file-chip cursor-pointer rounded-sm bg-background-tint-01 px-1 underline-offset-2 hover:bg-background-tint-02 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-border-03"
        data-testid="tool-file-chip"
        title={filePath}
      >
        <Text font="secondary-mono" color="text-04" nowrap>
          {text}
        </Text>
      </span>
    );
  }
  return (
    <span className="rounded-sm bg-background-tint-01 px-1">
      <Text font="secondary-mono" color="text-04" nowrap>
        {text}
      </Text>
    </span>
  );
}

function renderBody(toolCall: ToolCallState) {
  if (toolCall.toolName === "websearch") {
    return <WebSearchBody toolCall={toolCall} />;
  }
  if (toolCall.toolName === "webfetch") {
    return <WebFetchBody toolCall={toolCall} />;
  }
  switch (toolCall.kind) {
    case "execute":
      return <BashBody toolCall={toolCall} />;
    case "edit":
      return <DiffBody toolCall={toolCall} />;
    case "read":
      return <ReadBody toolCall={toolCall} />;
    case "search":
      return <SearchBody toolCall={toolCall} />;
    case "other":
    default:
      return <GenericBody toolCall={toolCall} />;
  }
}

function hasBodyContent(toolCall: ToolCallState): boolean {
  if (toolCall.toolName === "websearch" || toolCall.toolName === "webfetch") {
    return !!toolCall.rawOutput;
  }
  if (toolCall.toolName === "write") {
    return false;
  }
  switch (toolCall.kind) {
    case "execute":
      return !!(toolCall.command || toolCall.rawOutput);
    case "edit":
      return !!(toolCall.newContent || toolCall.oldContent);
    case "read":
    case "search":
      return !!toolCall.rawOutput;
    case "task":
      return !!(toolCall.command || toolCall.taskOutput || toolCall.rawOutput);
    case "other":
    default:
      return !!toolCall.rawOutput;
  }
}

interface ToolCallBlockProps {
  toolCall: ToolCallState;
  /** Nested inside a group row: the group carries comet/skill chrome. */
  nested?: boolean;
  /** Panel navigation for clickable file chips (diff/file preview). */
  nav?: FileNavProps;
}

function ToolCallBlock({ toolCall, nested = false, nav }: ToolCallBlockProps) {
  const t = useTranslations("craft.toolBlocks");
  const running =
    toolCall.status === "pending" || toolCall.status === "in_progress";
  const failed = toolCall.status === "failed";

  const diffCounts = useMemo(
    () =>
      toolCall.kind === "edit" && !running
        ? lineDiffCounts(toolCall.oldContent, toolCall.newContent)
        : null,
    [toolCall.kind, toolCall.oldContent, toolCall.newContent, running]
  );

  // The task tool is its own clickable row that navigates to the spawned
  // subagent's transcript — not a collapsible block.
  if (toolCall.kind === "task") {
    return <TaskBody toolCall={toolCall} />;
  }

  const Icon = getToolIcon(toolCall.kind);
  const labelKey = statusLabelKey(toolCall.status);
  // Failures surface the error on the status word's tooltip; the raw output
  // usually carries the stderr tail.
  const errorTooltip =
    failed && toolCall.rawOutput ? toolCall.rawOutput.slice(-2000) : undefined;

  return (
    <div
      className={cn(
        "rounded-08 px-1",
        failed && "bg-status-error-00",
        !nested &&
          isSkillInvocation(toolCall) &&
          !failed &&
          "border-[0.5px] border-border-01"
      )}
    >
      <ToolLayout
        toolId={toolCall.id}
        icon={<Icon className="size-4 shrink-0" />}
        kindLabel={t(kindLabelKey(toolCall))}
        primaryText={primaryTextFor(toolCall, nav)}
        secondaryText={
          toolCall.skillName && toolCall.toolName !== "skill" ? (
            <Text font="secondary-body" color="text-04" nowrap>
              {toolCall.skillName}
            </Text>
          ) : undefined
        }
        diffCount={
          diffCounts ? (
            <span className="flex shrink-0 items-baseline gap-1 font-secondary-action">
              <span className="text-status-success-05">
                +{diffCounts.added}
              </span>
              <span className="text-status-error-05">
                −{diffCounts.removed}
              </span>
            </span>
          ) : undefined
        }
        statusLabel={labelKey ? t(labelKey) : undefined}
        statusTooltip={failed ? errorTooltip : undefined}
        isRunning={running}
        // Completed edits and reads auto-open once so the result is seen;
        // everything else stays collapsed until clicked.
        autoOpen={
          !running &&
          (toolCall.kind === "edit" || failed) &&
          hasBodyContent(toolCall)
        }
        title={toolCall.title}
        content={renderBody(toolCall)}
      />
    </div>
  );
}

export default ToolCallBlock;
