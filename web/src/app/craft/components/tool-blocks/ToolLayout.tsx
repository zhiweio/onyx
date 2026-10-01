"use client";

import { memo, useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslations } from "next-intl";
import { Button, Text, Tooltip } from "@opal/components";
import { SvgCheck, SvgCopy, SvgLoader } from "@opal/icons";
import { cn } from "@opal/utils";
import {
  Collapsible,
  CollapsibleContent,
} from "@/refresh-components/Collapsible";
import {
  TOOL_CONTENT_COLLAPSE_UNMOUNT_DELAY_MS,
  getToolLayoutOpen,
  setToolLayoutOpen,
} from "@/app/craft/components/tool-blocks/toolLayoutStore";
import { ToolSummaryRow } from "@/app/craft/components/tool-blocks/ToolSummaryRow";

/**
 * ToolLayout — collapsible shell for one tool block, ported from ZCode:
 *
 * - open state persists in a module map keyed by `toolId`, surviving
 *   remounts (history reloads) so the user's collapse choices stick;
 * - `autoOpen` expands once when it first applies (edit/read results) without
 *   locking the block open;
 * - `autoCollapseOnComplete` collapses on the running→completed edge
 *   (subagent rows) unless the user had it open;
 * - content unmount is delayed 300ms so the Radix height animation has its
 *   measurement;
 * - failures render the status word with a dotted underline whose tooltip
 *   carries the error text plus a copy button.
 */

interface ToolLayoutProps {
  toolId: string;
  icon: ReactNode;
  kindLabel: ReactNode;
  primaryText: ReactNode;
  secondaryText?: ReactNode;
  diffCount?: ReactNode;
  statusLabel?: ReactNode;
  statusTooltip?: string;
  isRunning?: boolean;
  autoOpen?: boolean;
  autoCollapseOnComplete?: boolean;
  title?: string;
  content?: ReactNode;
  className?: string;
}

function ToolLayoutComponent({
  toolId,
  icon,
  kindLabel,
  primaryText,
  secondaryText,
  diffCount,
  statusLabel,
  statusTooltip,
  isRunning = false,
  autoOpen = false,
  autoCollapseOnComplete = false,
  title,
  content,
  className,
}: ToolLayoutProps) {
  const t = useTranslations("craft.toolBlocks");
  const [isOpen, setIsOpen] = useState(
    () => getToolLayoutOpen(toolId) ?? false,
  );
  const [shouldRenderContent, setShouldRenderContent] = useState(isOpen);
  const [isFailureCopied, setIsFailureCopied] = useState(false);
  const failureCopyResetRef = useRef<number | null>(null);
  const contentUnmountDelayRef = useRef<number | null>(null);
  const hasAutoOpenedRef = useRef(false);
  const previousIsRunningRef = useRef(isRunning);

  useEffect(() => {
    setIsOpen(getToolLayoutOpen(toolId) ?? false);
  }, [toolId]);

  useEffect(() => {
    // One-shot auto open: applies once, the user can still collapse after.
    if (!autoOpen || hasAutoOpenedRef.current) {
      return;
    }
    setToolLayoutOpen(toolId, true);
    setShouldRenderContent(true);
    setIsOpen(true);
    hasAutoOpenedRef.current = true;
  }, [autoOpen, toolId]);

  useEffect(() => {
    const wasRunning = previousIsRunningRef.current;
    previousIsRunningRef.current = isRunning;
    // Collapse only on the running→settled edge: a permanently expanded
    // subagent trail would dominate the transcript otherwise.
    if (autoCollapseOnComplete && !isRunning && wasRunning) {
      setToolLayoutOpen(toolId, false);
      setIsOpen(false);
    }
  }, [autoCollapseOnComplete, isRunning, toolId]);

  useEffect(() => {
    if (isOpen) {
      if (contentUnmountDelayRef.current !== null) {
        window.clearTimeout(contentUnmountDelayRef.current);
        contentUnmountDelayRef.current = null;
      }
      setShouldRenderContent(true);
      return;
    }
    if (!shouldRenderContent) {
      return;
    }
    contentUnmountDelayRef.current = window.setTimeout(() => {
      setShouldRenderContent(false);
      contentUnmountDelayRef.current = null;
    }, TOOL_CONTENT_COLLAPSE_UNMOUNT_DELAY_MS);
    return () => {
      if (contentUnmountDelayRef.current !== null) {
        window.clearTimeout(contentUnmountDelayRef.current);
        contentUnmountDelayRef.current = null;
      }
    };
  }, [isOpen, shouldRenderContent]);

  useEffect(() => {
    return () => {
      if (failureCopyResetRef.current !== null) {
        window.clearTimeout(failureCopyResetRef.current);
      }
      if (contentUnmountDelayRef.current !== null) {
        window.clearTimeout(contentUnmountDelayRef.current);
      }
    };
  }, []);

  const handleCopyFailure = () => {
    if (!statusTooltip?.trim()) {
      return;
    }
    void navigator.clipboard.writeText(statusTooltip).then(() => {
      setIsFailureCopied(true);
      if (failureCopyResetRef.current !== null) {
        window.clearTimeout(failureCopyResetRef.current);
      }
      failureCopyResetRef.current = window.setTimeout(() => {
        setIsFailureCopied(false);
        failureCopyResetRef.current = null;
      }, 1500);
    });
  };

  const statusNode =
    statusLabel != null ? (
      statusTooltip ? (
        <Tooltip
          tooltip={
            <div className="flex max-w-96 items-center gap-2">
              <span className="line-clamp-3 min-w-0 flex-1 whitespace-pre-wrap break-words">
                {statusTooltip}
              </span>
              {statusTooltip.trim() ? (
                <Button
                  type="button"
                  icon={isFailureCopied ? SvgCheck : SvgCopy}
                  prominence="tertiary"
                  onClick={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    handleCopyFailure();
                  }}
                  tooltip={
                    isFailureCopied
                      ? t("copyError.copied")
                      : t("copyError.label")
                  }
                  aria-label={
                    isFailureCopied
                      ? t("copyError.copied")
                      : t("copyError.label")
                  }
                />
              ) : null}
            </div>
          }
          side="top"
          align="start"
        >
          <span className="cursor-help whitespace-nowrap underline decoration-dotted underline-offset-2">
            {statusLabel}
          </span>
        </Tooltip>
      ) : (
        <span className="whitespace-nowrap">{statusLabel}</span>
      )
    ) : null;

  return (
    <Collapsible
      open={isOpen}
      onOpenChange={(open) => {
        setToolLayoutOpen(toolId, open);
        if (open) {
          setShouldRenderContent(true);
        }
        setIsOpen(open);
      }}
      className={cn("flex w-full flex-col", className)}
    >
      <ToolSummaryRow
        icon={icon}
        kindLabel={kindLabel}
        kindLabelClassName={
          isRunning
            ? "font-secondary-action text-text-03"
            : "font-secondary-action text-text-04"
        }
        primaryText={primaryText}
        secondaryText={secondaryText}
        diffCount={isOpen ? undefined : diffCount}
        statusNode={statusNode}
        isExpanded={isOpen}
        canToggle
        toggleAriaLabel={isOpen ? t("collapseDetails") : t("expandDetails")}
        title={title}
      />
      <CollapsibleContent>
        {/* Padding lives inside the animated node so the height animation
            clips it continuously instead of stopping at 8px. */}
        <div className="pt-2">{shouldRenderContent ? content : null}</div>
      </CollapsibleContent>
    </Collapsible>
  );
}

export const ToolLayout = memo(ToolLayoutComponent);
ToolLayout.displayName = "ToolLayout";
