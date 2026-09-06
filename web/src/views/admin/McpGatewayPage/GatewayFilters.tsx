"use client";

import { useMemo, useState, type ReactNode } from "react";
import { useTranslations } from "next-intl";
import useSWR from "swr";
import { InputSelect } from "@opal/components";
import { cn } from "@opal/utils";
import Text from "@/refresh-components/texts/Text";
import {
  DateRangePicker,
  rangeForInclusiveDays,
  type DateRange,
} from "@/refresh-components/DateRangePicker";
import { errorHandlingFetcher } from "@/lib/fetcher";
import type { MCPServer, ToolSnapshot } from "@/lib/tools/types";

const ALL_SERVERS = "__all__";
const ALL_TOOLS = "__all__";

export interface GatewayFiltersProps {
  servers: MCPServer[];
  selectedSlug: string;
  onServerChange: (slug: string) => void;
  selectedTool: string;
  onToolChange: (tool: string) => void;
  dateRange: DateRange;
  onDateRangeChange: (range: DateRange) => void;
}

function FilterField({
  label,
  children,
  className,
  testId,
}: {
  label: string;
  children: ReactNode;
  className?: string;
  testId?: string;
}) {
  return (
    <div
      className={cn("flex min-w-44 flex-col gap-1.5", className)}
      data-testid={testId}
    >
      <Text as="p" secondaryBody text03>
        {label}
      </Text>
      {children}
    </div>
  );
}

export default function GatewayFilters({
  servers,
  selectedSlug,
  onServerChange,
  selectedTool,
  onToolChange,
  dateRange,
  onDateRangeChange,
}: GatewayFiltersProps) {
  const t = useTranslations("admin.mcpGateway");
  const [serverQuery, setServerQuery] = useState("");
  const [toolQuery, setToolQuery] = useState("");

  const selectedServer = servers.find(
    (server) => server.catalog_slug === selectedSlug
  );

  const { data: toolsData } = useSWR<ToolSnapshot[]>(
    selectedServer
      ? `/api/admin/mcp/server/${selectedServer.id}/tools/snapshots?source=db`
      : null,
    errorHandlingFetcher,
    { revalidateOnFocus: false, revalidateOnReconnect: false }
  );

  const filteredServers = useMemo(() => {
    const query = serverQuery.trim().toLowerCase();
    if (!query) return servers;
    return servers.filter((server) =>
      server.name.toLowerCase().includes(query)
    );
  }, [servers, serverQuery]);

  const tools = toolsData ?? [];
  const filteredTools = useMemo(() => {
    const query = toolQuery.trim().toLowerCase();
    if (!query) return tools;
    return tools.filter((tool) => {
      const label = (tool.display_name || tool.name).toLowerCase();
      return label.includes(query) || tool.name.toLowerCase().includes(query);
    });
  }, [tools, toolQuery]);

  return (
    <div
      className="grid w-full grid-cols-1 items-end gap-4 md:grid-cols-[minmax(13rem,16rem)_minmax(0,auto)_minmax(13rem,16rem)]"
      data-testid="mcp-gateway-filters"
    >
      <FilterField
        className="w-full"
        label={t("filter.server")}
        testId="mcp-gateway-server-filter"
      >
        <InputSelect
          value={selectedSlug || ALL_SERVERS}
          onValueChange={(value) => {
            onServerChange(value === ALL_SERVERS ? "" : value);
            onToolChange("");
          }}
          onOpenChange={(open) => {
            if (open) setServerQuery("");
          }}
        >
          <InputSelect.Trigger placeholder={t("filter.server")} />
          <InputSelect.Content>
            <InputSelect.Search
              value={serverQuery}
              onChange={(event) => setServerQuery(event.target.value)}
              placeholder={t("filter.serverSearch")}
            />
            <InputSelect.Item value={ALL_SERVERS}>
              {t("filter.all")}
            </InputSelect.Item>
            {filteredServers.map((server) =>
              server.catalog_slug ? (
                <InputSelect.Item key={server.id} value={server.catalog_slug}>
                  {server.name}
                </InputSelect.Item>
              ) : null
            )}
          </InputSelect.Content>
        </InputSelect>
      </FilterField>

      <FilterField
        className="min-w-0"
        label={t("filter.time")}
        testId="mcp-gateway-time-filter"
      >
        <DateRangePicker
          value={dateRange ?? rangeForInclusiveDays(7)}
          onValueChange={onDateRangeChange}
          size="md"
          className="min-h-10 w-full justify-center rounded-08 border border-border-01 bg-background-neutral-00"
        />
      </FilterField>

      <FilterField
        className="w-full"
        label={t("filter.tool")}
        testId="mcp-gateway-tool-filter"
      >
        <InputSelect
          value={selectedTool || ALL_TOOLS}
          disabled={!selectedServer}
          onValueChange={(value) =>
            onToolChange(value === ALL_TOOLS ? "" : value)
          }
          onOpenChange={(open) => {
            if (open) setToolQuery("");
          }}
        >
          <InputSelect.Trigger
            placeholder={
              selectedServer
                ? t("filter.toolPlaceholder")
                : t("filter.toolDisabled")
            }
          />
          <InputSelect.Content>
            <InputSelect.Search
              value={toolQuery}
              onChange={(event) => setToolQuery(event.target.value)}
              placeholder={t("filter.toolSearch")}
            />
            <InputSelect.Item value={ALL_TOOLS}>
              {t("filter.toolAll")}
            </InputSelect.Item>
            {filteredTools.map((tool) => (
              <InputSelect.Item key={tool.id} value={tool.name}>
                {tool.display_name || tool.name}
              </InputSelect.Item>
            ))}
          </InputSelect.Content>
        </InputSelect>
      </FilterField>
    </div>
  );
}
