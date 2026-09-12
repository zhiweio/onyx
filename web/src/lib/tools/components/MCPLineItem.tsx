"use client";

import React from "react";
import { Button, LineItemButton, Switch } from "@opal/components";
import { Hoverable } from "@opal/core";
import { cn } from "@opal/utils";
import type { IconProps } from "@opal/types";
import {
  SvgCheck,
  SvgChevronRight,
  SvgKey,
  SvgLock,
  SvgServer,
  SvgSimpleLoader,
  SvgSlash,
} from "@opal/icons";

import { useTranslations } from "next-intl";
import { useUser } from "@/providers/UserProvider";
import { Section } from "@/layouts/general-layouts";
import {
  MCPAuthenticationType,
  MCPAuthenticationPerformer,
  McpServerScope,
  ToolSnapshot,
} from "@/lib/tools/types";
import EnabledCount from "@/refresh-components/EnabledCount";

export interface MCPServer {
  id: number;
  name: string;
  owner_email: string;
  server_url: string;
  auth_type: MCPAuthenticationType;
  auth_performer: MCPAuthenticationPerformer;
  user_can_authenticate?: boolean;
  auth_template?: any;
  user_credentials?: Record<string, string>;
  scope?: McpServerScope;
  owner?: string;
}

export interface MCPLineItemProps {
  server: MCPServer;
  isActive: boolean;
  onSelect: () => void;
  onAuthenticate: () => void;
  tools: ToolSnapshot[];
  enabledTools: ToolSnapshot[];
  isAuthenticated: boolean;
  isLoading: boolean;
  onToggleEnabled?: () => void;
  /** Slash is the older inline control. Switch matches the Cursor MCP list. */
  control?: "slash" | "switch";
}

export default function MCPLineItem({
  server,
  isActive,
  onSelect,
  onAuthenticate,
  tools,
  enabledTools,
  isAuthenticated,
  isLoading,
  onToggleEnabled,
  control = "slash",
}: MCPLineItemProps) {
  const t = useTranslations("actions.mcpLineItem");
  const tActions = useTranslations("actions");
  const { user } = useUser();
  const isPersonal = server.scope === McpServerScope.PERSONAL;
  const isOwner =
    server.owner === user?.email || server.owner_email === user?.email;
  const displayName = isPersonal
    ? isOwner
      ? t("personal", { name: server.name })
      : t("personalOnlyYou", { name: server.name })
    : server.name;

  const showAuthTrigger =
    server.auth_performer === MCPAuthenticationPerformer.PER_USER &&
    server.auth_type !== MCPAuthenticationType.NONE;

  const canClickIntoServer = isAuthenticated && tools.length > 0;
  const showInlineReauth = showAuthTrigger && canClickIntoServer;
  const showReauthButton = showAuthTrigger && !showInlineReauth;

  function getServerIcon(): React.FunctionComponent<IconProps> {
    if (isLoading) return SvgSimpleLoader;
    if (isAuthenticated) {
      return (({ className }) => (
        <SvgCheck className={cn(className, "stroke-status-success-05")} />
      )) as React.FunctionComponent<IconProps>;
    }
    if (server.auth_type === MCPAuthenticationType.NONE) return SvgServer;
    if (server.auth_performer === MCPAuthenticationPerformer.PER_USER) {
      return (({ className }) => (
        <SvgKey className={cn(className, "stroke-status-warning-05")} />
      )) as React.FunctionComponent<IconProps>;
    }
    return (({ className }) => (
      <SvgLock className={cn(className, "stroke-status-error-05")} />
    )) as React.FunctionComponent<IconProps>;
  }

  function handleClick() {
    if (canClickIntoServer) {
      onSelect();
      return;
    }
    if (showAuthTrigger) onAuthenticate();
  }

  const allToolsDisabled = enabledTools.length === 0 && tools.length > 0;
  const serverEnabled = isAuthenticated && enabledTools.length > 0;
  const useSwitch = control === "switch";
  const toggleLabel = allToolsDisabled
    ? tActions("actionLineItem.enable.label")
    : tActions("actionLineItem.disable.label");
  const toggleButton = !onToggleEnabled ? null : useSwitch ? (
    <span
      onClick={(event) => event.stopPropagation()}
      onPointerDown={(event) => event.stopPropagation()}
    >
      <Switch
        checked={serverEnabled}
        disabled={isLoading}
        aria-label={tActions("switchList.toggle.ariaLabel", {
          name: displayName,
        })}
        onCheckedChange={(checked) => {
          if (!isAuthenticated) {
            if (checked) onAuthenticate();
            return;
          }
          onToggleEnabled();
        }}
      />
    </span>
  ) : (
    <Button
      icon={SvgSlash}
      prominence="internal"
      size="sm"
      aria-label={toggleLabel}
      tooltip={toggleLabel}
      onClick={onToggleEnabled}
    />
  );

  return (
    <Hoverable.Root group="MCPLineItem">
      <LineItemButton
        title={displayName}
        icon={getServerIcon()}
        sizePreset="main-ui"
        variant="section"
        state={isActive ? "selected" : "empty"}
        strikethrough={!useSwitch && allToolsDisabled}
        color={!useSwitch && allToolsDisabled ? "muted" : undefined}
        onClick={handleClick}
        rightChildren={
          <Section gap={1} flexDirection="row">
            {!useSwitch &&
              isAuthenticated &&
              tools.length > 0 &&
              enabledTools.length > 0 &&
              tools.length !== enabledTools.length && (
                <EnabledCount
                  enabledCount={enabledTools.length}
                  totalCount={tools.length}
                />
              )}
            {toggleButton ? (
              useSwitch || allToolsDisabled ? (
                toggleButton
              ) : (
                <Hoverable.Item group="MCPLineItem">
                  {toggleButton}
                </Hoverable.Item>
              )
            ) : null}
            {!useSwitch && canClickIntoServer && (
              <span
                aria-hidden="true"
                className="pointer-events-none flex size-6 shrink-0 items-center justify-center"
              >
                <SvgChevronRight className="size-4 stroke-text-03" />
              </span>
            )}
            {!useSwitch && showReauthButton && (
              <span
                aria-hidden="true"
                className="pointer-events-none flex size-6 shrink-0 items-center justify-center"
              >
                <SvgKey className="size-4 stroke-text-03" />
              </span>
            )}
          </Section>
        }
      />
    </Hoverable.Root>
  );
}
