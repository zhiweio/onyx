"use client";

import { useTranslations } from "next-intl";
import { Text } from "@opal/components";
import { SvgTerminalSmall, SvgFileText, SvgEdit, SvgSearch } from "@opal/icons";
import { CATEGORY_AGENT_ICON } from "@/lib/skills/categoryIcons";
import { ToolLayout } from "@/app/craft/components/tool-blocks/ToolLayout";
import ToolCallBlock from "@/app/craft/components/tool-blocks/ToolCallBlock";
import {
  shortPhaseTarget,
  toolBatchIsLive,
  toolTarget,
  type ToolPhase,
} from "@/lib/craft/foldTurnStream";
import type { ToolCallState } from "@/app/craft/types/displayTypes";

/**
 * ToolGroupRow — ZCode-style grouped tool row: consecutive same-phase calls
 * collapse into one summary ("Explored 12 tools", "Ran 3 commands") that
 * expands into individual ToolCallBlocks. Open state persists per group.
 */

function phaseIcon(phase: ToolPhase) {
  switch (phase) {
    case "explore":
      return SvgSearch;
    case "edit":
      return SvgEdit;
    case "run":
      return SvgTerminalSmall;
    case "task":
      return CATEGORY_AGENT_ICON;
    case "other":
    default:
      return SvgFileText;
  }
}

function groupSummary(
  phase: ToolPhase,
  tools: ToolCallState[],
  live: boolean,
  t: ReturnType<typeof useTranslations>
): string {
  const last = tools[tools.length - 1];
  const target = last ? shortPhaseTarget(toolTarget(last)) : "";
  if (phase === "explore") {
    if (live) {
      return target ? t("exploringTarget", { target }) : t("exploring");
    }
    return t("exploredN", { count: tools.length });
  }
  if (phase === "edit") {
    const writing = last?.isNewFile || last?.toolName === "write";
    if (live) {
      if (writing) {
        return target ? t("writingTarget", { target }) : t("writing");
      }
      return target ? t("editingTarget", { target }) : t("editing");
    }
    if (writing) {
      return target ? t("wroteTarget", { target }) : t("wrote");
    }
    return target ? t("editedTarget", { target }) : t("edited");
  }
  if (phase === "run") {
    if (live) {
      return tools.length > 1
        ? t("runningN", { count: tools.length })
        : t("running");
    }
    return tools.length > 1 ? t("ranN", { count: tools.length }) : t("ran");
  }
  if (phase === "task") {
    if (live) return t("task");
    if (
      tools.length > 0 &&
      tools.every(
        (tool) => tool.status === "cancelled" || tool.status === "failed"
      )
    ) {
      return t("taskCancelled");
    }
    return t("taskDone");
  }
  return live ? t("running") : t("ran");
}

interface ToolGroupRowProps {
  phase: ToolPhase;
  tools: ToolCallState[];
  /** Once the turn's answer arrives, groups collapse back to the summary. */
  autoCollapse: boolean;
  summary?: string;
  /** Panel navigation for clickable file chips (diff/file preview). */
  nav?: {
    openDiff?: (toolCall: ToolCallState) => void;
    openFile?: (path: string) => void;
  };
}

export function ToolGroupRow({
  phase,
  tools,
  autoCollapse,
  summary,
  nav,
}: ToolGroupRowProps) {
  const t = useTranslations("craft.turnActivity");
  const live = toolBatchIsLive(tools);
  const Icon = phaseIcon(phase);

  const failed = tools.some((tool) => tool.status === "failed");

  return (
    <ToolLayout
      toolId={`group:${tools[0]?.id ?? phase}`}
      icon={<Icon className="size-4 shrink-0" />}
      kindLabel={
        <Text
          font="secondary-action"
          color={live ? "text-03" : "text-04"}
          nowrap
        >
          {groupSummary(phase, tools, live, t)}
        </Text>
      }
      primaryText={
        <Text font="secondary-body" color="text-04">
          {summary ?? ""}
        </Text>
      }
      isRunning={live}
      // While live the group auto-expands once (streaming detail is the
      // signal the agent is working); it collapses when the run settles
      // (unless the user had opened it deliberately).
      autoOpen={live}
      autoCollapseOnComplete={autoCollapse}
      // Single-call groups skip the extra nesting level.
      content={
        tools.length === 1 ? (
          <ToolCallBlock toolCall={tools[0]!} nested nav={nav} />
        ) : (
          <div className="flex flex-col gap-1 border-s border-border-02 ps-2.5">
            {tools.map((tool) => (
              <ToolCallBlock key={tool.id} toolCall={tool} nested nav={nav} />
            ))}
          </div>
        )
      }
    />
  );
}
