"use client";

/**
 * Shared tape session detail: turn table + event timeline + cinematic
 * replay + JSONL export. Used by the admin entry (all users' sessions)
 * and the personal entry (own sessions only); the variant only selects
 * which API base serves the data — server-side authorization differs,
 * the rendering core is one component (dsh: one render path, many shells).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import {
  Button,
  Card,
  Table,
  Tabs,
  Tag,
  createTableColumns,
} from "@opal/components";
import { toast } from "@opal/layouts";
import { JsonBlock } from "@/components/admin/JsonBlock";
import { DateTimeCell, MetricCell } from "@/components/admin/TableCells";
import {
  exportMyTapeSession,
  exportTapeSession,
  fetchMyTapeReplay,
  fetchTapeReplay,
  listMyTapeEvents,
  listMyTapeTurns,
  listTapeEvents,
  listTapeTurns,
} from "@/lib/craft-tape/api";
import type {
  TapeEventItem,
  TapeSessionItem,
  TapeTurnItem,
} from "@/lib/craft-tape/types";
import { errorMessage } from "@/views/admin/McpGatewayPage/format";
import TapeReplayPlayer from "./TapeReplayPlayer";

const tc = createTableColumns<TapeTurnItem>();

const REASON_TAG_COLORS: Record<string, "green" | "red" | "amber" | "gray"> = {
  completed: "green",
  error: "red",
  aborted: "amber",
  interrupted: "amber",
  deadline_exceeded: "amber",
};

interface TapeSessionDetailProps {
  session: TapeSessionItem;
  /** "admin" reads every session; "personal" reads only the caller's own. */
  variant: "admin" | "personal";
}

function EventRow({
  event,
  pairedIds,
}: {
  event: TapeEventItem;
  pairedIds: Set<string>;
}) {
  const t = useTranslations("craftTape");
  const [expanded, setExpanded] = useState(false);
  const interrupted = event.annotations.includes("interrupted");
  const pairKeys = event.annotations
    .map((annotation) => annotation.split(":", 2)[1])
    .filter((id): id is string => id !== undefined);
  const paired = pairKeys.some((key) => pairedIds.has(key));

  return (
    <div
      className={`flex flex-col gap-1 rounded-md border p-2 ${
        paired
          ? "border-l-4 border-l-blue-400 dark:border-l-blue-500"
          : "border-l-4 border-l-transparent"
      } border-neutral-200 dark:border-neutral-700`}
      data-testid={`craft-tape-event-${event.source_id}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs text-neutral-500">
          #{event.source_id}
        </span>
        <Tag
          title={event.kind}
          color={event.kind === "context_event" ? "blue" : "gray"}
        />
        <span className="font-mono text-xs">{event.subtype}</span>
        {interrupted ? (
          <Tag title={t("reasons.interrupted")} color="amber" />
        ) : null}
        <span className="ml-auto text-xs text-neutral-500">
          {new Date(event.created_at).toLocaleString()}
        </span>
      </div>
      <button
        type="button"
        className="w-fit text-left text-xs text-neutral-500 underline"
        onClick={() => setExpanded((value) => !value)}
      >
        {expanded ? t("events.hidePayload") : t("events.showPayload")}
      </button>
      {expanded ? <JsonBlock value={event.payload} /> : null}
    </div>
  );
}

export default function TapeSessionDetail({
  session,
  variant,
}: TapeSessionDetailProps) {
  const t = useTranslations("craftTape");
  const isPersonal = variant === "personal";
  const [turns, setTurns] = useState<TapeTurnItem[]>([]);
  const [events, setEvents] = useState<TapeEventItem[]>([]);
  const [nextSourceId, setNextSourceId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [turnFilter, setTurnFilter] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const turnsLoader = isPersonal
      ? listMyTapeTurns(session.session_id)
      : listTapeTurns(session.session_id);
    const eventsLoader = isPersonal
      ? listMyTapeEvents(session.session_id)
      : listTapeEvents(session.session_id);
    Promise.all([turnsLoader, eventsLoader])
      .then(([turnList, eventList]) => {
        if (cancelled) return;
        setTurns(turnList.items);
        setEvents(eventList.items);
        setNextSourceId(eventList.next_source_id);
      })
      .catch((error) => toast.error(errorMessage(error, t("loadFailed"))))
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [session.session_id, isPersonal, t]);

  const loadMore = useCallback(() => {
    if (nextSourceId === null) return;
    const loader = isPersonal
      ? listMyTapeEvents(session.session_id, nextSourceId)
      : listTapeEvents(session.session_id, nextSourceId);
    loader
      .then((page) => {
        setEvents((current) => [...current, ...page.items]);
        setNextSourceId(page.next_source_id);
      })
      .catch((error) => toast.error(errorMessage(error, t("loadFailed"))));
  }, [nextSourceId, session.session_id, isPersonal, t]);

  const pairedIds = useMemo(() => {
    const settled = new Set<string>();
    for (const event of events) {
      for (const annotation of event.annotations) {
        const [kind, id] = annotation.split(":", 2);
        if ((kind === "result" || kind === "call") && id !== undefined) {
          settled.add(id);
        }
      }
    }
    return settled;
  }, [events]);

  const turnColumns = useMemo(
    () => [
      tc.column("turn_index", {
        header: t("turns.col.turn"),
        weight: 8,
        enableSorting: false,
        cell: (value) => <MetricCell value={`#${value}`} />,
      }),
      tc.column("runtime", {
        header: t("turns.col.runtime"),
        weight: 10,
        enableSorting: false,
        cell: (value) => <MetricCell value={value} />,
      }),
      tc.column("model", {
        header: t("turns.col.model"),
        weight: 16,
        enableSorting: false,
        cell: (value) => <MetricCell value={value ?? "—"} />,
      }),
      tc.column("started_at", {
        header: t("turns.col.started"),
        weight: 16,
        enableSorting: false,
        cell: (value) =>
          value ? <DateTimeCell value={value} /> : <span>—</span>,
      }),
      tc.column("event_count", {
        header: t("turns.col.events"),
        weight: 9,
        enableSorting: false,
        cell: (value) => <MetricCell value={String(value)} />,
      }),
      tc.column("output_tokens", {
        header: t("turns.col.tokens"),
        weight: 10,
        enableSorting: false,
        cell: (value) => (
          <MetricCell value={value === null ? "—" : value.toLocaleString()} />
        ),
      }),
      tc.column("turn_end_reason", {
        header: t("turns.col.reason"),
        weight: 12,
        enableSorting: false,
        cell: (value) =>
          value ? (
            <Tag title={value} color={REASON_TAG_COLORS[value] ?? "gray"} />
          ) : (
            <Tag title={t("reasons.interrupted")} color="amber" />
          ),
      }),
      tc.column("tier", {
        header: t("turns.col.tier"),
        weight: 10,
        enableSorting: false,
        cell: (value) => <MetricCell value={value} />,
      }),
    ],
    [t]
  );

  const visibleEvents =
    turnFilter === null
      ? events
      : events.filter((event) => event.turn_index === turnFilter);

  return (
    <Card padding={3} rounding={3} data-testid="craft-tape-detail">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex flex-col">
          <span className="font-medium">
            {session.name ?? session.session_id.slice(0, 8)}
          </span>
          <span className="text-xs text-neutral-500">
            {session.user_email ?? session.user_id ?? "—"} ·{" "}
            {session.origin ?? "—"}
          </span>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <Button
            prominence="secondary"
            disabled={isExporting}
            onClick={() => {
              setIsExporting(true);
              const exporter = isPersonal
                ? exportMyTapeSession(session.session_id)
                : exportTapeSession(session.session_id);
              exporter
                .catch((error) =>
                  toast.error(errorMessage(error, t("loadFailed")))
                )
                .finally(() => setIsExporting(false));
            }}
          >
            {t("export")}
          </Button>
        </div>
      </div>

      <div className="pt-4">
        <Table
          data={turns}
          columns={turnColumns}
          getRowId={(row) => String(row.turn_index)}
          pageSize={10}
          variant="rows"
          footer={{ units: t("table.footerUnits") }}
          onRowClick={(row) =>
            setTurnFilter((current) =>
              current === row.turn_index ? null : row.turn_index
            )
          }
          emptyState={
            <span className="text-sm text-neutral-500">
              {loading ? t("table.loading") : t("turns.empty")}
            </span>
          }
        />
      </div>

      <div className="pt-4">
        <Tabs defaultValue="timeline">
          <Tabs.List>
            <Tabs.Trigger value="timeline">{t("events.title")}</Tabs.Trigger>
            <Tabs.Trigger value="replay">{t("replay.title")}</Tabs.Trigger>
          </Tabs.List>
          <Tabs.Content value="timeline">
            <div className="flex flex-col gap-2 pt-2">
              {turnFilter !== null ? (
                <button
                  type="button"
                  className="w-fit text-xs underline"
                  onClick={() => setTurnFilter(null)}
                >
                  {t("events.clearTurnFilter", { turn: turnFilter })}
                </button>
              ) : null}
              <div className="flex max-h-[28rem] flex-col gap-1 overflow-y-auto pr-1">
                {visibleEvents.map((event) => (
                  <EventRow
                    key={event.source_id}
                    event={event}
                    pairedIds={pairedIds}
                  />
                ))}
                {visibleEvents.length === 0 && !loading ? (
                  <span className="text-sm text-neutral-500">
                    {t("events.empty")}
                  </span>
                ) : null}
              </div>
              {nextSourceId !== null ? (
                <div>
                  <Button prominence="secondary" onClick={loadMore}>
                    {t("events.loadMore")}
                  </Button>
                </div>
              ) : null}
            </div>
          </Tabs.Content>
          <Tabs.Content value="replay">
            <div className="pt-2">
              <TapeReplayPlayer
                sessionId={session.session_id}
                fetchReplay={isPersonal ? fetchMyTapeReplay : fetchTapeReplay}
              />
            </div>
          </Tabs.Content>
        </Tabs>
      </div>
    </Card>
  );
}
