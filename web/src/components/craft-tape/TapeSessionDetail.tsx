"use client";

/**
 * Shared tape session detail — the dsh conversation surface ported to tapes:
 * a status-dot header with meta and actions (export, copy link, close), a
 * trajectory/replay view toggle (trajectory is the default because it renders
 * from the first event page; the replay player mounts only when its tab
 * opens), and the turn rail scoping both views to one turn. Used by the admin
 * and personal entries; the variant only selects which API base serves data.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { Button, Tabs } from "@opal/components";
import { toast } from "@opal/layouts";
import { SvgCopy, SvgDownload, SvgX } from "@opal/icons";
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
import { formatTokenCount, originKeyLabel, sessionTitle } from "./constants";
import { relativeTimeFromIso } from "./relativeTime";
import { sessionTapeStatus, turnTapeStatus } from "./tapeStatus";
import TapeReplayPlayer from "./TapeReplayPlayer";
import TapeStatusDot from "./TapeStatusDot";
import TapeTrajectoryView from "./TapeTrajectoryView";
import TapeTurnRail from "./TapeTurnRail";
import { useTickingNow } from "./useTickingNow";

export interface TapeSessionDetailProps {
  sessionId: string;
  /**
   * The list row for this session, when it has been seen — deep links open
   * before the list reaches the row, and the header degrades gracefully.
   */
  session: TapeSessionItem | null;
  /** "admin" reads every session; "personal" reads only the caller's own. */
  variant: "admin" | "personal";
  onClose: () => void;
}

export default function TapeSessionDetail({
  sessionId,
  session,
  variant,
  onClose,
}: TapeSessionDetailProps) {
  const t = useTranslations("craftTape");
  const now = useTickingNow();
  const isPersonal = variant === "personal";

  const [turns, setTurns] = useState<TapeTurnItem[]>([]);
  const [events, setEvents] = useState<TapeEventItem[]>([]);
  const [nextSourceId, setNextSourceId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [turnFilter, setTurnFilter] = useState<number | null>(null);
  const [isExporting, setIsExporting] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    // New selection: drop the previous session's data before refetching.
    setTurns([]);
    setEvents([]);
    setNextSourceId(null);
    setTurnFilter(null);
    setError(null);
    setLoading(true);
    let cancelled = false;
    const turnsLoader = isPersonal
      ? listMyTapeTurns(sessionId)
      : listTapeTurns(sessionId);
    const eventsLoader = isPersonal
      ? listMyTapeEvents(sessionId)
      : listTapeEvents(sessionId);
    Promise.all([turnsLoader, eventsLoader])
      .then(([turnList, eventList]) => {
        if (cancelled) return;
        setTurns(turnList.items);
        setEvents(eventList.items);
        setNextSourceId(eventList.next_source_id);
      })
      .catch((err) => {
        if (!cancelled) setError(err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, isPersonal, reloadKey]);

  const loadMoreEvents = useCallback(() => {
    if (nextSourceId === null) return;
    const loader = isPersonal
      ? listMyTapeEvents(sessionId, nextSourceId)
      : listTapeEvents(sessionId, nextSourceId);
    loader
      .then((page) => {
        setEvents((current) => [...current, ...page.items]);
        setNextSourceId(page.next_source_id);
      })
      .catch((err) => toast.error(errorMessage(err, t("loadFailed"))));
  }, [nextSourceId, sessionId, isPersonal, t]);

  const fetchReplay = useCallback(
    (id: string, args: { afterSourceId?: number | null }) =>
      isPersonal ? fetchMyTapeReplay(id, args) : fetchTapeReplay(id, args),
    [isPersonal]
  );

  const headerStatus = useMemo(() => {
    if (session) return sessionTapeStatus(session);
    const lastTurn = turns[turns.length - 1];
    return lastTurn ? turnTapeStatus(lastTurn) : ("idle" as const);
  }, [session, turns]);

  const title = session ? sessionTitle(session) : sessionId.slice(0, 8);
  const createdBucket = session
    ? relativeTimeFromIso(session.created_at, now)
    : null;
  const outputTokens = turns.reduce(
    (sum, turn) => sum + (turn.output_tokens ?? 0),
    0
  );
  const cost = turns.reduce((sum, turn) => sum + (turn.cost ?? 0), 0);
  const metaParts = [
    session?.user_email ?? session?.user_id ?? null,
    session?.origin ? originKeyLabel(session.origin, t) : null,
    session?.runtimes?.length ? session.runtimes.join(" / ") : null,
    createdBucket
      ? createdBucket.unit === "now"
        ? t("time.now")
        : t(`time.${createdBucket.unit}`, { n: createdBucket.n })
      : null,
  ].filter((part): part is string => part !== null);

  const copyLink = useCallback(() => {
    const url = `${window.location.origin}${window.location.pathname}?sessionId=${sessionId}`;
    navigator.clipboard
      .writeText(url)
      .then(() => toast.success(t("browser.linkCopied")))
      .catch(() => toast.error(t("browser.linkCopyFailed")));
  }, [sessionId, t]);

  if (error) {
    return (
      <div
        className="flex h-full flex-col items-center justify-center gap-2"
        data-testid="craft-tape-detail-error"
      >
        <span className="text-sm text-neutral-500">
          {errorMessage(error, t("loadFailed"))}
        </span>
        <Button
          prominence="secondary"
          onClick={() => setReloadKey((key) => key + 1)}
        >
          {t("browser.retry")}
        </Button>
      </div>
    );
  }

  return (
    <div
      className="flex h-full min-h-0 flex-col"
      data-testid="craft-tape-detail"
    >
      {/* Header */}
      <div className="flex items-start gap-2 px-1 pb-2">
        <span className="mt-1.5 flex-none">
          <TapeStatusDot status={headerStatus} />
        </span>
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="truncate text-base font-medium leading-6">
            {title}
          </span>
          <span className="truncate text-xs text-neutral-500 dark:text-neutral-400">
            {metaParts.join(" · ")}
          </span>
          <span className="truncate text-xs text-neutral-400">
            {t("detail.turns", { count: turns.length })}
            {" · "}
            {t("detail.tokens", { count: formatTokenCount(outputTokens) })}
            {" · "}
            {t("detail.cost", { cost: cost.toFixed(2) })}
          </span>
        </div>
        <div className="flex flex-none items-center gap-1">
          <Button
            prominence="secondary"
            icon={SvgDownload}
            disabled={isExporting}
            onClick={() => {
              setIsExporting(true);
              const exporter = isPersonal
                ? exportMyTapeSession(sessionId)
                : exportTapeSession(sessionId);
              exporter
                .catch((err) => toast.error(errorMessage(err, t("loadFailed"))))
                .finally(() => setIsExporting(false));
            }}
            data-testid="craft-tape-export"
          >
            {t("export")}
          </Button>
          <HeaderIconButton
            label={t("browser.copyLink")}
            onClick={copyLink}
            testId="craft-tape-copy-link"
          >
            <SvgCopy className="h-4 w-4" />
          </HeaderIconButton>
          <HeaderIconButton
            label={t("detail.close")}
            onClick={onClose}
            testId="craft-tape-close"
          >
            <SvgX className="h-4 w-4" />
          </HeaderIconButton>
        </div>
      </div>

      {/* Views: trajectory (default, cheap) and replay (lazy — the player
          drains the full packet timeline, so it loads only when opened). */}
      <div className="min-h-0 flex-1">
        <Tabs defaultValue="trajectory">
          <Tabs.List>
            <Tabs.Trigger value="trajectory" data-testid="tape-tab-trajectory">
              {t("trajectory.title")}
            </Tabs.Trigger>
            <Tabs.Trigger value="replay" data-testid="tape-tab-replay">
              {t("replay.title")}
            </Tabs.Trigger>
          </Tabs.List>
          <Tabs.Content value="trajectory">
            <div className="flex min-h-0 gap-1 pt-2">
              <div className="min-w-0 flex-1">
                <TapeTrajectoryView
                  turns={turns}
                  events={events}
                  loading={loading}
                  nextSourceId={nextSourceId}
                  onLoadMore={loadMoreEvents}
                  turnFilter={turnFilter}
                  onTurnFilterChange={setTurnFilter}
                />
              </div>
              <TapeTurnRail
                turns={turns}
                activeTurn={turnFilter}
                onSelectTurn={setTurnFilter}
              />
            </div>
          </Tabs.Content>
          <Tabs.Content value="replay">
            <div className="pt-2">
              <TapeReplayPlayer
                sessionId={sessionId}
                fetchReplay={fetchReplay}
              />
            </div>
          </Tabs.Content>
        </Tabs>
      </div>
    </div>
  );
}

function HeaderIconButton({
  label,
  testId,
  onClick,
  children,
}: {
  label: string;
  testId: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className="flex h-7 w-7 items-center justify-center rounded-md text-neutral-500 hover:bg-neutral-100 hover:text-neutral-900 dark:text-neutral-400 dark:hover:bg-neutral-800 dark:hover:text-neutral-100"
      data-testid={testId}
    >
      {children}
    </button>
  );
}
