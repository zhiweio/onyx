"use client";

import type { ReactNode } from "react";
import { cn } from "@opal/utils";
import { SvgChevronRight } from "@opal/icons";
import { CollapsibleTrigger } from "@/refresh-components/Collapsible";

/**
 * Summary row for a tool block, ported from ZCode's ToolSummaryRow:
 * [icon] [kindLabel] [primaryText] [secondaryText] [diffCount] [status]
 * with a chevron that only appears on row hover (and stays visible + rotated
 * while open). The row is a div trigger (not a full-width button) so the
 * primary text can hold code chips and preview buttons.
 */

interface ToolSummaryRowProps {
  icon: ReactNode;
  kindLabel: ReactNode;
  kindLabelClassName?: string;
  /** Detail right after the kind label (e.g. MCP server name). */
  kindDetail?: ReactNode;
  /** Separator between the content group's leading node and primary text. */
  separator?: ReactNode;
  primaryText: ReactNode;
  secondaryText?: ReactNode;
  diffCount?: ReactNode;
  statusNode?: ReactNode;
  isExpanded: boolean;
  canToggle: boolean;
  toggleAriaLabel: string;
  title?: string;
}

export function ToolSummaryRow({
  icon,
  kindLabel,
  kindLabelClassName,
  kindDetail,
  separator,
  primaryText,
  secondaryText,
  diffCount,
  statusNode,
  isExpanded,
  canToggle,
  toggleAriaLabel,
  title,
}: ToolSummaryRowProps) {
  const hasContent = [primaryText, secondaryText, diffCount, statusNode].some(
    (node) => node != null && node !== false && node !== "",
  );

  const sharedContent = (
    <>
      <span className="shrink-0 stroke-text-03 [&_svg]:stroke-text-03">
        {icon}
      </span>
      {kindLabel != null && kindLabel !== "" ? (
        <span className={cn("shrink-0 whitespace-nowrap", kindLabelClassName)}>
          {kindLabel}
        </span>
      ) : null}
      {kindDetail ? (
        <span className="shrink-0 whitespace-nowrap">{kindDetail}</span>
      ) : null}
      {hasContent ? (
        <span className="flex min-w-0 max-w-full items-center gap-2">
          {separator}
          <span className="min-w-0 truncate">{primaryText}</span>
          {secondaryText ? (
            <span className="min-w-0 shrink truncate">{secondaryText}</span>
          ) : null}
          {diffCount ? <span className="shrink-0">{diffCount}</span> : null}
          {statusNode}
        </span>
      ) : null}
    </>
  );

  const rowClass =
    "group/tool-summary inline-flex max-w-full cursor-pointer items-center gap-2 self-start rounded-04 text-start transition-colors hover:bg-background-tint-02 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-border-03";

  return (
    <CollapsibleTrigger asChild>
      <div
        role="button"
        tabIndex={canToggle ? 0 : -1}
        aria-expanded={isExpanded}
        aria-label={toggleAriaLabel}
        title={title}
        onKeyDown={(event) => {
          if (!canToggle || (event.key !== "Enter" && event.key !== " ")) {
            return;
          }
          // The summary can embed code chips and preview triggers, so the
          // row stays a div; keyboard toggling is handled here.
          event.preventDefault();
          event.currentTarget.click();
        }}
        className={rowClass}
      >
        {sharedContent}
        <SvgChevronRight
          aria-hidden
          className={cn(
            "size-4 shrink-0 stroke-text-03 opacity-0 transition-transform transition-opacity duration-200 ease-out group-hover/tool-summary:opacity-100",
            isExpanded ? "rotate-90 opacity-100" : "rotate-0",
          )}
        />
      </div>
    </CollapsibleTrigger>
  );
}
