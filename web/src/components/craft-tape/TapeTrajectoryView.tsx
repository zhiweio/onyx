"use client";

/**
 * Trajectory view — the dsh TrajectoryView pattern ported to tapes: a
 * toolbar (turn chip, kind filter, search with match highlighting,
 * collapse-all), collapsible per-turn sections, and an event ledger where
 * each row is a status dot, the subtype badge, a one-line payload summary,
 * and expandable raw JSON. Consecutive delta chunks collapse into run rows
 * (dsh shows request-level nodes, not every token).
 */

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import {
  Button,
  InputTypeIn,
  Popover,
  PopoverMenu,
  Tag,
  Tooltip,
} from "@opal/components";
import { SvgChevronRight, SvgFilter, SvgX } from "@opal/icons";
import { cn } from "@opal/utils";
import { humanReadableFormatWithTime } from "@opal/time";
import { JsonBlock } from "@/components/admin/JsonBlock";
import type { TapeEventItem, TapeTurnItem } from "@/lib/craft-tape/types";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { formatDuration, formatTokenCount } from "./constants";
import { isDeltaEvent, summarizeEvent } from "./eventSummary";
import { relativeTimeFromIso } from "./relativeTime";
import ReasonTag from "./ReasonTag";
import { turnTapeStatus } from "./tapeStatus";
import TapeStatusDot from "./TapeStatusDot";
import { useTickingNow } from "./useTickingNow";

type KindFilter = "all" | "harness_message" | "context_event";

type LedgerRow =
  | { type: "event"; event: TapeEventItem }
  | {
      type: "deltaRun";
      first: TapeEventItem;
      last: TapeEventItem;
      count: number;
      chars: number;
    };

interface TrajectorySection {
  key: string;
  turn: TapeTurnItem | null;
  rows: LedgerRow[];
}

export default function TapeTrajectoryView({
  turns,
  events,
  loading,
  nextSourceId,
  onLoadMore,
  turnFilter,
  onTurnFilterChange,
}: {
  turns: TapeTurnItem[];
  events: TapeEventItem[];
  loading: boolean;
  nextSourceId: number | null;
  onLoadMore: () => void;
  turnFilter: number | null;
  onTurnFilterChange: (turn: number | null) => void;
}) {
  const t = useTranslations("craftTape");
  const now = useTickingNow();

  const [queryInput, setQueryInput] = useState("");
  const query = useDebouncedValue(queryInput.trim().toLowerCase(), 250);
  const [kindFilter, setKindFilter] = useState<KindFilter>("all");
  const [collapsedTurns, setCollapsedTurns] = useState<Set<number>>(
    () => new Set()
  );

  const sections = useMemo(
    () => buildSections(turns, events, turnFilter, kindFilter, query),
    [turns, events, turnFilter, kindFilter, query]
  );

  const allCollapsed =
    turns.length > 0 &&
    turns.every((turn) => collapsedTurns.has(turn.turn_index));

  const toggleCollapseAll = () => {
    setCollapsedTurns(
      allCollapsed ? new Set() : new Set(turns.map((turn) => turn.turn_index))
    );
  };

  const empty = sections.every((section) => section.rows.length === 0);

  return (
    <div className="flex min-h-0 flex-col" data-testid="tape-trajectory-view">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2 px-1 pb-2">
        {turnFilter !== null ? (
          <button
            type="button"
            className="flex h-7 flex-none items-center gap-1 rounded-md bg-neutral-200/70 px-2 text-xs text-neutral-900 hover:bg-neutral-200 dark:bg-neutral-700/60 dark:text-neutral-100 dark:hover:bg-neutral-700"
            onClick={() => onTurnFilterChange(null)}
            data-testid="tape-trajectory-turn-chip"
          >
            {t("turns.turnOf", { turn: turnFilter })}
            <SvgX className="h-3 w-3" />
          </button>
        ) : null}
        <div className="w-44">
          <InputTypeIn
            searchIcon
            value={queryInput}
            onChange={(event) => setQueryInput(event.target.value)}
            placeholder={t("trajectory.search")}
            aria-label={t("trajectory.search")}
            data-testid="tape-trajectory-search"
          />
        </div>
        <Popover>
          <Popover.Trigger asChild>
            <button
              type="button"
              className="flex h-7 flex-none items-center gap-1.5 rounded-md border border-neutral-300 px-2 text-xs text-neutral-600 hover:bg-neutral-100 dark:border-neutral-600 dark:text-neutral-300 dark:hover:bg-neutral-800"
              data-testid="tape-trajectory-kind"
              aria-label={t("trajectory.kind")}
            >
              <SvgFilter className="h-3.5 w-3.5" />
              {kindFilter === "all"
                ? t("trajectory.kindAll")
                : kindFilter === "context_event"
                  ? t("trajectory.kindContext")
                  : t("trajectory.kindHarness")}
            </button>
          </Popover.Trigger>
          <Popover.Content align="start" width="sm">
            <PopoverMenu>
              {(
                [
                  ["all", t("trajectory.kindAll")],
                  ["harness_message", t("trajectory.kindHarness")],
                  ["context_event", t("trajectory.kindContext")],
                ] as const
              ).map(([value, label]) => (
                <MenuCheckRow
                  key={value}
                  active={kindFilter === value}
                  label={label}
                  onClick={() => setKindFilter(value)}
                />
              ))}
            </PopoverMenu>
          </Popover.Content>
        </Popover>
        {turns.length > 0 ? (
          <button
            type="button"
            className="ml-auto text-xs text-neutral-500 hover:text-neutral-900 dark:hover:text-neutral-100"
            onClick={toggleCollapseAll}
            data-testid="tape-trajectory-collapse-all"
          >
            {allCollapsed
              ? t("trajectory.expandAll")
              : t("trajectory.collapseAll")}
          </button>
        ) : null}
      </div>

      {/* Ledger */}
      <div
        className="flex max-h-[36rem] min-h-0 flex-col gap-2 overflow-y-auto pr-1"
        data-testid="tape-trajectory-ledger"
      >
        {loading ? (
          <div className="px-1 py-6 text-sm text-neutral-500">
            {t("table.loading")}
          </div>
        ) : empty ? (
          <div className="px-1 py-6 text-sm text-neutral-500">
            {events.length === 0 ? t("events.empty") : t("trajectory.empty")}
          </div>
        ) : (
          sections
            .filter((section) => section.rows.length > 0)
            .map((section) => (
              <TurnSection
                key={section.key}
                section={section}
                collapsed={
                  section.turn !== null &&
                  collapsedTurns.has(section.turn.turn_index)
                }
                query={query}
                now={now}
                onToggle={() => {
                  const turn = section.turn;
                  if (turn === null) return;
                  setCollapsedTurns((current) => {
                    const next = new Set(current);
                    if (next.has(turn.turn_index)) {
                      next.delete(turn.turn_index);
                    } else {
                      next.add(turn.turn_index);
                    }
                    return next;
                  });
                }}
              />
            ))
        )}

        {nextSourceId !== null && !loading ? (
          <div className="pb-1">
            <Button prominence="secondary" onClick={onLoadMore}>
              {t("events.loadMore")}
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Turn section
// ---------------------------------------------------------------------------

function TurnSection({
  section,
  collapsed,
  query,
  now,
  onToggle,
}: {
  section: TrajectorySection;
  collapsed: boolean;
  query: string;
  now: number;
  onToggle: () => void;
}) {
  const t = useTranslations("craftTape");
  const turn = section.turn;
  return (
    <div
      className="rounded-lg border border-neutral-200 dark:border-neutral-700"
      data-testid={
        turn
          ? `tape-trajectory-turn-${turn.turn_index}`
          : "tape-trajectory-ungrouped"
      }
    >
      {turn ? (
        <button
          type="button"
          className="flex w-full flex-wrap items-center gap-2 rounded-t-lg px-3 py-2 text-left hover:bg-neutral-50 dark:hover:bg-neutral-800/60"
          onClick={onToggle}
          aria-expanded={!collapsed}
        >
          <SvgChevronRight
            className={cn(
              "h-3.5 w-3.5 flex-none text-neutral-400 transition-transform",
              !collapsed && "rotate-90"
            )}
          />
          <TapeStatusDot status={turnTapeStatus(turn)} />
          <span className="text-xs font-medium">
            {t("turns.turn")} #{turn.turn_index}
          </span>
          <span className="truncate font-mono text-xs text-neutral-500 dark:text-neutral-400">
            {turn.model ?? "—"}
          </span>
          <span className="text-xs text-neutral-400">
            {formatDuration(turn.started_at, turn.ended_at) ?? "—"}
          </span>
          {turn.turn_end_reason === null ? (
            <Tag title={t("status.running")} color="amber" />
          ) : (
            <ReasonTag reason={turn.turn_end_reason} />
          )}
          <span className="ml-auto text-xs text-neutral-400">
            {formatTokenCount(turn.output_tokens)} tok
          </span>
        </button>
      ) : (
        <div className="px-3 py-2 text-xs font-medium text-neutral-500 dark:text-neutral-400">
          {t("turns.ungrouped")}
        </div>
      )}

      {!collapsed ? (
        <div className="flex flex-col gap-0.5 border-t border-neutral-100 px-1 py-1 dark:border-neutral-800">
          {turn?.error_detail ? (
            <div className="px-2 pb-1 text-xs text-red-600 dark:text-red-400">
              {turn.error_detail}
            </div>
          ) : null}
          {section.rows.map((row) =>
            row.type === "event" ? (
              <EventLedgerRow
                key={row.event.source_id}
                event={row.event}
                query={query}
                now={now}
              />
            ) : (
              <DeltaRunRow key={`delta-${row.first.source_id}`} row={row} />
            )
          )}
        </div>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Ledger rows
// ---------------------------------------------------------------------------

function EventLedgerRow({
  event,
  query,
  now,
}: {
  event: TapeEventItem;
  query: string;
  now: number;
}) {
  const t = useTranslations("craftTape");
  const [expanded, setExpanded] = useState(false);
  const summary = useMemo(() => summarizeEvent(event), [event]);
  const paired = event.annotations.some(
    (annotation) =>
      annotation.startsWith("call:") || annotation.startsWith("result:")
  );
  const interrupted = event.annotations.includes("interrupted");
  const bucket = relativeTimeFromIso(event.created_at, now);

  return (
    <div
      className="rounded-md px-2 py-1.5 hover:bg-neutral-50 dark:hover:bg-neutral-800/60"
      data-testid={`craft-tape-event-${event.source_id}`}
    >
      <div className="flex items-center gap-2">
        <Tooltip
          tooltip={paired ? t("trajectory.paired") : undefined}
          side="top"
          delayDuration={300}
        >
          <span
            className={cn(
              "h-1.5 w-1.5 flex-none rounded-full",
              paired ? "bg-blue-500" : "bg-neutral-300 dark:bg-neutral-600"
            )}
          />
        </Tooltip>
        <span className="flex-none font-mono text-[10px] text-neutral-400">
          #{event.source_id}
        </span>
        <span className="truncate font-mono text-xs text-neutral-700 dark:text-neutral-300">
          <Highlight text={event.subtype} query={query} />
        </span>
        {event.kind === "context_event" ? (
          <Tag title={t("trajectory.context")} color="blue" />
        ) : null}
        {interrupted ? (
          <Tag title={t("reasons.interrupted")} color="amber" />
        ) : null}
        <span className="ml-auto flex flex-none items-center gap-1">
          <Tooltip
            tooltip={humanReadableFormatWithTime(event.created_at)}
            side="top"
            delayDuration={300}
          >
            <span className="text-[10px] text-neutral-400">
              {bucket === null
                ? "—"
                : bucket.unit === "now"
                  ? t("time.now")
                  : t(`time.${bucket.unit}`, { n: bucket.n })}
            </span>
          </Tooltip>
          <button
            type="button"
            className="flex h-5 w-5 items-center justify-center rounded text-neutral-400 hover:text-neutral-900 dark:hover:text-neutral-100"
            aria-label={
              expanded ? t("events.hidePayload") : t("events.showPayload")
            }
            onClick={() => setExpanded((value) => !value)}
            data-testid={`craft-tape-event-toggle-${event.source_id}`}
          >
            <SvgChevronRight
              className={cn(
                "h-3 w-3 transition-transform",
                expanded && "rotate-90"
              )}
            />
          </button>
        </span>
      </div>
      {summary ? (
        <div className="truncate pl-5 pt-0.5 text-xs text-neutral-500 dark:text-neutral-400">
          <Highlight text={summary} query={query} />
        </div>
      ) : null}
      {expanded ? (
        <div className="pl-5 pt-1">
          <JsonBlock value={event.payload} />
        </div>
      ) : null}
    </div>
  );
}

function DeltaRunRow({
  row,
}: {
  row: Extract<LedgerRow, { type: "deltaRun" }>;
}) {
  const t = useTranslations("craftTape");
  return (
    <div
      className="flex items-center gap-2 rounded-md px-2 py-1 text-xs text-neutral-400"
      data-testid={`craft-tape-delta-run-${row.first.source_id}`}
    >
      <span className="h-1.5 w-1.5 flex-none rounded-full bg-neutral-200 dark:bg-neutral-700" />
      <span className="flex-none font-mono text-[10px]">
        #{row.first.source_id}–#{row.last.source_id}
      </span>
      <span>
        {t("trajectory.deltaRun", {
          count: row.count,
          chars: row.chars.toLocaleString(),
        })}
      </span>
    </div>
  );
}

function Highlight({
  text,
  query,
}: {
  text: string;
  query: string;
}): React.ReactNode {
  if (!query) return text;
  const lower = text.toLowerCase();
  const parts: React.ReactNode[] = [];
  let cursor = 0;
  let index = lower.indexOf(query);
  let key = 0;
  while (index !== -1) {
    if (index > cursor) parts.push(text.slice(cursor, index));
    parts.push(
      <mark
        key={key}
        className="rounded-sm bg-amber-200/70 text-inherit dark:bg-amber-500/30"
      >
        {text.slice(index, index + query.length)}
      </mark>
    );
    key += 1;
    cursor = index + query.length;
    index = lower.indexOf(query, cursor);
  }
  if (cursor < text.length) parts.push(text.slice(cursor));
  return parts;
}

function MenuCheckRow({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      role="menuitemradio"
      aria-checked={active}
      className="flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-neutral-100 dark:hover:bg-neutral-800"
    >
      <span className="truncate">{label}</span>
      {active ? (
        <span className="text-xs text-neutral-900 dark:text-neutral-100">
          ✓
        </span>
      ) : null}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Section building: filter → match → collapse delta runs → group by turn
// ---------------------------------------------------------------------------

function matches(
  event: TapeEventItem,
  query: string,
  summary: string
): boolean {
  if (!query) return true;
  const haystack =
    `${event.subtype}\n${summary}\n${JSON.stringify(event.payload)}`.toLowerCase();
  return haystack.includes(query);
}

function buildSections(
  turns: TapeTurnItem[],
  events: TapeEventItem[],
  turnFilter: number | null,
  kindFilter: KindFilter,
  query: string
): TrajectorySection[] {
  const summaries = new Map<number, string>();
  const filtered = events.filter((event) => {
    if (kindFilter !== "all" && event.kind !== kindFilter) return false;
    const summary = summarizeEvent(event) ?? "";
    summaries.set(event.source_id, summary);
    return matches(event, query, summary);
  });

  const scoped =
    turnFilter === null
      ? filtered
      : filtered.filter((event) => event.turn_index === turnFilter);

  const rows = collapseDeltaRuns(scoped);

  if (turnFilter !== null) {
    const turn = turns.find((item) => item.turn_index === turnFilter) ?? null;
    return [{ key: `turn:${turnFilter}`, turn, rows }];
  }

  const byTurn = new Map<string, LedgerRow[]>();
  for (const row of rows) {
    const event = row.type === "event" ? row.event : row.first;
    const key =
      event.turn_index === null ? "ungrouped" : `turn:${event.turn_index}`;
    const bucket = byTurn.get(key);
    if (bucket) bucket.push(row);
    else byTurn.set(key, [row]);
  }

  const sections: TrajectorySection[] = [];
  const ungrouped = byTurn.get("ungrouped");
  if (ungrouped) {
    sections.push({ key: "ungrouped", turn: null, rows: ungrouped });
  }
  for (const turn of turns) {
    const key = `turn:${turn.turn_index}`;
    const bucket = byTurn.get(key);
    if (bucket) {
      sections.push({ key, turn, rows: bucket });
    }
  }
  // Turns the API knows but whose events are still behind the cursor keep
  // their (empty) section so the outline matches the turn rail.
  return sections;
}

function collapseDeltaRuns(events: TapeEventItem[]): LedgerRow[] {
  const rows: LedgerRow[] = [];
  let run: TapeEventItem[] = [];
  const flush = () => {
    const first = run[0];
    const last = run[run.length - 1];
    if (first === undefined || last === undefined) {
      run = [];
      return;
    }
    const chars = run.reduce((sum, event) => sum + deltaLength(event), 0);
    rows.push({
      type: "deltaRun",
      first,
      last,
      count: run.length,
      chars,
    });
    run = [];
  };
  for (const event of events) {
    if (isDeltaEvent(event)) {
      run.push(event);
      continue;
    }
    flush();
    rows.push({ type: "event", event });
  }
  flush();
  return rows;
}

function deltaLength(event: TapeEventItem): number {
  const props = event.payload.properties;
  if (
    typeof props === "object" &&
    props !== null &&
    typeof (props as Record<string, unknown>).delta === "string"
  ) {
    return ((props as Record<string, unknown>).delta as string).length;
  }
  return 0;
}
