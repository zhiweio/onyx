"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import useSWR from "swr";
import { Button, Card, Tabs, Text } from "@opal/components";
import { SettingsLayouts } from "@opal/layouts";
import { useAdminRouteTitle } from "@/lib/adminNavLabels";
import { ADMIN_ROUTES } from "@/lib/admin-routes";
import {
  DateRangePicker,
  rangeForInclusiveDays,
  type DateRange,
} from "@/refresh-components/DateRangePicker";
import { isoWindowForInclusiveDateRange } from "@/lib/dateWindow";
import ToolCallsTab from "./ToolCallsTab";
import { ApprovalsTab, QuarantinesTab, QueryHistoryTab } from "./RecordTables";
import {
  fetchAuditUsage,
  type AuditUsageSummary,
  type AuditWindow,
} from "./api";

type AuditTab = "tools" | "approvals" | "quarantines" | "usage" | "history";

const TABS: AuditTab[] = [
  "tools",
  "approvals",
  "quarantines",
  "usage",
  "history",
];

function UsageCards({ days }: { days: number }) {
  const t = useTranslations("admin.audit");
  const { data, isLoading, error } = useSWR<AuditUsageSummary>(
    ["audit-usage", days],
    () => fetchAuditUsage(days)
  );

  if (error) {
    return (
      <Card padding={4} rounding={3}>
        <Text font="secondary-body" color="text-03">
          {t("loadFailed")}
        </Text>
      </Card>
    );
  }

  const cards = [
    { key: "queries", label: t("usage.queries"), value: data?.search_queries },
    { key: "users", label: t("usage.users"), value: data?.active_users },
    { key: "toolCalls", label: t("usage.toolCalls"), value: data?.tool_calls },
  ];

  return (
    <div className="grid grid-cols-1 gap-3 pt-4 md:grid-cols-3">
      {cards.map((card) => (
        <Card key={card.key} padding={4} rounding={3}>
          <Text font="main-ui-body">{card.label}</Text>
          <Text font="main-ui-title" className="mt-1">
            {isLoading ? "-" : (card.value ?? 0).toLocaleString()}
          </Text>
        </Card>
      ))}
    </div>
  );
}

export default function AuditPage() {
  const t = useTranslations("admin.audit");
  const adminRouteTitle = useAdminRouteTitle();
  const route = ADMIN_ROUTES.AUDIT;
  const [tab, setTab] = useState<AuditTab>("tools");
  const [dateRange, setDateRange] = useState<NonNullable<DateRange>>(
    rangeForInclusiveDays(7)
  );
  const [refreshKey, setRefreshKey] = useState(0);

  // The picker emits undefined when the user clears the range; fall back to
  // the default window instead of rendering without a time filter.
  const activeRange = dateRange ?? rangeForInclusiveDays(7);
  const isoWindow = isoWindowForInclusiveDateRange(activeRange);
  const auditWindow: AuditWindow = {
    start: isoWindow.from,
    end: isoWindow.to,
  };
  const inclusiveDays =
    Math.round(
      (activeRange.to.getTime() - activeRange.from.getTime()) / 86400000
    ) + 1;

  return (
    <SettingsLayouts.Root width="lg" data-testid="audit-page">
      <SettingsLayouts.Header
        icon={route.icon}
        title={adminRouteTitle(route)}
        divider
      />
      <SettingsLayouts.Body>
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div className="flex flex-col gap-1.5">
              <Text as="p" font="secondary-body" color="text-03">
                {t("filter.time")}
              </Text>
              <DateRangePicker
                value={dateRange}
                onValueChange={(value) =>
                  setDateRange(value ?? rangeForInclusiveDays(7))
                }
                size="md"
                className="h-[42px] items-center rounded-08 border border-border-01 bg-background-neutral-00"
              />
            </div>
            <Button
              prominence="secondary"
              data-testid="audit-refresh"
              onClick={() => setRefreshKey((value) => value + 1)}
            >
              {t("refresh")}
            </Button>
          </div>

          <Tabs
            value={tab}
            onValueChange={(value) => setTab(value as AuditTab)}
          >
            <Tabs.List>
              {TABS.map((item) => (
                <Tabs.Trigger
                  key={item}
                  value={item}
                  data-testid={`audit-tab-${item}`}
                >
                  {t(`tabs.${item}`)}
                </Tabs.Trigger>
              ))}
            </Tabs.List>
            <Tabs.Content value="tools">
              {tab === "tools" ? (
                <ToolCallsTab key={`tools-${refreshKey}`} window={auditWindow} />
              ) : null}
            </Tabs.Content>
            <Tabs.Content value="approvals">
              {tab === "approvals" ? (
                <ApprovalsTab
                  key={`approvals-${refreshKey}`}
                  window={auditWindow}
                />
              ) : null}
            </Tabs.Content>
            <Tabs.Content value="quarantines">
              {tab === "quarantines" ? (
                <QuarantinesTab
                  key={`quarantines-${refreshKey}`}
                  window={auditWindow}
                />
              ) : null}
            </Tabs.Content>
            <Tabs.Content value="usage">
              {tab === "usage" ? (
                <UsageCards key={`usage-${refreshKey}`} days={inclusiveDays} />
              ) : null}
            </Tabs.Content>
            <Tabs.Content value="history">
              {tab === "history" ? (
                <QueryHistoryTab
                  key={`history-${refreshKey}`}
                  window={auditWindow}
                />
              ) : null}
            </Tabs.Content>
          </Tabs>
        </div>
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
