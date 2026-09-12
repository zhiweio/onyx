"use client";

import { useState, type ReactNode } from "react";
import { Text } from "@opal/components";
import { cn } from "@opal/utils";
import { SvgChevronDown, SvgSparkle } from "@opal/icons";
import { useTranslations } from "next-intl";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/refresh-components/Collapsible";
import BashBody from "@/app/craft/components/tool-cards/BashBody";
import DiffBody from "@/app/craft/components/tool-cards/DiffBody";
import ReadBody from "@/app/craft/components/tool-cards/ReadBody";
import SearchBody from "@/app/craft/components/tool-cards/SearchBody";
import WebSearchBody from "@/app/craft/components/tool-cards/WebSearchBody";
import WebFetchBody from "@/app/craft/components/tool-cards/WebFetchBody";
import GenericBody from "@/app/craft/components/tool-cards/GenericBody";
import {
  getStatusDisplay,
  getToolIcon,
  isSkillInvocation,
  SvgLoader,
} from "@/app/craft/components/tool-cards/helpers";
import type { ToolCallState } from "@/app/craft/types/displayTypes";

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
      return !!toolCall.rawOutput;
    case "search":
      return !!toolCall.rawOutput;
    case "other":
    default:
      return !!toolCall.rawOutput;
  }
}

function lineVerb(toolCall: ToolCallState, t: (key: string) => string): string {
  const live =
    toolCall.status === "pending" || toolCall.status === "in_progress";
  if (toolCall.toolName === "skill") {
    return live ? t("lineUsing") : t("lineUsed");
  }
  if (toolCall.kind === "read") {
    return live ? t("lineReading") : t("lineRead");
  }
  if (toolCall.kind === "search" || toolCall.toolName === "websearch") {
    return live ? t("lineSearching") : t("lineSearched");
  }
  if (toolCall.toolName === "webfetch") {
    return live ? t("lineFetching") : t("lineFetched");
  }
  if (toolCall.kind === "edit") {
    if (toolCall.isNewFile || toolCall.toolName === "write") {
      return live ? t("lineWriting") : t("lineWrote");
    }
    return live ? t("lineEditing") : t("lineEdited");
  }
  if (toolCall.kind === "execute") {
    return live ? t("lineRunning") : t("lineRan");
  }
  return toolCall.title;
}

function renderStatusIcon(toolCall: ToolCallState) {
  const statusDisplay = getStatusDisplay(toolCall.status);
  const baseClass = "size-4 shrink-0";
  if (statusDisplay.showSpinner) {
    return (
      <SvgLoader
        className={cn(baseClass, "stroke-status-info-05 animate-spin")}
      />
    );
  }
  if (isSkillInvocation(toolCall) && toolCall.status === "completed") {
    return (
      <SvgSparkle
        className={cn(baseClass, "stroke-status-info-05 fill-status-info-05")}
      />
    );
  }
  const StatusIcon = statusDisplay.icon;
  if (StatusIcon) {
    return <StatusIcon className={cn(baseClass, statusDisplay.iconClass)} />;
  }
  const ToolIcon = getToolIcon(toolCall.kind);
  return <ToolIcon className={cn(baseClass, "stroke-text-03")} />;
}

function primaryLine(
  toolCall: ToolCallState,
  t: (key: string) => string
): ReactNode {
  const target = toolCall.description || toolCall.command;
  return (
    <span className="flex min-w-0 max-w-full items-center gap-1.5">
      <Text font="main-ui-muted" color="text-03" nowrap>
        {lineVerb(toolCall, t)}
      </Text>
      {target ? (
        <span className="min-w-0 flex-1 overflow-hidden">
          <Text as="p" font="secondary-mono" color="text-03" maxLines={1}>
            {target}
          </Text>
        </span>
      ) : null}
    </span>
  );
}

export default function ToolActivityLine({
  toolCall,
}: {
  toolCall: ToolCallState;
}) {
  const t = useTranslations("craft.turnActivity");
  const failed = toolCall.status === "failed";
  const expandable = hasBodyContent(toolCall) || failed;
  const [isOpen, setIsOpen] = useState(failed);

  const header = (
    <div className="flex min-w-0 w-full items-center gap-2">
      {renderStatusIcon(toolCall)}
      <span className="min-w-0 truncate">{primaryLine(toolCall, t)}</span>
      <SvgChevronDown
        aria-hidden={!expandable}
        className={cn(
          "ms-auto size-3.5 shrink-0 stroke-text-03 transition-transform duration-150",
          !isOpen && "-rotate-90",
          !expandable && "invisible"
        )}
      />
    </div>
  );

  if (!expandable) {
    return (
      <div className="w-full min-w-0 max-w-full overflow-hidden py-0.5">
        {header}
      </div>
    );
  }

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <CollapsibleTrigger asChild>
        <button
          type="button"
          className="w-full min-w-0 max-w-full overflow-hidden rounded-sm py-0.5 text-start hover:bg-background-tint-02"
        >
          {header}
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent>{renderBody(toolCall)}</CollapsibleContent>
    </Collapsible>
  );
}
