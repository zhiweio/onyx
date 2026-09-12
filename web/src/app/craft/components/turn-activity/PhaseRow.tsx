"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { Text } from "@opal/components";
import { cn } from "@opal/utils";
import { SvgBubbleText, SvgChevronDown } from "@opal/icons";
import { useTranslations } from "next-intl";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/refresh-components/Collapsible";
import MinimalMarkdown from "@/components/chat/MinimalMarkdown";
import ActivityToolLine from "@/app/craft/components/turn-activity/ActivityToolLine";
import {
  SvgLoader,
  getToolIcon,
} from "@/app/craft/components/tool-cards/helpers";
import {
  shortPhaseTarget,
  toolBatchIsLive,
  toolTarget,
  type ToolPhase,
} from "@/lib/craft/foldTurnStream";
import type { ToolCallState } from "@/app/craft/types/displayTypes";

interface ThinkingBlockProps {
  children?: ReactNode;
  dir?: string;
}

const thinkingP = ({ children, dir }: ThinkingBlockProps) => (
  <p dir={dir} className="text-sm leading-relaxed text-text-03 my-1">
    {children}
  </p>
);
const thinkingHeader = ({ children, dir }: ThinkingBlockProps) => (
  <p
    dir={dir}
    className="text-sm leading-relaxed text-text-03 font-semibold mt-4 mb-2"
  >
    {children}
  </p>
);

function normalizeThinking(text: string): string {
  let out = text.replace(/(?<!\n)\n(?!\n)/g, "\n\n");
  out = out.replace(/([.!?)\]])(\*\*[^*\n]+\*\*)/g, "$1\n\n$2");
  out = out.replace(/(\*\*[^*\n]+\*\*)(?=[A-Z([])/g, "$1\n\n");
  return out;
}

const THINKING_MARKDOWN_OVERRIDES = {
  p: thinkingP,
  h1: thinkingHeader,
  h2: thinkingHeader,
  h3: thinkingHeader,
  h4: thinkingHeader,
  h5: thinkingHeader,
  h6: thinkingHeader,
  li: ({ children, dir }: ThinkingBlockProps) => (
    <li dir={dir} className="text-sm leading-relaxed text-text-03 my-0.5">
      {children}
    </li>
  ),
  ul: ({ children, dir }: ThinkingBlockProps) => (
    <ul dir={dir} className="list-disc ms-4 my-1 text-sm">
      {children}
    </ul>
  ),
  ol: ({ children, dir }: ThinkingBlockProps) => (
    <ol dir={dir} className="list-decimal ms-4 my-1 text-sm">
      {children}
    </ol>
  ),
  blockquote: ({ children, dir }: ThinkingBlockProps) => (
    <blockquote
      dir={dir}
      className="text-sm text-text-02 border-s-2 border-border-02 ps-2 my-1"
    >
      {children}
    </blockquote>
  ),
};

function rowTriggerClass(expandable: boolean): string {
  return cn(
    "group flex w-full min-w-0 max-w-full items-center gap-2 overflow-hidden py-0.5 text-left",
    expandable && "rounded-sm hover:bg-background-tint-02"
  );
}

export function StepSummary({ text }: { text: string }) {
  if (!text) return null;
  return (
    <div className="min-w-0 max-w-full ps-6 pb-1.5">
      <Text
        as="p"
        font="main-ui-body"
        color="text-03"
        maxLines={2}
        wordWrap="wrap-anywhere"
      >
        {text}
      </Text>
    </div>
  );
}

function PhaseTitle({ children }: { children: string }) {
  return (
    <span className="min-w-0 flex-1 overflow-hidden">
      <Text as="p" font="main-ui-muted" color="text-03" maxLines={1}>
        {children}
      </Text>
    </span>
  );
}

function ThoughtActivityIcon({ isStreaming }: { isStreaming: boolean }) {
  if (!isStreaming) {
    return <SvgBubbleText className="size-4 shrink-0 stroke-text-03" />;
  }
  return (
    <span
      aria-hidden
      className="relative flex size-4 shrink-0 items-center justify-center"
    >
      <span className="absolute size-3 rounded-full bg-status-info-03 opacity-35 motion-safe:animate-ping motion-reduce:hidden" />
      <span className="size-1.5 rounded-full bg-status-info-05" />
    </span>
  );
}

export function ThoughtRow({
  content,
  isStreaming,
  durationMs,
  summary,
}: {
  content: string;
  isStreaming: boolean;
  durationMs?: number;
  summary?: string;
}) {
  const t = useTranslations("craft.turnActivity");
  const [isOpen, setIsOpen] = useState(false);
  if (!content) return null;

  const seconds =
    durationMs != null && durationMs >= 1000
      ? Math.round(durationMs / 1000)
      : null;
  const label = isStreaming
    ? t("thinking")
    : seconds != null
      ? t("thoughtFor", { seconds })
      : t("thought");

  return (
    <div className="min-w-0 max-w-full">
      <Collapsible open={isOpen} onOpenChange={setIsOpen}>
        <CollapsibleTrigger asChild>
          <button type="button" className={rowTriggerClass(true)}>
            <ThoughtActivityIcon isStreaming={isStreaming} />
            <PhaseTitle>{label}</PhaseTitle>
            <SvgChevronDown
              className={cn(
                "size-3.5 shrink-0 stroke-text-03 transition-transform duration-150",
                !isOpen && "-rotate-90"
              )}
            />
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="max-h-48 overflow-y-auto py-1 ps-6">
            <MinimalMarkdown
              content={normalizeThinking(content)}
              className="text-text-03 prose-sm"
              streaming={isStreaming}
              components={THINKING_MARKDOWN_OVERRIDES}
            />
          </div>
        </CollapsibleContent>
      </Collapsible>
      <StepSummary text={summary ?? ""} />
    </div>
  );
}

export function PlanningNextRow() {
  const t = useTranslations("craft.turnActivity");
  return (
    <div className={rowTriggerClass(false)}>
      <SvgLoader className="size-4 shrink-0 animate-spin stroke-text-03" />
      <Text font="main-ui-muted" color="text-03" nowrap>
        {t("planningNext")}
      </Text>
    </div>
  );
}

function phaseLabel({
  phase,
  tools,
  live,
  t,
}: {
  phase: ToolPhase;
  tools: ToolCallState[];
  live: boolean;
  t: ReturnType<typeof useTranslations>;
}): string {
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

export function ToolPhaseRow({
  phase,
  tools,
  autoCollapse,
  summary,
}: {
  phase: ToolPhase;
  tools: ToolCallState[];
  autoCollapse: boolean;
  summary?: string;
}) {
  const t = useTranslations("craft.turnActivity");
  const live = toolBatchIsLive(tools);
  const [isOpen, setIsOpen] = useState(live);
  const didAutoCollapse = useRef(false);

  useEffect(() => {
    if (autoCollapse && !didAutoCollapse.current) {
      didAutoCollapse.current = true;
      setIsOpen(false);
    }
  }, [autoCollapse]);

  const PhaseIcon = getToolIcon(
    phase === "explore"
      ? "read"
      : phase === "run"
        ? "execute"
        : phase === "task"
          ? "task"
          : "edit"
  );

  return (
    <div className="min-w-0 max-w-full">
      <Collapsible open={isOpen} onOpenChange={setIsOpen}>
        <CollapsibleTrigger asChild>
          <button type="button" className={rowTriggerClass(true)}>
            {live ? (
              <SvgLoader className="size-4 shrink-0 animate-spin stroke-status-info-05" />
            ) : (
              <PhaseIcon className="size-4 shrink-0 stroke-text-03" />
            )}
            <PhaseTitle>{phaseLabel({ phase, tools, live, t })}</PhaseTitle>
            <SvgChevronDown
              className={cn(
                "size-3.5 shrink-0 stroke-text-03 transition-transform duration-150",
                !isOpen && "-rotate-90"
              )}
            />
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="flex min-w-0 flex-col ps-6">
            {tools.map((toolCall) => (
              <ActivityToolLine key={toolCall.id} toolCall={toolCall} />
            ))}
          </div>
        </CollapsibleContent>
      </Collapsible>
      <StepSummary text={summary ?? ""} />
    </div>
  );
}
