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
} from "@/app/craft/components/tool-cards/DiffBody";
import { getFileIcon } from "@/lib/utils";
import type { PanelTab } from "@/app/craft/types/displayTypes";

/**
 * Full-height diff view for a transient `diff` panel tab (ZCode PreviewPane
 * pattern): breadcrumb header + stat + view toggle + actions, body reuses the
 * tool-card diff engine with unchanged-line collapsing.
 */
export function DiffTabBody({
  tab,
  onViewCurrentFile,
}: {
  tab: Extract<PanelTab, { kind: "diff" }>;
  onViewCurrentFile: (path: string, fileName: string) => void;
}) {
  const t = useTranslations("craft.diffTab");
  const [view, setView] = useState<"unified" | "side-by-side">("unified");
  const [copied, setCopied] = useState(false);

  const dirs = tab.path.split("/");
  const fileName = dirs.pop() ?? tab.path;
  const FileIcon = getFileIcon(fileName);

  const lines = useMemo(
    () =>
      collapseUnchanged(computeLines(tab), (count) =>
        t("unchangedLines", { count })
      ),
    [tab, t]
  );

  const changedCount = useMemo(
    () =>
      lines.filter((l) => l.type === "added" || l.type === "removed").length,
    [lines]
  );
  const autoSideBySide = changedCount > 20;
  const effectiveView =
    autoSideBySide && view === "unified" ? "side-by-side" : view;

  return (
    <div className="flex h-full flex-col bg-background-neutral-00">
      {/* Header: breadcrumb + stat + actions */}
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
        <span className="ms-1 flex shrink-0 items-baseline gap-1 font-secondary-action">
          <span className="text-status-success-05">+{tab.added}</span>
          <span className="text-status-error-05">−{tab.removed}</span>
        </span>
        <div className="ms-auto flex shrink-0 items-center gap-1">
          <Button
            variant="default"
            prominence="tertiary"
            icon={effectiveView === "unified" ? SvgColumn : SvgMenu}
            onClick={() =>
              setView(effectiveView === "unified" ? "side-by-side" : "unified")
            }
            tooltip={t(effectiveView === "unified" ? "sideBySide" : "unified")}
            aria-label={t(
              effectiveView === "unified" ? "sideBySide" : "unified"
            )}
          />
          <Button
            variant="default"
            prominence="tertiary"
            icon={SvgCopy}
            onClick={() => {
              void navigator.clipboard.writeText(tab.path);
              setCopied(true);
              setTimeout(() => setCopied(false), 1200);
            }}
            tooltip={copied ? t("copied") : t("copyPath")}
            aria-label={t("copyPath")}
          />
          <Button
            variant="default"
            prominence="tertiary"
            onClick={() => onViewCurrentFile(tab.path, tab.fileName)}
            tooltip={t("viewCurrentFile")}
            aria-label={t("viewCurrentFile")}
          >
            {t("viewCurrentFile")}
          </Button>
        </div>
      </div>
      {/* Body */}
      <div className="min-h-0 flex-1 overflow-auto">
        <div className="p-3 text-ui-sm">
          {effectiveView === "unified" ? (
            <UnifiedDiff lines={lines} />
          ) : (
            <SideBySideDiff lines={lines} />
          )}
        </div>
      </div>
    </div>
  );
}

// Local import split so the engine import stays tree-shakeable.
import { computeDiff } from "@/app/craft/components/tool-cards/DiffBody";

function computeLines(tab: Extract<PanelTab, { kind: "diff" }>) {
  return computeDiff(tab.oldContent ?? "", tab.newContent ?? "");
}

export default DiffTabBody;
