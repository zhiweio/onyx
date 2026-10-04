"use client";

import { useState, useCallback } from "react";
import { useTranslations } from "next-intl";
import { useFocusOnMount } from "@opal/hooks";
import { Button, InputTypeIn, Popover, PopoverMenu } from "@opal/components";
import { SvgSliders } from "@opal/icons";

import { MinimalAgent } from "@/lib/agents/types";
import useCCPairs from "@/hooks/useCCPairs";
import { useProjectsContext } from "@/lib/projects/providers";
import { useSettings } from "@/lib/settings/hooks";
import { SEARCH_TOOL_ID } from "@/lib/tools/constants";
import { shouldShowBuiltInToolInChatMenu } from "@/lib/tools/chatToolVisibility";
import {
  useAvailableTools,
  useBuiltInToolNames,
  type ToolConfigurationHandle,
} from "@/lib/tools/hooks";
import { ToolsPopoverProvider } from "@/lib/tools/providers";
import SourcesView from "@/lib/tools/components/SourcesView";
import ToolLineItem from "@/lib/tools/components/ToolLineItem";

/**
 * The actions popover.
 *
 * Takes the agent rather than resolving one. Built-in tool rows are its tools.
 * MCP servers are not chosen here: enablement lives on /craft/v1/mcp-actions
 * and every enabled server is injected once per session.
 *
 * Callers should key this on the agent, so switching starts clean rather than
 * carrying the previous agent's open panel and search term across.
 */
export interface ToolsPopoverProps {
  agent: MinimalAgent;
  /**
   * Owned by the surface, because the send path reads the same one. The
   * popover decides nothing about where it lives or how long it lasts.
   */
  toolConfiguration: ToolConfigurationHandle;
  disabled?: boolean;
}

export default function ToolsPopover({
  agent,
  toolConfiguration,
  disabled = false,
}: ToolsPopoverProps) {
  const t = useTranslations("actions");
  const builtInToolNames = useBuiltInToolNames();
  const [open, setOpen] = useState(false);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const focusOnMount = useFocusOnMount<HTMLInputElement>();

  const { vectorDbEnabled } = useSettings();
  const { ccPairs } = useCCPairs(vectorDbEnabled);
  const { currentProjectId, allCurrentProjectFiles } = useProjectsContext();
  const { tools: availableTools, isLoading: isAvailableToolsLoading } =
    useAvailableTools();

  const hasNoConnectors = ccPairs.length === 0;
  const availableToolIds = isAvailableToolsLoading
    ? null
    : new Set(availableTools.map((tool) => tool.id));

  const close = useCallback(() => setOpen(false), []);
  const openSources = useCallback(() => setSourcesOpen(true), []);

  const displayTools = agent.tools.filter((tool) =>
    shouldShowBuiltInToolInChatMenu({
      tool,
      availableToolIds,
      currentProjectId,
      hasProjectFiles: (allCurrentProjectFiles?.length ?? 0) > 0,
      hasNoConnectors,
    })
  );

  // Filter tools based on search term
  const filteredTools = displayTools.filter((tool) => {
    if (!searchTerm) return true;
    const searchLower = searchTerm.toLowerCase();
    // Match the name the row actually shows, including the rename search
    // takes on inside a project, so typing what is on screen finds it. The
    // raw names stay searchable below for anyone who knows them.
    const shownName =
      currentProjectId != null && tool.in_code_tool_id === SEARCH_TOOL_ID
        ? t("actionLineItem.projectSearch.label")
        : (builtInToolNames[tool.in_code_tool_id ?? ""] ?? tool.display_name);
    return (
      shownName?.toLowerCase().includes(searchLower) ||
      tool.display_name?.toLowerCase().includes(searchLower) ||
      tool.name.toLowerCase().includes(searchLower) ||
      tool.description?.toLowerCase().includes(searchLower)
    );
  });

  const handleOpenChange = (newOpen: boolean) => {
    setOpen(newOpen);
    if (newOpen) {
      setSourcesOpen(false);
      setSearchTerm("");
    }
  };

  const primaryView = (
    <PopoverMenu>
      {[
        <InputTypeIn
          key="search"
          placeholder={t("toolsPopover.search.placeholder")}
          searchIcon
          value={searchTerm}
          onChange={(event) => setSearchTerm(event.target.value)}
          ref={focusOnMount}
          variant="internal"
        />,

        ...filteredTools.map((tool) => (
          <ToolLineItem key={tool.id} tool={tool} />
        )),
      ]}
    </PopoverMenu>
  );

  if (displayTools.length === 0) {
    return null;
  }

  return (
    <ToolsPopoverProvider
      agent={agent}
      toolConfiguration={toolConfiguration}
      openSources={openSources}
      close={close}
    >
      <Popover open={open} onOpenChange={handleOpenChange}>
        <Popover.Trigger asChild>
          <div data-testid="action-management-toggle">
            <Button
              disabled={disabled}
              icon={SvgSliders}
              interaction={open ? "hover" : "rest"}
              prominence="tertiary"
              tooltip={t("toolsPopover.manageActions.tooltip")}
            />
          </div>
        </Popover.Trigger>
        <Popover.Content side="bottom" align="start" width="lg">
          <div data-testid="tool-options">
            {sourcesOpen ? (
              <SourcesView onBack={() => setSourcesOpen(false)} />
            ) : (
              primaryView
            )}
          </div>
        </Popover.Content>
      </Popover>
    </ToolsPopoverProvider>
  );
}
