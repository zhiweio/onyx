"use client";

import type { ReactNode } from "react";
import { useTranslations } from "next-intl";
import useSWR from "swr";
import { Card, Text } from "@opal/components";
import { Section } from "@opal/layouts";
import { getMcpGatewayStatsSeries } from "@/lib/mcp-catalog/api";
import type {
  McpGatewayStats,
  McpGatewayStatsSeries,
} from "@/lib/mcp-catalog/types";
import AreaChart from "@/refresh-components/AreaChart";
import BarChart from "@/refresh-components/BarChart";
import { formatCalendarDay } from "@/lib/dateUtils";
import type { DateRange } from "@/refresh-components/DateRangePicker";
import { formatBytes, formatPercent } from "./format";

const SERIES_COLORS = [
  "var(--theme-purple-05)",
  "var(--theme-magenta-05)",
  "var(--theme-purple-04)",
  "var(--theme-magenta-04)",
  "var(--theme-purple-03)",
] as const;

interface GatewayOverviewProps {
  stats: McpGatewayStats;
  dateRange: DateRange;
  catalogSlug: string;
}

function remapCategories(
  rows: Array<Record<string, string | number>>,
  index: string,
  labels: Record<string, string>
): Array<Record<string, string | number>> {
  return rows.map((row) => {
    const next: Record<string, string | number> = {
      [index]: row[index] ?? "",
    };
    for (const [key, label] of Object.entries(labels)) {
      if (key in row) {
        next[label] = row[key] ?? 0;
      }
    }
    return next;
  });
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Card border="solid" rounding={4} padding={4}>
      <Section
        flexDirection="column"
        justifyContent="start"
        alignItems="stretch"
        gap={0.125}
        width="full"
        height="fit"
      >
        <Text font="secondary-body" color="text-03">
          {label}
        </Text>
        <Text font="heading-h3">{value}</Text>
      </Section>
    </Card>
  );
}

function ChartCard({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <Card border="solid" rounding={4} padding={6}>
      <Section
        flexDirection="column"
        justifyContent="start"
        alignItems="stretch"
        gap={0.5}
        width="full"
        height="fit"
      >
        <Text font="heading-h3">{title}</Text>
        {children}
      </Section>
    </Card>
  );
}

export default function GatewayOverview({
  stats,
  dateRange,
  catalogSlug,
}: GatewayOverviewProps) {
  const t = useTranslations("admin.mcpGateway");
  const charts = useTranslations("admin.mcpGateway.charts");
  const fromIso = dateRange?.from?.toISOString();
  const toIso = dateRange?.to?.toISOString();
  const { data: series } = useSWR<McpGatewayStatsSeries>(
    fromIso && toIso
      ? ["mcp-gateway-series", fromIso, toIso, catalogSlug]
      : null,
    ([, from, to, slug]: [string, string, string, string]) =>
      getMcpGatewayStatsSeries({
        from,
        to,
        catalog_slug: slug || undefined,
      }),
    { revalidateOnFocus: false, revalidateOnReconnect: false }
  );

  const outcomeLabels = {
    hit: charts("series.hit"),
    miss: charts("series.miss"),
    swr: charts("series.swr"),
    bypass: charts("series.bypass"),
    error: charts("series.error"),
  };
  const latencyLabels = {
    p50: charts("series.p50"),
    p95: charts("series.p95"),
  };
  const billedLabels = {
    billed: charts("series.billed"),
    saved: charts("series.saved"),
  };
  const countLabel = charts("series.count");
  const bytesLabel = charts("series.bytes");

  const topServers = (series?.top_servers ?? stats.top_servers ?? []).map(
    (row) => ({ server: row.slug, [countLabel]: row.count })
  );
  const topTools = (series?.top_tools ?? stats.top_tools ?? []).map((row) => ({
    tool: row.tool,
    [countLabel]: row.count,
  }));
  const bytesByServer = (series?.bytes_by_server ?? []).map((row) => ({
    server: row.server,
    [bytesLabel]: row.bytes,
  }));

  return (
    <div
      className="flex flex-col gap-4 pt-4"
      data-testid="mcp-gateway-overview"
    >
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
        <Stat label={t("stats.total")} value={String(stats.total_calls)} />
        <Stat
          label={t("stats.hitRate")}
          value={formatPercent(stats.hit_rate)}
        />
        <Stat label={t("stats.billed")} value={String(stats.upstream_billed)} />
        <Stat label={t("stats.saved")} value={String(stats.saved_calls)} />
        <Stat
          label={t("storage.stored")}
          value={formatBytes(stats.blob_total_bytes)}
        />
        <Stat label={t("stats.hits")} value={String(stats.cache_hits)} />
      </div>

      <ChartCard title={charts("callsByOutcome")}>
        <AreaChart
          className="h-[220px]"
          data={remapCategories(
            series?.calls_by_outcome ?? [],
            "day",
            outcomeLabels
          )}
          index="day"
          categories={Object.values(outcomeLabels)}
          colors={SERIES_COLORS}
          stacked
          xAxisFormatter={formatCalendarDay}
        />
      </ChartCard>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <ChartCard title={charts("latency")}>
          <AreaChart
            className="h-[220px]"
            data={remapCategories(series?.latency ?? [], "day", latencyLabels)}
            index="day"
            categories={Object.values(latencyLabels)}
            xAxisFormatter={formatCalendarDay}
          />
        </ChartCard>
        <ChartCard title={charts("billedVsSaved")}>
          <AreaChart
            className="h-[220px]"
            data={remapCategories(
              series?.billed_vs_saved ?? [],
              "day",
              billedLabels
            )}
            index="day"
            categories={Object.values(billedLabels)}
            xAxisFormatter={formatCalendarDay}
          />
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <ChartCard title={charts("topServers")}>
          <BarChart
            data={topServers}
            index="server"
            categories={[countLabel]}
          />
        </ChartCard>
        <ChartCard title={charts("topTools")}>
          <BarChart data={topTools} index="tool" categories={[countLabel]} />
        </ChartCard>
      </div>

      <ChartCard title={charts("bytesByServer")}>
        <BarChart
          data={bytesByServer}
          index="server"
          categories={[bytesLabel]}
          yAxisFormatter={(value) => formatBytes(value)}
        />
      </ChartCard>
    </div>
  );
}
