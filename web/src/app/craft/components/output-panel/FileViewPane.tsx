"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { cn } from "@opal/utils";
import { Button, Text } from "@opal/components";
import { SvgColumn, SvgCopy, SvgMenu } from "@opal/icons";
import {
  collapseUnchanged,
  SideBySideDiff,
  UnifiedDiff,
  computeDiff,
} from "@/app/craft/components/tool-cards/DiffBody";
import { FilePreviewContent } from "@/app/craft/components/output-panel/FilePreviewContent";
import { getFileIcon } from "@/lib/utils";
import type {
  FileEditPayload,
  FileViewMode,
} from "@/app/craft/types/displayTypes";

/**
 * Full-height pane for one file tab, ZCode-pattern: a file edited during the
 * task opens on the diff view and flips to the live source via the segmented
 * Diff | Source toggle; a never-edited file renders the source only.
 *
 * Diff mode reuses the tool-card diff engine with unchanged-line collapsing
 * and the unified / side-by-side layout toggle.
 */
export function FileViewPane({
  path,
  edit,
  viewMode,
  onViewModeChange,
  sessionId,
  refreshKey,
}: {
  path: string;
  /** Latest task edit for this path; null = source-only. */
  edit: FileEditPayload | null;
  viewMode: FileViewMode;
  onViewModeChange: (mode: FileViewMode) => void;
  sessionId: string;
  refreshKey: number;
}) {
  const t = useTranslations("craft.diffTab");
  const [layout, setLayout] = useState<"unified" | "side-by-side">("unified");
  const [copied, setCopied] = useState(false);

  const effectiveMode: FileViewMode = edit ? viewMode : "source";

  const dirs = path.split("/");
  const fileName = dirs.pop() ?? path;
  const FileIcon = getFileIcon(fileName);

  const lines = useMemo(() => {
    if (!edit) return [];
    return collapseUnchanged(
      computeDiff(edit.oldContent ?? "", edit.newContent ?? ""),
      (count) => t("unchangedLines", { count })
    );
  }, [edit, t]);

  const changedCount = useMemo(
    () =>
      lines.filter((l) => l.type === "added" || l.type === "removed").length,
    [lines]
  );
  const autoSideBySide = changedCount > 20;
  const effectiveLayout =
    autoSideBySide && layout === "unified" ? "side-by-side" : layout;

  return (
    <div className="flex h-full flex-col bg-background-neutral-00">
      {/* Header: breadcrumb + stat + view toggle + actions */}
      <div className="flex items-center gap-2 border-b border-border-01 px-3 py-2">
        <FileIcon size={14} className="shrink-0 stroke-text-03" />
        <div
          className="flex min-w-0 items-baseline gap-1 overflow-x-auto"
          data-testid="diff-tab-breadcrumb"
        >
          {dirs.map((dir, i) => (
            <span key={i} className="flex shrink-0 items-baseline gap-1">
              <Text font="secondary-body" color="text-03">
                {dir}
              </Text>
              <Text font="secondary-body" color="text-03">
                /
              </Text>
            </span>
          ))}
          <Text font="main-ui-body" color="text-05" nowrap>
            {fileName}
          </Text>
        </div>
        {edit && (
          <span className="ms-1 flex shrink-0 items-baseline gap-1 font-secondary-action">
            <span className="text-status-success-05">+{edit.added}</span>
            <span className="text-status-error-05">−{edit.removed}</span>
          </span>
        )}
        <div className="ms-auto flex shrink-0 items-center gap-1">
          {edit && (
            /* ZCode-style segmented Diff | Source toggle */
            <div
              className="flex items-center rounded-08 border border-border-01 p-0.5"
              data-testid="file-view-toggle"
              role="tablist"
              aria-label={t("viewToggleLabel")}
            >
              {(["diff", "source"] as const).map((mode) => (
                <button
                  key={mode}
                  role="tab"
                  aria-selected={effectiveMode === mode}
                  onClick={() => onViewModeChange(mode)}
                  className={cn(
                    "rounded-06 px-2 py-0.5 transition-colors",
                    effectiveMode === mode
                      ? "bg-background-tint-03 text-text-05"
                      : "text-text-03 hover:text-text-04"
                  )}
                >
                  <Text font="secondary-action" color="inherit">
                    {t(mode === "diff" ? "diffView" : "sourceView")}
                  </Text>
                </button>
              ))}
            </div>
          )}
          {edit && effectiveMode === "diff" && (
            <Button
              variant="default"
              prominence="tertiary"
              icon={effectiveLayout === "unified" ? SvgColumn : SvgMenu}
              onClick={() =>
                setLayout(
                  effectiveLayout === "unified" ? "side-by-side" : "unified"
                )
              }
              tooltip={t(
                effectiveLayout === "unified" ? "sideBySide" : "unified"
              )}
              aria-label={t(
                effectiveLayout === "unified" ? "sideBySide" : "unified"
              )}
            />
          )}
          <Button
            variant="default"
            prominence="tertiary"
            icon={SvgCopy}
            onClick={() => {
              void navigator.clipboard.writeText(path);
              setCopied(true);
              setTimeout(() => setCopied(false), 1200);
            }}
            tooltip={copied ? t("copied") : t("copyPath")}
            aria-label={t("copyPath")}
          />
        </div>
      </div>
      {/* Body */}
      {edit && effectiveMode === "diff" ? (
        <div className="min-h-0 flex-1 overflow-auto">
          <div className="p-3 text-ui-sm">
            {effectiveLayout === "unified" ? (
              <UnifiedDiff lines={lines} />
            ) : (
              <SideBySideDiff lines={lines} />
            )}
          </div>
        </div>
      ) : (
        <div className="min-h-0 flex-1 overflow-auto">
          <FilePreviewContent
            sessionId={sessionId}
            filePath={path}
            refreshKey={refreshKey}
          />
        </div>
      )}
    </div>
  );
}

export default FileViewPane;
