"use client";

import { ReactNode, useState } from "react";
import { useTranslations } from "next-intl";
import { Button, Card, InputTypeIn, Switch } from "@opal/components";
import {
  Card as CardLayout,
  ContentAction,
  InputHorizontal,
} from "@opal/layouts";
import { Section } from "@/layouts/general-layouts";
import { SvgExpand, SvgFold } from "@opal/icons";
import { cn } from "@opal/utils";
import type { IconFunctionComponent } from "@opal/types";
import useFilter from "@/hooks/useFilter";
import useServerTools from "@/hooks/useServerTools";
import { MCPServer } from "@/lib/tools/types";

/** One inline tool row. */
export interface McpToolsCardTool {
  id: string;
  name: string;
  description: string;
}

/**
 * The MCP server card shared by every MCP list surface: a header (logo,
 * name, description, caller-provided controls) that expands into an inline
 * tool list with its own search — the chat-preferences "操作与工具" design.
 *
 * Tools come either from the caller (`tools`) or lazily from the per-server
 * snapshots endpoint when the card expands (`server` + `surface`).
 */
export interface McpToolsCardProps {
  name: string;
  description?: string | null;
  logo: IconFunctionComponent;
  /** Header right side: availability switch, status tags, actions. */
  headerRight?: ReactNode;
  /** Provide tools directly; omit for lazy fetch on expand. */
  tools?: McpToolsCardTool[] | null;
  /** Required for the lazy mode. */
  server?: MCPServer;
  surface?: "admin" | "personal" | "gallery";
  /** Right side of each tool row (a switch, a tag, nothing). */
  renderToolRight?: (tool: McpToolsCardTool) => ReactNode;
  /** Row under the tool list: counts, bulk actions. */
  footer?: ReactNode;
  isLoading?: boolean;
  defaultExpanded?: boolean;
  /** Master switch semantics: disable every tool row until it is on. */
  toolsLocked?: boolean;
  className?: string;
  "data-testid"?: string;
}

// SAFETY: placeholder for the non-lazy mode — the hook never fetches with it
// (isExpanded stays false), so only `id` is ever read.
const NO_LAZY_SERVER: MCPServer = { id: -1 } as MCPServer;

export default function McpToolsCard({
  name,
  description,
  logo,
  headerRight,
  tools: providedTools,
  server,
  surface = "admin",
  renderToolRight,
  footer,
  isLoading = false,
  defaultExpanded = false,
  toolsLocked = false,
  className,
  ...rest
}: McpToolsCardProps) {
  const t = useTranslations("actions.toolsCard");
  const [isFolded, setIsFolded] = useState(!defaultExpanded);

  const lazy = providedTools === undefined && server !== undefined;
  const { tools: lazyTools, isLoading: lazyLoading } = useServerTools(
    server ?? NO_LAZY_SERVER,
    !isFolded && lazy,
    surface
  );
  const tools = lazy ? lazyTools : (providedTools ?? []);

  const {
    query,
    setQuery,
    filtered: filteredTools,
  } = useFilter(tools, (tool) => `${tool.name} ${tool.description}`);

  const loading = lazy ? lazyLoading : isLoading;
  const expanded = !isFolded;
  const hasContent = tools.length > 0 && filteredTools.length > 0;
  // Lazy mode cannot know the tool count before the first expansion, so the
  // toolbar (search + expand) shows unconditionally there.
  const showToolbar = lazy || tools.length > 0 || loading;

  return (
    <div className={className} data-testid={rest["data-testid"]}>
      <Card
        expandable
        expanded={expanded}
        border="solid"
        rounding={4}
        padding={2}
        expandedContent={
          hasContent ? (
            <Section gap={2} padding={2}>
              {filteredTools.map((tool) => (
                <Card key={tool.id} border="solid" rounding={3}>
                  <InputHorizontal
                    icon={logo}
                    title={tool.name}
                    description={tool.description}
                    withLabel
                  >
                    <div
                      className={cn(
                        toolsLocked && "pointer-events-none opacity-50"
                      )}
                    >
                      {renderToolRight?.(tool)}
                    </div>
                  </InputHorizontal>
                </Card>
              ))}
              {footer}
            </Section>
          ) : undefined
        }
      >
        <CardLayout.Header
          bottomChildren={
            showToolbar ? (
              <Section flexDirection="row" gap={2}>
                <InputTypeIn
                  placeholder={t("search.placeholder")}
                  variant="internal"
                  searchIcon
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
                <Button
                  rightIcon={isFolded ? SvgExpand : SvgFold}
                  onClick={() => setIsFolded((prev) => !prev)}
                  prominence="internal"
                  size="lg"
                >
                  {isFolded ? t("expandButton.label") : t("foldButton.label")}
                </Button>
              </Section>
            ) : undefined
          }
        >
          <div className="p-2">
            <ContentAction
              icon={logo}
              title={name}
              description={description ?? undefined}
              sizePreset="main-ui"
              variant="section"
              padding={0}
              rightChildren={headerRight}
            />
          </div>
        </CardLayout.Header>
      </Card>
    </div>
  );
}

/** Convenience: a plain enable switch for a tool row. */
export function McpToolSwitch({
  checked,
  disabled,
  onCheckedChange,
  ariaLabel,
}: {
  checked: boolean;
  disabled?: boolean;
  onCheckedChange: (checked: boolean) => void;
  ariaLabel: string;
}) {
  return (
    <Switch
      checked={checked}
      onCheckedChange={onCheckedChange}
      disabled={disabled}
      aria-label={ariaLabel}
    />
  );
}
