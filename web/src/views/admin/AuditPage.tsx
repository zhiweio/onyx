"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Button, Card, Text } from "@opal/components";
import { SettingsLayouts, toast } from "@opal/layouts";
import { useAdminRouteTitle } from "@/lib/adminNavLabels";
import { ADMIN_ROUTES } from "@/lib/admin-routes";

interface ToolCall {
  id: number;
  user: string;
  tool: string;
  ok: boolean;
  result_excerpt: string;
  duration_ms: number | null;
  created_at: string;
}

interface ToolStat {
  tool: string;
  calls: number;
  failures: number;
  avg_ms: number | null;
}

interface ApprovalRow {
  id: string;
  app_name: string;
  decision: string | null;
  created_at: string;
}

interface QuarantineRow {
  id: string;
  url_hash: string;
  verdict: string;
  decision: string;
  created_at: string;
}

interface UsageSummary {
  days: number;
  search_queries: number;
  active_users: number;
  tool_calls: number;
}

interface QueryHistoryRow {
  user: string;
  query: string;
  created_at: string;
}

async function api<T>(path: string): Promise<T> {
  const resp = await fetch(path);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json() as Promise<T>;
}

type Tab = "tools" | "approvals" | "quarantines" | "usage" | "history";

const TABS: Tab[] = ["tools", "approvals", "quarantines", "usage", "history"];

export default function AuditPage() {
  const t = useTranslations("admin.audit");
  const adminRouteTitle = useAdminRouteTitle();
  const route = ADMIN_ROUTES.AUDIT;
  const [tab, setTab] = useState<Tab>("tools");
  const [days, setDays] = useState(7);

  const [toolCalls, setToolCalls] = useState<ToolCall[]>([]);
  const [toolStats, setToolStats] = useState<ToolStat[]>([]);
  const [approvals, setApprovals] = useState<ApprovalRow[]>([]);
  const [quarantines, setQuarantines] = useState<QuarantineRow[]>([]);
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [history, setHistory] = useState<QueryHistoryRow[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const start = new Date(Date.now() - days * 86400_000).toISOString();
      if (tab === "tools") {
        const data = await api<{ calls: ToolCall[]; stats: ToolStat[] }>(
          `/api/admin/audit/tool-calls?start=${encodeURIComponent(start)}&limit=200`
        );
        setToolCalls(data.calls);
        setToolStats(data.stats);
      } else if (tab === "approvals") {
        setApprovals(
          await api<ApprovalRow[]>(
            `/api/admin/audit/approvals?start=${encodeURIComponent(start)}`
          )
        );
      } else if (tab === "quarantines") {
        setQuarantines(
          await api<QuarantineRow[]>(
            `/api/admin/audit/quarantines?start=${encodeURIComponent(start)}`
          )
        );
      } else if (tab === "usage") {
        setUsage(await api<UsageSummary>(`/api/admin/audit/usage?days=${days}`));
      } else {
        const data = await api<{ queries: QueryHistoryRow[] }>(
          `/api/admin/audit/query-history?start=${encodeURIComponent(start)}&limit=200`
        );
        setHistory(data.queries);
      }
    } catch (err) {
      toast.error(String(err));
    } finally {
      setLoading(false);
    }
  }, [tab, days]);

  useEffect(() => {
    void load();
  }, [load]);

  const exportCsv = () => {
    const rows: string[][] =
      tab === "tools"
        ? [["time", "user", "tool", "ok", "ms"], ...toolCalls.map((c) => [c.created_at, c.user, c.tool, String(c.ok), String(c.duration_ms ?? "")])]
        : tab === "history"
          ? [["time", "user", "query"], ...history.map((h) => [h.created_at, h.user, h.query.replace(/[",\n]/g, " ")])]
          : [["time", "key"], ...approvals.map((a) => [a.created_at, `${a.app_name}:${a.decision ?? "pending"}`])];
    const csv = rows.map((r) => r.join(",")).join("\n");
    const url = URL.createObjectURL(new Blob(["\uFEFF" + csv], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `audit-${tab}-${days}d.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={route.icon}
        title={adminRouteTitle(route)}
        divider
      />
      <SettingsLayouts.Body>
        <div className="mb-2 flex flex-wrap items-center gap-1">
          {TABS.map((item) => (
            <Button
              key={item}
              size="xs"
              prominence={item === tab ? "primary" : "tertiary"}
              onClick={() => setTab(item)}
            >
              {t(`tabs.${item}`)}
            </Button>
          ))}
          <span className="ml-2 flex items-center gap-1">
            {[7, 30, 90].map((d) => (
              <Button
                key={d}
                size="xs"
                prominence={d === days ? "primary" : "tertiary"}
                onClick={() => setDays(d)}
              >
                {d}d
              </Button>
            ))}
          </span>
          <span className="ml-auto flex gap-1">
            <Button size="xs" prominence="tertiary" onClick={() => void load()} disabled={loading}>
              {t("refresh")}
            </Button>
            <Button size="xs" prominence="tertiary" onClick={exportCsv}>
              {t("export")}
            </Button>
          </span>
        </div>

        {tab === "tools" && (
          <>
            <Card className="mb-2 p-3">
              <Text font="main-ui-body">{t("stats")}</Text>
              <div className="mt-1 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-text-03">
                      <th className="p-2">{t("col.tool")}</th>
                      <th className="p-2">{t("col.calls")}</th>
                      <th className="p-2">{t("col.failures")}</th>
                      <th className="p-2">{t("col.avgMs")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {toolStats.map((s) => (
                      <tr key={s.tool} className="border-t border-border-01">
                        <td className="p-2">{s.tool}</td>
                        <td className="p-2">{s.calls}</td>
                        <td className={`p-2 ${s.failures > 0 ? "text-status-error-05" : ""}`}>
                          {s.failures}
                        </td>
                        <td className="p-2">{s.avg_ms ?? "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
            <Card className="p-3">
              <Text font="main-ui-body">{t("calls")}</Text>
              <div className="mt-1 max-h-96 overflow-auto">
                <table className="w-full text-sm">
                  <tbody>
                    {toolCalls.map((c) => (
                      <tr key={c.id} className="border-t border-border-01">
                        <td className="p-2 text-text-03">{new Date(c.created_at).toLocaleString()}</td>
                        <td className="p-2">{c.user}</td>
                        <td className="p-2 font-medium">{c.tool}</td>
                        <td className={`p-2 ${c.ok ? "text-status-success-05" : "text-status-error-05"}`}>
                          {c.ok ? "OK" : "FAIL"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </>
        )}

        {tab === "approvals" && (
          <Card className="p-3">
            <div className="max-h-[32rem] overflow-auto">
              <table className="w-full text-sm">
                <tbody>
                  {approvals.map((a) => (
                    <tr key={a.id} className="border-t border-border-01">
                      <td className="p-2 text-text-03">{new Date(a.created_at).toLocaleString()}</td>
                      <td className="p-2 font-medium">{a.app_name}</td>
                      <td className="p-2">{a.decision ?? t("pending")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        )}

        {tab === "quarantines" && (
          <Card className="p-3">
            <div className="max-h-[32rem] overflow-auto">
              <table className="w-full text-sm">
                <tbody>
                  {quarantines.map((q) => (
                    <tr key={q.id} className="border-t border-border-01">
                      <td className="p-2 text-text-03">{new Date(q.created_at).toLocaleString()}</td>
                      <td className="p-2 font-mono text-xs">{q.url_hash.slice(0, 12)}</td>
                      <td className="p-2">{q.verdict}</td>
                      <td className="p-2">{q.decision}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        )}

        {tab === "usage" && usage && (
          <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
            <Card className="p-4">
              <Text font="main-ui-body">{t("usage.queries")}</Text>
              <Text font="main-ui-title" className="mt-1">
                {usage.search_queries.toLocaleString()}
              </Text>
            </Card>
            <Card className="p-4">
              <Text font="main-ui-body">{t("usage.users")}</Text>
              <Text font="main-ui-title" className="mt-1">
                {usage.active_users.toLocaleString()}
              </Text>
            </Card>
            <Card className="p-4">
              <Text font="main-ui-body">{t("usage.toolCalls")}</Text>
              <Text font="main-ui-title" className="mt-1">
                {usage.tool_calls.toLocaleString()}
              </Text>
            </Card>
          </div>
        )}

        {tab === "history" && (
          <Card className="p-3">
            <div className="max-h-[32rem] overflow-auto">
              <table className="w-full text-sm">
                <tbody>
                  {history.map((h, i) => (
                    <tr key={i} className="border-t border-border-01">
                      <td className="p-2 text-text-03">{new Date(h.created_at).toLocaleString()}</td>
                      <td className="p-2">{h.user}</td>
                      <td className="p-2">{h.query}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        )}
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
