"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { useTranslations } from "next-intl";
import { useFocusOnMount } from "@opal/hooks";
import {
  InputTypeIn,
  Button,
  LineItemButton,
  Popover,
  PopoverMenu,
} from "@opal/components";
import {
  SvgChevronRight,
  SvgKey,
  SvgMcp,
  SvgSliders,
  SvgSimpleLoader,
} from "@opal/icons";

import { MinimalAgent } from "@/lib/agents/types";
import MCPApiKeyModal from "@/components/chat/MCPApiKeyModal";
import useCCPairs from "@/hooks/useCCPairs";
import { useProjectsContext } from "@/lib/projects/providers";
import { useSettings } from "@/lib/settings/hooks";
import { SEARCH_TOOL_ID } from "@/lib/tools/constants";
import { shouldShowBuiltInToolInChatMenu } from "@/lib/tools/chatToolVisibility";
import {
  useAvailableTools,
  useBuiltInToolNames,
  useMcpServers,
  type ToolConfigurationHandle,
} from "@/lib/tools/hooks";
import { toChatMcpServer } from "@/lib/tools/mcpSelection";
import { ToolsPopoverProvider } from "@/lib/tools/providers";
import ManageConnectionsView from "@/lib/tools/components/ManageConnectionsView";
import { MCPServer } from "@/lib/tools/components/MCPLineItem";
import SourcesView from "@/lib/tools/components/SourcesView";
import SwitchList, { SwitchListItem } from "@/lib/tools/components/SwitchList";
import ToolLineItem from "@/lib/tools/components/ToolLineItem";
import {
  MCPAuthenticationType,
  MCPAuthenticationPerformer,
  SecondaryViewState,
} from "@/lib/tools/types";
import {
  getMCPUserOAuthNavigationUrl,
  saveMCPUserCredentials,
  startMCPUserOAuth,
} from "@/lib/tools/svc";

/**
 * The actions popover.
 *
 * Takes the agent rather than resolving one. Built-in tool rows are its
 * tools; the MCP list is every server this user may use, default off, and
 * turning one on attaches it for the current agent's next send.
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
  const [secondaryView, setSecondaryView] = useState<SecondaryViewState | null>(
    null
  );
  const [searchTerm, setSearchTerm] = useState("");
  const focusOnMount = useFocusOnMount<HTMLInputElement>();
  const { mcpData } = useMcpServers();
  const mcpServers = useMemo(
    () => (mcpData?.mcp_servers ?? []).map(toChatMcpServer),
    [mcpData]
  );

  // Store MCP server auth/loading state (tools are part of agent.tools)
  const [mcpServerData, setMcpServerData] = useState<{
    [serverId: number]: {
      isAuthenticated: boolean;
      isLoading: boolean;
    };
  }>({});

  const [mcpApiKeyModal, setMcpApiKeyModal] = useState<{
    isOpen: boolean;
    serverId: number | null;
    serverName: string;
    authTemplate?: any;
    onSuccess?: () => void;
    isAuthenticated?: boolean;
    existingCredentials?: Record<string, string>;
  }>({
    isOpen: false,
    serverId: null,
    serverName: "",
    authTemplate: undefined,
    onSuccess: undefined,
    isAuthenticated: false,
  });

  const { vectorDbEnabled, onyx_craft_enabled } = useSettings();
  const { ccPairs } = useCCPairs(vectorDbEnabled);
  const { currentProjectId, allCurrentProjectFiles } = useProjectsContext();
  const { tools: availableTools, isLoading: isAvailableToolsLoading } =
    useAvailableTools();

  const hasNoConnectors = ccPairs.length === 0;
  // Chat "Manage" opens the user MCP library, not the admin installer.
  const canManageMcp = onyx_craft_enabled === true;
  const availableToolIds = isAvailableToolsLoading
    ? null
    : new Set(availableTools.map((tool) => tool.id));

  const close = useCallback(() => setOpen(false), []);
  const openSources = useCallback(
    () => setSecondaryView({ type: "sources" }),
    []
  );

  const displayTools = agent.tools.filter((tool) =>
    shouldShowBuiltInToolInChatMenu({
      tool,
      availableToolIds,
      currentProjectId,
      hasProjectFiles: (allCurrentProjectFiles?.length ?? 0) > 0,
      hasNoConnectors,
    })
  );

  useEffect(() => {
    setMcpServerData((prev) => {
      const next = { ...prev };
      for (const server of mcpServers) {
        next[server.id] = {
          isAuthenticated: !!server.user_can_authenticate,
          isLoading: prev[server.id]?.isLoading ?? false,
        };
      }
      return next;
    });
  }, [mcpServers]);

  // Handle MCP authentication
  const handleMCPAuthenticate = async (
    serverId: number,
    authType: MCPAuthenticationType,
    forceReauthentication = false
  ) => {
    if (authType === MCPAuthenticationType.OAUTH) {
      const updateLoadingState = (loading: boolean) => {
        setMcpServerData((prev) => {
          const previous = prev[serverId] ?? {
            isAuthenticated: false,
            isLoading: false,
          };
          return {
            ...prev,
            [serverId]: {
              ...previous,
              isLoading: loading,
            },
          };
        });
      };

      updateLoadingState(true);
      try {
        const oauthStart = await startMCPUserOAuth(
          serverId,
          window.location.pathname + window.location.search,
          { forceReauthentication }
        );
        window.location.href = getMCPUserOAuthNavigationUrl(oauthStart);
      } catch (error) {
        console.error("Error initiating OAuth:", error);
        updateLoadingState(false);
        throw error;
      }
    }
  };

  // Both submit paths are the same request; the API-key form just names its
  // one field. `saveMCPUserCredentials` owns the endpoint and its errors.
  const handleMCPApiKeySubmit = (serverId: number, apiKey: string) =>
    saveMCPUserCredentials(serverId, { api_key: apiKey });

  const handleMCPCredentialsSubmit = (
    serverId: number,
    credentials: Record<string, string>
  ) => saveMCPUserCredentials(serverId, credentials);

  const handleServerAuthentication = (
    server: MCPServer,
    forceReauthentication = false
  ) => {
    const authType = server.auth_type;
    const performer = server.auth_performer;
    const requiresHeaderValues =
      (server.auth_template?.required_fields.length ?? 0) > 0;

    if (!requiresHeaderValues && authType === MCPAuthenticationType.OAUTH) {
      void handleMCPAuthenticate(
        server.id,
        MCPAuthenticationType.OAUTH,
        forceReauthentication
      ).catch(() => undefined);
      return;
    }
    if (
      !requiresHeaderValues &&
      (authType === MCPAuthenticationType.NONE ||
        performer === MCPAuthenticationPerformer.ADMIN)
    ) {
      return;
    }
    if (requiresHeaderValues || authType === MCPAuthenticationType.API_TOKEN) {
      setMcpApiKeyModal({
        isOpen: true,
        serverId: server.id,
        serverName: server.name,
        authTemplate: server.auth_template,
        onSuccess: async () => {
          if (authType === MCPAuthenticationType.OAUTH) {
            await handleMCPAuthenticate(
              server.id,
              MCPAuthenticationType.OAUTH,
              forceReauthentication
            );
            return;
          }
          setMcpServerData((prev) => ({
            ...prev,
            [server.id]: {
              ...prev[server.id],
              isAuthenticated: true,
              isLoading: false,
            },
          }));
          toolConfiguration.setMcpServerEnabled(server.id, true);
        },
        isAuthenticated: server.user_can_authenticate,
        existingCredentials: server.user_credentials,
      });
    }
  };

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

  const mcpLabel = t("toolsPopover.mcp.label");
  const searchLower = searchTerm.toLowerCase();
  const mcpRowMatchesSearch =
    !searchTerm ||
    mcpLabel.toLowerCase().includes(searchLower) ||
    mcpServers.some((server) =>
      server.name.toLowerCase().includes(searchLower)
    );
  const showMcpRow =
    (mcpServers.length > 0 || canManageMcp) && mcpRowMatchesSearch;

  const selectedMcpServerId =
    secondaryView?.type === "mcp" ? secondaryView.serverId : null;
  const selectedMcpServer = selectedMcpServerId
    ? mcpServers.find((server) => server.id === selectedMcpServerId)
    : undefined;
  const selectedMcpTools =
    selectedMcpServerId !== null
      ? agent.tools.filter(
          (t) => t.mcp_server_id === Number(selectedMcpServerId)
        )
      : [];
  const selectedMcpServerData = selectedMcpServer
    ? mcpServerData[selectedMcpServer.id]
    : undefined;
  const isActiveServerAuthenticated =
    selectedMcpServerData?.isAuthenticated ??
    !!selectedMcpServer?.user_can_authenticate;
  const showActiveReauthRow =
    !!selectedMcpServer &&
    selectedMcpTools.length > 0 &&
    selectedMcpServer.auth_performer === MCPAuthenticationPerformer.PER_USER &&
    selectedMcpServer.auth_type !== MCPAuthenticationType.NONE &&
    isActiveServerAuthenticated;

  const mcpToggleItems: SwitchListItem[] = selectedMcpTools.map((tool) => ({
    id: tool.id.toString(),
    label: tool.display_name || tool.name,
    description: tool.description,
    isEnabled: !toolConfiguration.disabledToolIds.includes(tool.id),
    onToggle: () => toolConfiguration.toggleToolState(tool.id, "disabled"),
  }));

  const mcpAllDisabled = selectedMcpTools.every((tool) =>
    toolConfiguration.disabledToolIds.includes(tool.id)
  );

  // One call per tool rather than a second setter taking many. React batches
  // them, and each sees what the one before it left, so the rules hold across
  // the run instead of the last write landing on a stale map.
  const setServerToolsDisabled = (serverId: number, disabled: boolean) => {
    for (const tool of agent.tools) {
      if (tool.mcp_server_id !== serverId) continue;
      toolConfiguration.setToolState(tool.id, () =>
        disabled ? "disabled" : null
      );
    }
  };

  const setSelectedServerToolsDisabled = (disabled: boolean) => {
    if (!selectedMcpServer) return;
    setServerToolsDisabled(selectedMcpServer.id, disabled);
  };

  const toolsByServer = new Map(
    mcpServers.map((server) => [
      server.id,
      agent.tools.filter((tool) => tool.mcp_server_id === server.id),
    ])
  );
  const enabledToolsByServer = new Map(
    [...toolsByServer.entries()].map(([serverId, serverTools]) => [
      serverId,
      serverTools.filter(
        (tool) => !toolConfiguration.disabledToolIds.includes(tool.id)
      ),
    ])
  );
  const enabledServerIds = useMemo(
    () => new Set(toolConfiguration.selectedMcpServerIds),
    [toolConfiguration.selectedMcpServerIds]
  );

  const handleToggleServer = (serverId: number, enabled: boolean) => {
    toolConfiguration.setMcpServerEnabled(serverId, enabled);
    if (enabled) {
      setServerToolsDisabled(serverId, false);
    }
  };

  const handleFooterReauthClick = () => {
    if (selectedMcpServer) {
      handleServerAuthentication(selectedMcpServer, true);
    }
  };

  const handleOpenChange = (newOpen: boolean) => {
    setOpen(newOpen);
    if (newOpen) {
      setSecondaryView(null);
      setSearchTerm("");
    }
  };

  const mcpFooter = showActiveReauthRow ? (
    <LineItemButton
      disabled={selectedMcpServerData?.isLoading}
      onClick={handleFooterReauthClick}
      icon={selectedMcpServerData?.isLoading ? SvgSimpleLoader : SvgKey}
      title={t("toolsPopover.reauthenticate.label")}
      sizePreset="main-ui"
      variant="section"
    />
  ) : undefined;

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

        showMcpRow ? (
          <LineItemButton
            key="mcp"
            onClick={() => setSecondaryView({ type: "mcpList" })}
            icon={SvgMcp}
            title={mcpLabel}
            sizePreset="main-ui"
            variant="section"
            rounding={2}
            rightChildren={
              <span
                aria-hidden="true"
                className="pointer-events-none flex size-6 shrink-0 items-center justify-center"
              >
                <SvgChevronRight className="size-4 stroke-text-03" />
              </span>
            }
          />
        ) : (
          false
        ),
      ]}
    </PopoverMenu>
  );

  const manageView = (
    <ManageConnectionsView
      canManage={canManageMcp}
      enabledToolsByServer={enabledToolsByServer}
      mcpServerData={mcpServerData}
      onAuthenticate={handleServerAuthentication}
      onBack={() => setSecondaryView(null)}
      onSelectServer={(serverId) =>
        setSecondaryView({ type: "mcp", serverId, from: "mcpList" })
      }
      onToggleServer={handleToggleServer}
      servers={mcpServers}
      toolsByServer={toolsByServer}
      enabledServerIds={enabledServerIds}
    />
  );

  const mcpView = (
    <SwitchList
      items={mcpToggleItems}
      searchPlaceholder={t("toolsPopover.mcpTools.searchPlaceholder", {
        server:
          selectedMcpServer?.name ?? t("toolsPopover.serverFallback.label"),
      })}
      allDisabled={mcpAllDisabled}
      onDisableAll={() => setSelectedServerToolsDisabled(true)}
      onEnableAll={() => setSelectedServerToolsDisabled(false)}
      disableAllLabel={t("toolsPopover.disableAllTools.label")}
      enableAllLabel={t("toolsPopover.enableAllTools.label")}
      onBack={() =>
        setSecondaryView(
          secondaryView?.type === "mcp" && secondaryView.from === "mcpList"
            ? { type: "mcpList" }
            : null
        )
      }
      footer={mcpFooter}
    />
  );

  if (displayTools.length === 0 && mcpServers.length === 0 && !canManageMcp) {
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
            {secondaryView ? (
              secondaryView.type === "mcp" ? (
                mcpView
              ) : secondaryView.type === "mcpList" ? (
                manageView
              ) : (
                <SourcesView onBack={() => setSecondaryView(null)} />
              )
            ) : (
              primaryView
            )}
          </div>
        </Popover.Content>
      </Popover>

      {/* MCP API Key Modal */}
      {mcpApiKeyModal.isOpen && (
        <MCPApiKeyModal
          isOpen={mcpApiKeyModal.isOpen}
          onClose={() =>
            setMcpApiKeyModal({
              isOpen: false,
              serverId: null,
              serverName: "",
              authTemplate: undefined,
              onSuccess: undefined,
              isAuthenticated: false,
              existingCredentials: undefined,
            })
          }
          serverName={mcpApiKeyModal.serverName}
          serverId={mcpApiKeyModal.serverId ?? 0}
          authTemplate={mcpApiKeyModal.authTemplate}
          onSubmit={handleMCPApiKeySubmit}
          onSubmitCredentials={handleMCPCredentialsSubmit}
          onSuccess={mcpApiKeyModal.onSuccess}
          isAuthenticated={mcpApiKeyModal.isAuthenticated}
          existingCredentials={mcpApiKeyModal.existingCredentials}
        />
      )}
    </ToolsPopoverProvider>
  );
}
