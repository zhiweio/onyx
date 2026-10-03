"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { cn } from "@opal/utils";
import { Button, Text } from "@opal/components";
import { SvgCopy } from "@opal/icons";
import {
  buildInlineRows,
  collapseUnchanged,
  computeDiff,
  type InlineDiffRow,
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
 * Diff mode is the ZCode inline diff — ONE row per change with the old text
 * struck through in red and the new text in green on the same line (no
 * side-by-side columns).
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
  const [copied, setCopied] = useState(false);

  const effectiveMode: FileViewMode = edit ? viewMode : "source";

  const dirs = path.split("/");
  const fileName = dirs.pop() ?? path;
  const FileIcon = getFileIcon(fileName);

  const rows = useMemo(() => {
    if (!edit) return [];
    return buildInlineRows(
      collapseUnchanged(
        computeDiff(edit.oldContent ?? "", edit.newContent ?? ""),
        (count) => t("unchangedLines", { count })
      )
    );
  }, [edit, t]);

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
            <InlineZcodeDiff rows={rows} />
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

function rowBackground(row: InlineDiffRow): string {
  switch (row.kind) {
    case "added":
      return "bg-status-success-01";
    case "removed":
      return "bg-status-error-01";
    case "header":
      return "bg-background-tint-02 italic text-center";
    default:
      return "";
  }
}

/**
 * The ZCode inline diff body: same-row word diff. A modified line shows its
 * old text struck through in red followed by the new text in green, with the
 * pair's two line numbers in the gutter.
 */
function InlineZcodeDiff({ rows }: { rows: InlineDiffRow[] }) {
  return (
    <div className="flex flex-col">
      {rows.map((row, idx) => {
        if (row.kind === "modified") {
          return (
            <div
              key={idx}
              className="flex items-baseline gap-2 px-2 py-0.5"
              data-testid="inline-diff-modified-row"
            >
              <span className="flex shrink-0 select-none items-baseline gap-1 font-secondary-mono text-text-03">
                <span className="text-status-error-05 line-through">
                  {row.oldLineNum}
                </span>
                <span className="text-status-success-05">{row.newLineNum}</span>
              </span>
              <span
                className="min-w-0 flex-1 font-secondary-mono whitespace-pre-wrap wrap-break-word text-text-04"
                data-testid="inline-diff-word-diff"
              >
                {row.segments!.map((seg, si) =>
                  seg.t === "same" ? (
                    <span key={si}>{seg.s}</span>
                  ) : seg.t === "del" ? (
                    <span
                      key={si}
                      className="bg-status-error-01 text-status-error-05 line-through decoration-status-error-05/60"
                    >
                      {seg.s}
                    </span>
                  ) : (
                    <span
                      key={si}
                      className="bg-status-success-01 text-status-success-05"
                    >
                      {seg.s}
                    </span>
                  )
                )}
              </span>
            </div>
          );
        }
        const prefix =
          row.kind === "added" ? "+" : row.kind === "removed" ? "−" : " ";
        const lineNum = row.newLineNum ?? row.oldLineNum;
        return (
          <div
            key={idx}
            className={cn(
              "flex items-baseline gap-2 px-2 py-0.5",
              rowBackground(row)
            )}
          >
            {row.kind !== "header" && (
              <>
                <span className="w-8 shrink-0 select-none text-end font-secondary-mono text-text-03">
                  {lineNum ?? ""}
                </span>
                <span
                  className={cn(
                    "shrink-0 select-none font-secondary-mono",
                    row.kind === "added" && "text-status-success-05",
                    row.kind === "removed" && "text-status-error-05"
                  )}
                >
                  {prefix}
                </span>
              </>
            )}
            <span
              className={cn(
                "min-w-0 flex-1 font-secondary-mono whitespace-pre-wrap wrap-break-word",
                row.kind === "unchanged" && "text-text-03",
                (row.kind === "added" || row.kind === "removed") && "text-text-04"
              )}
            >
              {row.content ?? ""}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export default FileViewPane;
