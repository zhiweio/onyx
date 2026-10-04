"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import hljs from "highlight.js/lib/core";
import json from "highlight.js/lib/languages/json";
import { CopyButton, Text } from "@opal/components";
import { SvgPlug } from "@opal/icons";
import { cn } from "@opal/utils";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/refresh-components/Collapsible";
import ShimmerText from "@/refresh-components/texts/ShimmerText";
import { SvgChevronDown } from "@opal/icons";

/**
 * ZCode-style MCP tool-call presentation, shared by the craft timeline and
 * the main chat timeline:
 *
 * - collapsed summary: `[plug] MCP <server> · <tool>` — "MCP" medium and
 *   shimmering while running, server name subtle, tool name subtlest;
 * - expanded: Running status / Result block (compact ≤160-char results stay
 *   single-line, otherwise a JSON-highlighted scrollable block with copy),
 *   then a "View call details" collapsible with Description + Parameters.
 *
 * Server-name recovery follows ZCode's legacy convention for tools whose
 * name was never enriched server-side: `mcp__<server>__<tool>` splits on
 * double underscores; `mcp_<server>_<tool>` on the first underscore.
 */

export interface McpPresentation {
  serverName?: string | null;
  toolName: string;
  description?: string | null;
}

let hljsRegistered = false;
function ensureHljsRegistered() {
  if (!hljsRegistered) {
    hljs.registerLanguage("json", json);
    hljsRegistered = true;
  }
}

function HighlightedJsonCode({ code }: { code: string }) {
  const html = useMemo(() => {
    ensureHljsRegistered();
    try {
      return hljs.highlight(code, { language: "json" }).value;
    } catch {
      return code
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
    }
  }, [code]);
  return <span dangerouslySetInnerHTML={{ __html: html }} className="hljs" />;
}

function isCompactResult(text: string): boolean {
  return (
    text.length <= 160 &&
    !text.includes("\n") &&
    !text.trimStart().startsWith("{")
  );
}

export function McpSummaryLine({
  serverName,
  toolName,
  running = false,
}: {
  serverName?: string | null;
  toolName: string;
  running?: boolean;
}) {
  const t = useTranslations("chat.mcpCall");
  return (
    <span className="flex min-w-0 items-center gap-2">
      <SvgPlug className="size-4 shrink-0 stroke-text-03" />
      <span
        className={cn(
          "shrink-0 whitespace-nowrap font-medium",
          running ? "text-text-04" : "text-text-04",
        )}
      >
        {running ? <ShimmerText>{t("label")}</ShimmerText> : t("label")}
      </span>
      {serverName ? (
        <span className="shrink-0 whitespace-nowrap text-text-04">
          {serverName}
        </span>
      ) : null}
      <span aria-hidden className="shrink-0 text-text-03">
        ·
      </span>
      <span className="min-w-0 truncate whitespace-nowrap text-text-03">
        {toolName}
      </span>
    </span>
  );
}

export function McpResultBlock({ result }: { result: string }) {
  const t = useTranslations("chat.mcpCall");
  const compact = isCompactResult(result);
  const prettyJson = useMemo(() => {
    if (compact) return null;
    try {
      return JSON.stringify(JSON.parse(result), null, 2);
    } catch {
      return result;
    }
  }, [result, compact]);

  if (compact) {
    return (
      <div className="rounded-08 border border-border-01 bg-background-neutral-01 px-3 py-2">
        <Text font="secondary-body" color="text-03">
          {result}
        </Text>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-08 border border-border-01">
      <div className="flex items-center justify-between border-b border-border-01 bg-background-tint-01 px-3 py-1.5">
        <Text font="secondary-action" color="text-04">
          {t("result")}
        </Text>
        <CopyButton
          getCopyText={() => result}
          prominence="tertiary"
          tooltip={t("copyResult")}
        />
      </div>
      <div className="max-h-72 overflow-y-auto bg-background-neutral-01 px-3 py-2 font-secondary-mono text-text-04">
        {prettyJson ? (
          <HighlightedJsonCode code={prettyJson} />
        ) : (
          <span className="whitespace-pre-wrap">{result}</span>
        )}
      </div>
    </div>
  );
}

export function McpCallDetails({
  description,
  parameters,
}: {
  description?: string | null;
  parameters?: Record<string, unknown> | null;
}) {
  const t = useTranslations("chat.mcpCall");
  const [open, setOpen] = useState(false);
  const prettyParams = useMemo(
    () => (parameters ? JSON.stringify(parameters, null, 2) : null),
    [parameters],
  );

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger asChild>
        <button
          type="button"
          className="flex items-center gap-1.5 rounded-04 py-0.5 text-start hover:bg-background-tint-02"
        >
          <SvgChevronDown
            className={cn(
              "size-3.5 shrink-0 stroke-text-03 transition-transform duration-150",
              !open && "-rotate-90",
            )}
          />
          <Text font="secondary-body" color="text-04">
            {t("viewCallDetails")}
          </Text>
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="flex min-w-0 flex-col gap-2 py-1">
          {description ? (
            <>
              <Text font="secondary-action" color="text-04">
                {t("description")}
              </Text>
              <Text font="secondary-body" color="text-03">
                {description}
              </Text>
            </>
          ) : null}
          {prettyParams ? (
            <>
              <Text font="secondary-action" color="text-04">
                {t("parameters")}
              </Text>
              <div className="max-h-60 overflow-auto rounded-08 border border-border-01 bg-background-neutral-01 px-3 py-2 font-secondary-mono text-text-04">
                <HighlightedJsonCode code={prettyParams} />
              </div>
            </>
          ) : null}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
