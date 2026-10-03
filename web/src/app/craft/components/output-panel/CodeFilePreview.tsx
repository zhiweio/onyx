"use client";

import { useMemo } from "react";
import { getLanguageFromPath } from "@/app/craft/utils/codeLanguage";
import { useCodeHighlighter } from "@/app/craft/hooks/useCodeHighlighter";
import { MONO_STYLE } from "@/app/craft/components/tool-cards/ToolCardSurface";
import type { FileRendererProps } from "@/app/craft/components/output-panel/MarkdownFilePreview";

/** Beyond this, per-line highlighting costs more than it is worth. */
const MAX_HIGHLIGHT_LINES = 8000;

/**
 * CodeFilePreview — ZCode-style source view for code files: line-number
 * gutter, editor-style no-wrap horizontal scrolling, and per-line
 * highlight.js coloring (same lazy highlighter the tool cards use).
 * Files with no recognized language never route here (registry matcher).
 */
export default function CodeFilePreview({
  content,
  filePath,
}: FileRendererProps) {
  const language = useMemo(() => getLanguageFromPath(filePath), [filePath]);
  const lines = useMemo(() => content.split("\n"), [content]);
  const highlight = useCodeHighlighter(!!language && lines.length <= MAX_HIGHLIGHT_LINES);

  // One pass once the lazy highlighter resolves; null until then renders
  // plain lines and the same rows re-render colored a tick later.
  const htmlLines = useMemo(() => {
    if (!highlight) return null;
    return lines.map((line) => highlight(line, language));
  }, [highlight, lines, language]);

  return (
    <div className="h-full min-h-0 overflow-auto hljs">
      <table className="w-full border-separate border-spacing-0">
        <tbody>
          {lines.map((line, idx) => {
            const html = htmlLines ? htmlLines[idx] : null;
            return (
              <tr key={idx} className="align-baseline">
                <td
                  className="sticky left-0 select-none border-e-[0.5px] border-border-01 bg-background-code-01 px-2 py-0 text-end align-baseline"
                  style={{ ...MONO_STYLE, minWidth: "3.5em", color: "var(--text-02)" }}
                >
                  {idx + 1}
                </td>
                <td
                  className="whitespace-pre px-3 py-0 align-baseline"
                  style={MONO_STYLE}
                >
                  {html !== null ? (
                    <span dangerouslySetInnerHTML={{ __html: html || " " }} />
                  ) : (
                    line || " "
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
