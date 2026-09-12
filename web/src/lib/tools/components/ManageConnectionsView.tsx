"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { useFocusOnMount } from "@opal/hooks";
import { Button, InputTypeIn, PopoverMenu, Text } from "@opal/components";
import { SvgChevronLeft, SvgExternalLink } from "@opal/icons";

import { CRAFT_MCP_ACTIONS_PATH } from "@/app/craft/v1/constants";
import MCPLineItem, { MCPServer } from "@/lib/tools/components/MCPLineItem";
import type { ToolSnapshot } from "@/lib/tools/types";

export default function ManageConnectionsView({
  canManage,
  enabledToolsByServer,
  mcpServerData,
  onAuthenticate,
  onBack,
  onSelectServer,
  onToggleServer,
  servers,
  toolsByServer,
  enabledServerIds,
  manageHref = CRAFT_MCP_ACTIONS_PATH,
}: {
  canManage: boolean;
  enabledToolsByServer: Map<number, ToolSnapshot[]>;
  mcpServerData: {
    [serverId: number]: { isAuthenticated: boolean; isLoading: boolean };
  };
  onAuthenticate: (server: MCPServer) => void;
  onBack: () => void;
  onSelectServer: (serverId: number) => void;
  onToggleServer: (serverId: number, enabled: boolean) => void;
  servers: MCPServer[];
  toolsByServer: Map<number, ToolSnapshot[]>;
  /** Servers the current agent will use on the next send. Default none. */
  enabledServerIds: ReadonlySet<number>;
  /** User MCP page (Mine + Gallery). Do not send chat users to admin. */
  manageHref?: string;
}) {
  const t = useTranslations("actions");
  const [searchTerm, setSearchTerm] = useState("");
  const focusOnMount = useFocusOnMount<HTMLInputElement>();
  const filteredServers = useMemo(() => {
    if (!searchTerm) return servers;
    const searchLower = searchTerm.toLowerCase();
    return servers.filter((server) =>
      server.name.toLowerCase().includes(searchLower)
    );
  }, [searchTerm, servers]);

  return (
    <PopoverMenu>
      {[
        <div className="flex items-center gap-1" key="header">
          <Button
            icon={SvgChevronLeft}
            prominence="tertiary"
            size="sm"
            aria-label={t("switchList.back.ariaLabel")}
            onClick={() => {
              setSearchTerm("");
              onBack();
            }}
          />
          <div className="min-w-0 flex-1">
            <InputTypeIn
              variant="internal"
              searchIcon
              placeholder={t("toolsPopover.mcp.searchPlaceholder")}
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              ref={focusOnMount}
            />
          </div>
          {canManage ? (
            <Button
              href={manageHref}
              target="_blank"
              prominence="tertiary"
              size="sm"
              rightIcon={SvgExternalLink}
            >
              {t("toolsPopover.mcp.manage")}
            </Button>
          ) : null}
        </div>,
        ...(filteredServers.length === 0
          ? [
              <Text
                key="empty"
                font="secondary-body"
                color="text-03"
                className="px-2 py-2"
              >
                {servers.length === 0
                  ? canManage
                    ? t("toolsPopover.manageConnections.empty")
                    : t("toolsPopover.manageConnections.askAdmin")
                  : t("toolsPopover.manageConnections.empty")}
              </Text>,
            ]
          : filteredServers.map((server) => {
              const serverData = mcpServerData[server.id] || {
                isAuthenticated: !!server.user_can_authenticate,
                isLoading: false,
              };
              const serverTools = toolsByServer.get(server.id) ?? [];
              const enabledTools = enabledToolsByServer.get(server.id) ?? [];
              const serverEnabled = enabledServerIds.has(server.id);
              return (
                <MCPLineItem
                  key={server.id}
                  server={server}
                  isActive={false}
                  tools={serverTools}
                  enabledTools={enabledTools}
                  enabled={serverEnabled}
                  isAuthenticated={serverData.isAuthenticated}
                  isLoading={serverData.isLoading}
                  control="switch"
                  onSelect={() => onSelectServer(server.id)}
                  onAuthenticate={() => onAuthenticate(server)}
                  onToggleEnabled={() =>
                    onToggleServer(server.id, !serverEnabled)
                  }
                />
              );
            })),
      ]}
    </PopoverMenu>
  );
}
