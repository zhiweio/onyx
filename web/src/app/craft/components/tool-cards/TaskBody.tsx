"use client";

import { useEffect } from "react";
import { useTranslations } from "next-intl";
import { Text } from "@opal/components";
import { SvgCheckCircle, SvgAlertTriangle, SvgLoader } from "@opal/icons";
import { cn } from "@opal/utils";
import ShimmerText from "@/refresh-components/texts/ShimmerText";
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
import type { ToolCardBodyProps } from "@/app/craft/components/tool-cards/interfaces";
import { CATEGORY_AGENT_ICON } from "@/lib/skills/categoryIcons";

/**
 * SubAgent row, ZCode-style: a single-line summary
 * `[bot] SubAgent · <task description>` with the latest child activity as a
 * secondary line. The whole row opens the subagent's full timeline (main
 * column swap to SubagentView); the parent conversation keeps only this
 * summary — no in-place expansion.
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
        matchesLaneTaskToolId(toolCall.id, laneTaskToolId(row.node_id)),
  );
  const linkedSessionId = childSessionIdForTask(
    toolCall.id,
    toolCall.subagentSessionId,
    subagents.values(),
    { allowRematch: !settled },
  );
  const subagent = useSubagent(linkedSessionId);

  const status = taskRowStatus(
    subagent?.status,
    toolCall.status,
    specialist?.status,
    specialist ? craftJob?.status : undefined,
  );

  const running = status === "running";
  const description =
    toolCall.description || toolCall.command || toolCall.title;
  const seedName = description;
  const activity =
    latestSubagentActivity(subagent) || specialist?.last_activity || "";

  useEffect(() => {
    if (!parentSessionId || !linkedSessionId) return;
    seedSubagentMeta(
      parentSessionId,
      linkedSessionId,
      toolCall.id,
      toolCall.subagentType ?? null,
      seedName,
      toolCall.command || "",
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

  // Keep the lane transcript warm so the swapped-in SubagentView is current.
  useLaneTranscript({
    open: linkedSessionId !== null,
    parentSessionId,
    childSessionId: linkedSessionId,
    parentToolCallId: toolCall.id,
    running: running,
  });

  function openTranscript() {
    if (!parentSessionId || !linkedSessionId) return;
    seedSubagentMeta(
      parentSessionId,
      linkedSessionId,
      toolCall.id,
      toolCall.subagentType ?? null,
      seedName,
      toolCall.command || "",
    );
    viewSubagent(parentSessionId, linkedSessionId);
  }

  return (
    <button
      type="button"
      onClick={openTranscript}
      disabled={linkedSessionId === null}
      data-testid="subagent-row"
      aria-label={t("openSubagent")}
      className={cn(
        "group/subagent flex min-w-0 w-full items-center gap-2 rounded-04 py-0.5 text-start transition-colors",
        linkedSessionId !== null && "hover:bg-background-tint-02",
      )}
    >
      <CATEGORY_AGENT_ICON className="h-4 w-4 shrink-0 stroke-text-03" />
      <span
        className={cn(
          "shrink-0 whitespace-nowrap font-medium",
          running ? "text-text-04" : "text-text-04",
        )}
      >
        {running ? <ShimmerText>{t("subagent")}</ShimmerText> : t("subagent")}
      </span>
      <span aria-hidden className="shrink-0 text-text-03">
        ·
      </span>
      <span className="min-w-0 flex-1 overflow-hidden">
        <Text as="p" font="main-ui-muted" color="text-04" maxLines={1}>
          {description}
        </Text>
        {activity ? (
          <Text as="p" font="secondary-mono" color="text-03" maxLines={1}>
            {activity}
          </Text>
        ) : null}
      </span>
      {running && (
        <SvgLoader className="h-4 w-4 shrink-0 animate-spin stroke-action-selection-05" />
      )}
      {status === "done" && (
        <SvgCheckCircle className="h-4 w-4 shrink-0 stroke-status-success-05" />
      )}
      {status === "failed" && (
        <SvgAlertTriangle className="h-4 w-4 shrink-0 stroke-status-error-05" />
      )}
    </button>
  );
}
