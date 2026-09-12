"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Button, Text } from "@opal/components";
import {
  SvgCpu,
  SvgLoader,
  SvgCheckCircle,
  SvgAlertTriangle,
  SvgChevronDown,
  SvgArrowRight,
} from "@opal/icons";
import { cn } from "@opal/utils";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/refresh-components/Collapsible";
import ToolActivityLine from "@/app/craft/components/turn-activity/ToolActivityLine";
import {
  useSubagent,
  useSubagents,
  useBuildSessionStore,
} from "@/app/craft/hooks/useBuildSessionStore";
import { useLaneTranscript } from "@/app/craft/hooks/useLaneTranscript";
import { useCraftJob } from "@/app/craft/components/CraftJobBanner";
import { latestSubagentActivity } from "@/app/craft/utils/subagentActivity";
import {
  childSessionIdForTask,
  isSettledToolStatus,
  laneTaskToolId,
  matchesLaneTaskToolId,
  taskRowStatus,
} from "@/app/craft/utils/laneTask";
import { isHiddenJobTool } from "@/lib/craft-jobs/display";
import type { ToolCardBodyProps } from "@/app/craft/components/tool-cards/interfaces";
import type { StreamItem } from "@/app/craft/types/displayTypes";

/**
 * Task row for every subagent type. Expands in place to the live process.
 * "Open" still swaps the main column to the full transcript.
 */
export default function TaskBody({ toolCall }: ToolCardBodyProps) {
  const t = useTranslations("craft.turnActivity");
  const subagents = useSubagents();
  const viewSubagent = useBuildSessionStore((s) => s.viewSubagent);
  const seedSubagentMeta = useBuildSessionStore((s) => s.seedSubagentMeta);

  const parentSessionId = useBuildSessionStore((s) => s.currentSessionId);
  const { data: craftJob } = useCraftJob(parentSessionId);
  const settled = isSettledToolStatus(toolCall.status);
  const specialist = (craftJob?.specialists ?? []).find((row) =>
    toolCall.subagentSessionId
      ? row.session_id === toolCall.subagentSessionId
      : !settled &&
        !!row.node_id &&
        matchesLaneTaskToolId(toolCall.id, laneTaskToolId(row.node_id))
  );
  const linkedSessionId = childSessionIdForTask(
    toolCall.id,
    toolCall.subagentSessionId,
    subagents.values(),
    { allowRematch: !settled }
  );
  const subagent = useSubagent(linkedSessionId);

  const status = taskRowStatus(
    subagent?.status,
    toolCall.status,
    specialist?.status,
    specialist ? craftJob?.status : undefined
  );

  const label = toolCall.description || "Spawning subagent";
  const seedName = toolCall.description || toolCall.title || label;
  const activity =
    latestSubagentActivity(subagent) || specialist?.last_activity || "";
  const expandable = linkedSessionId !== null;
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    if (!parentSessionId || !linkedSessionId) return;
    seedSubagentMeta(
      parentSessionId,
      linkedSessionId,
      toolCall.id,
      toolCall.subagentType ?? null,
      seedName,
      toolCall.command || ""
    );
  }, [
    parentSessionId,
    linkedSessionId,
    toolCall.id,
    toolCall.subagentType,
    toolCall.command,
    seedName,
    seedSubagentMeta,
  ]);

  useLaneTranscript({
    open: isOpen,
    parentSessionId,
    childSessionId: linkedSessionId,
    parentToolCallId: toolCall.id,
    running: status === "running",
  });

  const lastTurn = subagent?.turns[subagent.turns.length - 1];
  const processItems = (lastTurn?.streamItems ?? []).filter((item) => {
    return item.type !== "tool_call" || !isHiddenJobTool(item.toolCall);
  });

  function openFull(event: { stopPropagation: () => void }) {
    event.stopPropagation();
    if (!parentSessionId || !linkedSessionId) return;
    seedSubagentMeta(
      parentSessionId,
      linkedSessionId,
      toolCall.id,
      toolCall.subagentType ?? null,
      seedName,
      toolCall.command || ""
    );
    viewSubagent(parentSessionId, linkedSessionId);
  }

  const header = (
    <div className="flex min-w-0 w-full items-center gap-2">
      <SvgCpu className="h-4 w-4 shrink-0 stroke-action-selection-05" />
      <span className="min-w-0 flex-1 overflow-hidden">
        <Text as="p" font="main-ui-action" color="text-04" maxLines={1}>
          {label}
        </Text>
        {activity ? (
          <Text as="p" font="secondary-mono" color="text-03" maxLines={1}>
            {activity}
          </Text>
        ) : null}
      </span>
      {status === "running" && (
        <SvgLoader className="h-4 w-4 shrink-0 animate-spin stroke-action-selection-05" />
      )}
      {status === "done" && (
        <SvgCheckCircle className="h-4 w-4 shrink-0 stroke-status-success-05" />
      )}
      {status === "failed" && (
        <SvgAlertTriangle className="h-4 w-4 shrink-0 stroke-status-error-05" />
      )}
      <SvgChevronDown
        aria-hidden={!expandable}
        className={cn(
          "size-3.5 shrink-0 stroke-text-03 transition-transform duration-150",
          !isOpen && "-rotate-90",
          !expandable && "invisible"
        )}
      />
    </div>
  );

  if (!expandable) {
    return <div className="w-full min-w-0 py-0.5">{header}</div>;
  }

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <CollapsibleTrigger asChild>
        <button
          type="button"
          aria-label={t("expandTask", { label })}
          className="w-full min-w-0 rounded-sm py-0.5 text-start hover:bg-background-tint-02"
        >
          {header}
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="flex min-w-0 flex-col gap-1 ps-6 pb-1">
          <div className="max-h-48 overflow-y-auto">
            {processItems.length === 0 ? (
              <Text font="main-ui-muted" color="text-03">
                {t("taskWaiting")}
              </Text>
            ) : (
              processItems.map((item) => (
                <TaskProcessItem key={item.id} item={item} />
              ))
            )}
          </div>
          <Button
            type="button"
            size="xs"
            prominence="tertiary"
            icon={SvgArrowRight}
            onClick={openFull}
          >
            {t("openTranscript")}
          </Button>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

function TaskProcessItem({ item }: { item: StreamItem }) {
  if (item.type === "tool_call") {
    if (item.toolCall.kind === "task") {
      return (
        <Text as="p" font="main-ui-muted" color="text-03" maxLines={1}>
          {item.toolCall.description || item.toolCall.title}
        </Text>
      );
    }
    return <ToolActivityLine toolCall={item.toolCall} />;
  }
  if (item.type === "thinking" && item.content) {
    return (
      <Text as="p" font="main-ui-muted" color="text-03" maxLines={3}>
        {item.content}
      </Text>
    );
  }
  return null;
}
