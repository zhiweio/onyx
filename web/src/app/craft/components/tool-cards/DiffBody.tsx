"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { cn } from "@opal/utils";
import { Text, Button } from "@opal/components";
import { SvgColumn, SvgMenu } from "@opal/icons";
import ToolCardSurface from "@/app/craft/components/tool-cards/ToolCardSurface";
import type { ToolCardBodyProps } from "@/app/craft/components/tool-cards/interfaces";

type DiffLineType = "added" | "removed" | "unchanged" | "header";

interface DiffLine {
  type: DiffLineType;
  content: string;
  oldLineNum?: number;
  newLineNum?: number;
}

const SIDE_BY_SIDE_AUTO_THRESHOLD = 20;
const BLANK = " ";

export function computeDiff(oldText: string, newText: string): DiffLine[] {
  const oldLines = oldText.split("\n");
  const newLines = newText.split("\n");
  const result: DiffLine[] = [];

  // Last-occurrence index per unique line, so the "exists later" check
  // below is O(1) instead of O(n) via slice().includes() — the prior
  // form made computeDiff O(n²) on large diffs.
  const lastOldIdxOf = new Map<string, number>();
  oldLines.forEach((l, i) => lastOldIdxOf.set(l, i));
  const lastNewIdxOf = new Map<string, number>();
  newLines.forEach((l, i) => lastNewIdxOf.set(l, i));

  let oldIdx = 0;
  let newIdx = 0;
  let oldLineNum = 1;
  let newLineNum = 1;

  while (oldIdx < oldLines.length || newIdx < newLines.length) {
    const oldLine: string | undefined = oldLines[oldIdx];
    const newLine: string | undefined = newLines[newIdx];

    if (oldIdx >= oldLines.length || oldLine === undefined) {
      result.push({
        type: "added",
        content: newLine ?? "",
        newLineNum: newLineNum++,
      });
      newIdx++;
    } else if (newIdx >= newLines.length || newLine === undefined) {
      result.push({
        type: "removed",
        content: oldLine,
        oldLineNum: oldLineNum++,
      });
      oldIdx++;
    } else if (oldLine === newLine) {
      result.push({
        type: "unchanged",
        content: oldLine,
        oldLineNum: oldLineNum++,
        newLineNum: newLineNum++,
      });
      oldIdx++;
      newIdx++;
    } else {
      const oldExistsLaterInNew = (lastNewIdxOf.get(oldLine) ?? -1) > newIdx;
      const newExistsLaterInOld = (lastOldIdxOf.get(newLine) ?? -1) > oldIdx;

      if (!oldExistsLaterInNew && newExistsLaterInOld) {
        result.push({
          type: "removed",
          content: oldLine,
          oldLineNum: oldLineNum++,
        });
        oldIdx++;
      } else if (oldExistsLaterInNew && !newExistsLaterInOld) {
        result.push({
          type: "added",
          content: newLine,
          newLineNum: newLineNum++,
        });
        newIdx++;
      } else {
        result.push({
          type: "removed",
          content: oldLine,
          oldLineNum: oldLineNum++,
        });
        result.push({
          type: "added",
          content: newLine,
          newLineNum: newLineNum++,
        });
        oldIdx++;
        newIdx++;
      }
    }
  }
  return result;
}

export function collapseUnchanged(
  lines: DiffLine[],
  formatUnchanged: (count: number) => string,
  contextLines: number = 3
): DiffLine[] {
  const result: DiffLine[] = [];
  const changeIndices: number[] = [];

  lines.forEach((line, idx) => {
    if (line.type === "added" || line.type === "removed") {
      changeIndices.push(idx);
    }
  });

  if (changeIndices.length === 0) {
    if (lines.length > 10) {
      return [{ type: "header", content: formatUnchanged(lines.length) }];
    }
    return lines;
  }

  const showIndices = new Set<number>();
  changeIndices.forEach((idx) => {
    for (
      let i = Math.max(0, idx - contextLines);
      i <= Math.min(lines.length - 1, idx + contextLines);
      i++
    ) {
      showIndices.add(i);
    }
  });

  const pushSkippedHeader = (count: number) => {
    if (count <= 0) return;
    result.push({
      type: "header",
      content: formatUnchanged(count),
    });
  };

  let lastShownIdx = -1;
  lines.forEach((line, idx) => {
    if (showIndices.has(idx)) {
      // Leading skipped block when the first shown index is past line 0.
      if (lastShownIdx === -1 && idx > 0) {
        pushSkippedHeader(idx);
      } else if (lastShownIdx !== -1 && idx - lastShownIdx > 1) {
        pushSkippedHeader(idx - lastShownIdx - 1);
      }
      result.push(line);
      lastShownIdx = idx;
    }
  });
  // Trailing skipped block when the last shown index is before the end.
  if (lastShownIdx !== -1 && lastShownIdx < lines.length - 1) {
    pushSkippedHeader(lines.length - 1 - lastShownIdx);
  }
  return result;
}

type DiffTextColor = "text-02" | "text-03" | "text-04";

function lineRowClass(type: DiffLineType): string {
  switch (type) {
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

function linePrefix(type: DiffLineType): { glyph: string; color: string } {
  if (type === "added") return { glyph: "+", color: "text-status-success-05" };
  if (type === "removed") return { glyph: "-", color: "text-status-error-05" };
  return { glyph: BLANK, color: "text-text-03" };
}

function lineTextColor(type: DiffLineType): DiffTextColor {
  if (type === "header") return "text-02";
  if (type === "unchanged") return "text-03";
  return "text-04";
}

export function UnifiedDiff({ lines }: { lines: DiffLine[] }) {
  return (
    <div className="overflow-auto max-h-60">
      {lines.map((line, idx) => {
        const prefix = linePrefix(line.type);
        return (
          <div
            key={idx}
            className={cn(
              "px-2 py-0.5 flex gap-2 items-baseline",
              lineRowClass(line.type)
            )}
          >
            {line.type !== "header" && (
              <span className={cn("select-none shrink-0", prefix.color)}>
                <Text font="secondary-mono" color="inherit">
                  {prefix.glyph}
                </Text>
              </span>
            )}
            <span className="min-w-0 flex-1 whitespace-pre-wrap wrap-break-word block">
              <Text font="secondary-mono" color={lineTextColor(line.type)}>
                {line.content || (line.type === "header" ? "" : BLANK)}
              </Text>
            </span>
          </div>
        );
      })}
    </div>
  );
}

export function SideBySideDiff({ lines }: { lines: DiffLine[] }) {
  return (
    <div className="overflow-auto max-h-60 grid grid-cols-2 divide-x divide-border-01">
      <div>
        {lines.map((line, idx) => {
          const isHeader = line.type === "header";
          const showRemoved = line.type === "removed";
          const content = line.type === "added" ? BLANK : line.content || BLANK;
          return (
            <div
              key={`l-${idx}`}
              className={cn(
                "px-2 py-0.5 whitespace-pre-wrap wrap-break-word",
                showRemoved && "bg-status-error-01",
                isHeader && "bg-background-tint-02 italic text-center"
              )}
            >
              <Text font="secondary-mono" color={lineTextColor(line.type)}>
                {content}
              </Text>
            </div>
          );
        })}
      </div>
      <div>
        {lines.map((line, idx) => {
          const isHeader = line.type === "header";
          const showAdded = line.type === "added";
          const content =
            line.type === "removed" ? BLANK : line.content || BLANK;
          return (
            <div
              key={`r-${idx}`}
              className={cn(
                "px-2 py-0.5 whitespace-pre-wrap wrap-break-word",
                showAdded && "bg-status-success-01",
                isHeader && "bg-background-tint-02 italic text-center"
              )}
            >
              <Text font="secondary-mono" color={lineTextColor(line.type)}>
                {content}
              </Text>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/**
 * DiffBody - Diff renderer for the edit/write tool.
 *
 * Replaces the old DiffView with design-token colors (no hardcoded hex) and
 * adds a unified <-> side-by-side toggle. Auto-picks side-by-side for hunks
 * larger than SIDE_BY_SIDE_AUTO_THRESHOLD.
 */
export default function DiffBody({ toolCall }: ToolCardBodyProps) {
  const t = useTranslations("craft.toolCards.diff");
  const oldContent = toolCall.oldContent ?? "";
  const newContent = toolCall.newContent ?? "";

  const diffLines = useMemo(() => {
    const rawDiff = computeDiff(oldContent, newContent);
    return collapseUnchanged(rawDiff, (count) =>
      t("unchangedLines.label", { count })
    );
  }, [oldContent, newContent, t]);

  const stats = useMemo(() => {
    const added = diffLines.filter((l) => l.type === "added").length;
    const removed = diffLines.filter((l) => l.type === "removed").length;
    return { added, removed };
  }, [diffLines]);

  const autoSideBySide =
    stats.added + stats.removed > SIDE_BY_SIDE_AUTO_THRESHOLD;
  const [mode, setMode] = useState<"unified" | "side-by-side">(
    autoSideBySide ? "side-by-side" : "unified"
  );

  if (!newContent && !oldContent) {
    return null;
  }

  return (
    <ToolCardSurface scroll={false}>
      <div
        className={cn(
          "px-2 py-0.5 border-b-[0.5px] border-border-01",
          "bg-background-tint-01 flex items-center gap-2"
        )}
      >
        {toolCall.description && (
          <span className="truncate flex-1 min-w-0">
            <Text font="secondary-mono" color="text-03" nowrap>
              {toolCall.description}
            </Text>
          </span>
        )}
        <div className="flex items-center gap-2 shrink-0">
          {stats.added > 0 && (
            <span className="text-status-success-05">
              <Text font="figure-small-value" color="inherit">
                {`+${stats.added}`}
              </Text>
            </span>
          )}
          {stats.removed > 0 && (
            <span className="text-status-error-05">
              <Text font="figure-small-value" color="inherit">
                {`-${stats.removed}`}
              </Text>
            </span>
          )}
          <Button
            variant="default"
            prominence="tertiary"
            size="2xs"
            icon={mode === "unified" ? SvgColumn : SvgMenu}
            onClick={() =>
              setMode(mode === "unified" ? "side-by-side" : "unified")
            }
            tooltip={
              mode === "unified"
                ? t("viewToggle.sideBySideTooltip")
                : t("viewToggle.unifiedTooltip")
            }
          />
        </div>
      </div>

      {mode === "unified" ? (
        <UnifiedDiff lines={diffLines} />
      ) : (
        <SideBySideDiff lines={diffLines} />
      )}
    </ToolCardSurface>
  );
}

// ── ZCode-style inline diff (same-row word diff) ─────────────────────────

export type WordSegmentType = "same" | "del" | "add";

export interface WordSegment {
  t: WordSegmentType;
  s: string;
}

export interface InlineDiffRow {
  kind: "unchanged" | "removed" | "added" | "modified" | "header";
  /** Pure rows: the whole line. Modified rows: unused (see segments). */
  content?: string;
  /** Modified rows only: word-level segments across old and new text. */
  segments?: WordSegment[];
  oldLineNum?: number;
  newLineNum?: number;
}

/** Split a line into word / whitespace / punctuation tokens, keeping every char. */
function tokenize(line: string): string[] {
  return line.match(/\s+|[A-Za-z0-9_]+|./g) ?? [];
}

/**
 * Word-level LCS between a removed line and its replacement — the segments
 * render on ONE row: deletions struck through in red, insertions in green
 * (ZCode inline-diff pattern).
 */
export function wordSegments(oldLine: string, newLine: string): WordSegment[] {
  const a = tokenize(oldLine);
  const b = tokenize(newLine);
  // LCS table; diff lines are short so O(n·m) is fine.
  const dp: number[][] = Array.from({ length: a.length + 1 }, () =>
    new Array<number>(b.length + 1).fill(0)
  );
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      const av = a[i]!;
      const bv = b[j]!;
      dp[i]![j] =
        av === bv
          ? dp[i + 1]![j + 1]! + 1
          : Math.max(dp[i + 1]![j]!, dp[i]![j + 1]!);
    }
  }
  const segments: WordSegment[] = [];
  const push = (t: WordSegmentType, s: string) => {
    const last = segments[segments.length - 1];
    if (last && last.t === t) last.s += s;
    else segments.push({ t, s });
  };
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    const av = a[i]!;
    const bv = b[j]!;
    if (av === bv) {
      push("same", av);
      i++;
      j++;
    } else if (dp[i + 1]![j]! >= dp[i]![j + 1]!) {
      push("del", av);
      i++;
    } else {
      push("add", bv);
      j++;
    }
  }
  while (i < a.length) push("del", a[i++]!);
  while (j < b.length) push("add", b[j++]!);
  return segments;
}

/**
 * Collapse a unified diff into ZCode-style rows: a removed line immediately
 * followed by its replacement merges into ONE modified row whose segments
 * carry the old text (del) and new text (add) inline.
 */
export function buildInlineRows(lines: DiffLine[]): InlineDiffRow[] {
  const rows: InlineDiffRow[] = [];
  let idx = 0;
  while (idx < lines.length) {
    const line = lines[idx]!;
    if (line.type === "removed") {
      const next = lines[idx + 1];
      if (next && next.type === "added") {
        rows.push({
          kind: "modified",
          segments: wordSegments(line.content, next.content),
          oldLineNum: line.oldLineNum,
          newLineNum: next.newLineNum,
        });
        idx += 2;
        continue;
      }
      rows.push({
        kind: "removed",
        content: line.content,
        oldLineNum: line.oldLineNum,
      });
      idx++;
      continue;
    }
    if (line.type === "added") {
      rows.push({
        kind: "added",
        content: line.content,
        newLineNum: line.newLineNum,
      });
      idx++;
      continue;
    }
    if (line.type === "header") {
      rows.push({ kind: "header", content: line.content });
    } else {
      rows.push({
        kind: "unchanged",
        content: line.content,
        oldLineNum: line.oldLineNum,
        newLineNum: line.newLineNum,
      });
    }
    idx++;
  }
  return rows;
}
