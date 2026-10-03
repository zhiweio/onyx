"use client";

import { useTranslations } from "next-intl";
import { Button, Card, Checkbox, InputTypeIn, Text } from "@opal/components";
import { CATEGORY_MCP_ICON } from "@/lib/skills/categoryIcons";
import type { IconFunctionComponent } from "@opal/types";
import { cn } from "@opal/utils";
import useUserExternalApps from "@/hooks/useUserExternalApps";
import { useCraftMcpServers } from "@/lib/tools/hooks";
import { getActionIcon } from "@/lib/tools/utils";
import { getAppTypeLogo } from "@/app/craft/v1/apps/registry";
import { useSearchablePagination } from "@/hooks/useSearchablePagination";
import BrowsePagination from "@/sections/gallery/BrowsePagination";

interface PreApprovalPickerProps {
  selectedAppIds: number[];
  selectedMcpServerIds: number[];
  onAppChange: (ids: number[]) => void;
  onMcpServerChange: (ids: number[]) => void;
}

function toggledIds(selectedIds: number[], id: number): number[] {
  return selectedIds.includes(id)
    ? selectedIds.filter((selectedId) => selectedId !== id)
    : [...selectedIds, id];
}

export default function PreApprovalPicker({
  selectedAppIds,
  selectedMcpServerIds,
  onAppChange,
  onMcpServerChange,
}: PreApprovalPickerProps) {
  const t = useTranslations("craft.tasks.preApproval");
  const tShared = useTranslations("admin.shared");
  const {
    data: apps,
    isLoading: appsLoading,
    error: appsError,
  } = useUserExternalApps();
  const {
    data: mcpData,
    isLoading: mcpLoading,
    error: mcpError,
  } = useCraftMcpServers();

  const appOptions: PreApprovalOption[] = (apps ?? []).map((app) => ({
    id: app.id,
    name: app.name,
    status: app.authenticated
      ? t("status.connected")
      : t("status.connectionRequired"),
    icon: getAppTypeLogo(app.app_type),
    testId: `pre-approval-app-${app.id}`,
  }));
  const visibleMcpServers = mcpData?.mcp_servers ?? [];
  const visibleMcpServerIds = new Set(
    visibleMcpServers.map((server) => server.id)
  );
  const mcpOptions: PreApprovalOption[] = [
    ...visibleMcpServers.map((server) => ({
      id: server.id,
      name: server.name,
      description: server.description ?? "",
      status: server.craft_connected
        ? t("status.connected")
        : t("status.connectionRequired"),
      icon: getActionIcon(server.server_url, server.name),
      testId: `pre-approval-mcp-server-${server.id}`,
    })),
    ...(mcpData || mcpError
      ? selectedMcpServerIds
          .filter((id) => !visibleMcpServerIds.has(id))
          .map((id) => ({
            id,
            name: t("mcpServerFallbackName", { id }),
            description: "",
            status: t("status.unavailable"),
            icon: CATEGORY_MCP_ICON,
            testId: `pre-approval-mcp-server-${id}`,
          }))
      : []),
  ];
  const hasOptions = appOptions.length > 0 || mcpOptions.length > 0;

  if ((appsLoading || mcpLoading) && !hasOptions) {
    return (
      <Card background="none" border="dashed" rounding={4}>
        <Text font="secondary-body" color="text-03">
          {t("loading.label")}
        </Text>
      </Card>
    );
  }

  if ((appsError || mcpError) && !hasOptions) {
    return (
      <Card background="none" border="dashed" rounding={4}>
        <Text font="secondary-body" color="text-03">
          {t("errors.loadFailed")}
        </Text>
      </Card>
    );
  }

  if (!hasOptions) {
    return (
      <Card background="none" border="dashed" rounding={4}>
        <Text font="secondary-body" color="text-03">
          {t("empty.label")}
        </Text>
      </Card>
    );
  }

  return (
    <div
      className="flex w-full flex-col gap-4"
      data-testid="pre-approval-picker"
    >
      {(appsError || mcpError) && (
        <Card background="none" border="dashed" rounding={4}>
          <Text font="secondary-body" color="text-03">
            {t("errors.partialLoadFailed")}
          </Text>
        </Card>
      )}
      {appOptions.length > 0 && (
        <PreApprovalGroup
          title={t("appsGroupTitle")}
          options={appOptions}
          selectedIds={selectedAppIds}
          onToggle={(id) => onAppChange(toggledIds(selectedAppIds, id))}
          paginationUnits={tShared("pagination.units")}
        />
      )}
      {mcpOptions.length > 0 && (
        <PreApprovalGroup
          title={t("mcpGroupTitle")}
          options={mcpOptions}
          selectedIds={selectedMcpServerIds}
          onToggle={(id) =>
            onMcpServerChange(toggledIds(selectedMcpServerIds, id))
          }
          paginationUnits={tShared("pagination.units")}
        />
      )}
    </div>
  );
}

interface PreApprovalOption {
  id: number;
  name: string;
  description?: string;
  status: string;
  icon: IconFunctionComponent;
  testId: string;
}

interface PreApprovalGroupProps {
  title: string;
  options: PreApprovalOption[];
  selectedIds: number[];
  onToggle: (id: number) => void;
  paginationUnits: string;
}

function PreApprovalGroup({
  title,
  options,
  selectedIds,
  onToggle,
  paginationUnits,
}: PreApprovalGroupProps) {
  const t = useTranslations("craft.tasks.preApproval");
  const selected = new Set(selectedIds);

  // Selections always stay visible — a checked row must never vanish into a
  // later page just because its name does not match the query.
  const groupList = useSearchablePagination(options, (option, query) =>
    query ? option.name.toLowerCase().includes(query) : true
  );
  const pageOptions = groupList.pageItems.some((option) =>
    selected.has(option.id)
  )
    ? groupList.pageItems
    : [
        ...groupList.pageItems,
        ...options.filter(
          (option) =>
            selected.has(option.id) && !groupList.pageItems.includes(option)
        ),
      ];

  return (
    <section className="flex flex-col gap-2" aria-label={title}>
      <Text as="h3" font="main-ui-action" color="text-03">
        {title}
      </Text>
      {options.length > 12 && (
        <div className="max-w-sm">
          <InputTypeIn
            searchIcon
            variant="internal"
            value={groupList.searchQuery}
            onChange={(e) => groupList.setSearchQuery(e.target.value)}
            placeholder={t("search.placeholder")}
            aria-label={t("search.placeholder")}
          />
        </div>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {pageOptions.map((option) => (
          <PreApprovalRow
            key={option.id}
            option={option}
            checked={selected.has(option.id)}
            onToggle={() => onToggle(option.id)}
          />
        ))}
      </div>
      <BrowsePagination
        page={groupList.safePage}
        totalItems={groupList.filtered.length}
        onPageChange={groupList.setPage}
        units={paginationUnits}
      />
    </section>
  );
}

interface PreApprovalRowProps {
  option: PreApprovalOption;
  checked: boolean;
  onToggle: () => void;
}

function PreApprovalRow({ option, checked, onToggle }: PreApprovalRowProps) {
  const Logo = option.icon;
  const checkboxId = `${option.testId}-checkbox`;
  const statusId = `${option.testId}-status`;
  return (
    <div
      className={cn(
        "rounded-12 focus-within:outline-none focus-within:ring-2 focus-within:ring-action-selection-04",
        checked && "ring-2 ring-action-selection-04"
      )}
      data-testid={option.testId}
    >
      <Card background="light" border="solid" rounding={4}>
        <label
          className="flex w-full cursor-pointer items-center gap-3"
          htmlFor={checkboxId}
        >
          <Logo className="w-8 h-8" />
          <div className="flex-1 flex flex-col gap-1 min-w-0">
            <Text font="main-ui-action">{option.name}</Text>
            <Text id={statusId} font="secondary-body" color="text-03">
              {option.status}
            </Text>
          </div>
          <Checkbox
            id={checkboxId}
            aria-label={option.name}
            aria-describedby={statusId}
            checked={checked}
            onCheckedChange={onToggle}
          />
        </label>
      </Card>
    </div>
  );
}
