"use client";

/**
 * Cinematic tape replay player (shared by the admin and personal entries).
 *
 * Deterministic replay: a cursor over the packet timeline, and the visible
 * state is always the pure fold of the prefix up to that cursor (dsh
 * loadThrough semantics — seeking re-folds from scratch). Each tick advances
 * the cursor by one entry; turn markers segment the fold the same way the
 * live stream does, and folded turns render through the craft `FoldRow`
 * model so replayed frames match live ones.
 *
 * The shell is dsh chat-view shaped: a centered column that follows the tail
 * while the reader sits at the bottom (with a return-to-bottom pill when they
 * scroll up), icon transport controls, and a popover speed menu.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { Button, Popover, PopoverMenu, Tag } from "@opal/components";
import { toast } from "@opal/layouts";
import {
  SvgChevronDown,
  SvgChevronLeft,
  SvgChevronRight,
  SvgPauseCircle,
  SvgPlayCircle,
} from "@opal/icons";
import { cn } from "@opal/utils";
import type { StreamItem } from "@/app/craft/types/displayTypes";
import { foldTurnStream, type FoldRow } from "@/lib/craft/foldTurnStream";
import type { ReplayPacketItem, ReplayPage } from "@/lib/craft-tape/types";
import { errorMessage } from "@/views/admin/McpGatewayPage/format";
import { applyReplayPacket } from "./packetPlayer";

const SPEEDS = [
  { label: "0.5x", ms: 400 },
  { label: "1x", ms: 200 },
  { label: "2x", ms: 100 },
  { label: "4x", ms: 40 },
] as const;

const MAX_REPLAY_ENTRIES = 5000;

/* The reader counts as "at the tail" while the viewport bottom is this close. */
const FOLLOW_TAIL_THRESHOLD_PX = 48;

interface TapeReplayPlayerProps {
  sessionId: string;
  fetchReplay: (
    sessionId: string,
    args: { afterSourceId?: number | null }
  ) => Promise<ReplayPage>;
}

interface TurnRender {
  turnIndex: number | null;
  items: StreamItem[];
  reason: string | null;
}

/** Pure fold of the entry prefix up to ``cursor`` (exclusive). */
function stateUpTo(
  entries: ReplayPacketItem[],
  cursor: number
): { committed: TurnRender[]; current: TurnRender | null } {
  const committed: TurnRender[] = [];
  let current: TurnRender | null = null;
  for (let i = 0; i < cursor && i < entries.length; i += 1) {
    const entry = entries[i];
    if (!entry) continue;
    if (entry.type === "marker") {
      if (entry.marker === "turn_start") {
        if (current) committed.push(current);
        current = { turnIndex: entry.turn_index, items: [], reason: null };
      } else if (entry.marker === "turn_end") {
        if (current) {
          current.reason = entry.reason;
          committed.push(current);
          current = null;
        }
      }
      continue;
    }
    if (!current) {
      // Packets before any turn marker (legacy tapes): one implicit turn.
      current = { turnIndex: null, items: [], reason: null };
    }
    current.items = applyReplayPacket(current.items, entry);
  }
  if (current) committed.push(current);
  return { committed, current: null };
}

function FoldRowView({ row }: { row: FoldRow }) {
  if (row.kind === "thought") {
    return (
      <details className="rounded-md border border-neutral-200 px-2 py-1 text-sm dark:border-neutral-700">
        <summary className="cursor-pointer text-neutral-500">
          {row.summary ?? row.content.slice(0, 80)}
        </summary>
        <pre className="whitespace-pre-wrap pt-1 text-xs">{row.content}</pre>
      </details>
    );
  }
  if (row.kind === "tools") {
    return (
      <div className="flex flex-col gap-1">
        {row.tools.map((tool) => (
          <div
            key={tool.id}
            className="rounded-md border border-neutral-200 px-2 py-1 text-xs dark:border-neutral-700"
          >
            <div className="flex items-center gap-2">
              <span className="font-medium">{tool.title}</span>
              <Tag
                title={tool.status}
                color={
                  tool.status === "completed"
                    ? "green"
                    : tool.status === "failed"
                      ? "red"
                      : "amber"
                }
              />
            </div>
            {tool.command ? (
              <pre className="overflow-x-auto pt-1 font-mono text-[11px] text-neutral-500">
                {tool.command}
              </pre>
            ) : null}
          </div>
        ))}
      </div>
    );
  }
  if (row.kind === "text") {
    return <p className="whitespace-pre-wrap text-sm">{row.content}</p>;
  }
  if (row.kind === "todo_list") {
    return (
      <ul className="rounded-md border border-neutral-200 px-3 py-2 text-xs dark:border-neutral-700">
        {row.todoList.todos.map((todo, index) => (
          <li key={`${index}-${todo.content}`}>
            {todo.status === "completed" ? "☑" : "☐"} {todo.content}
          </li>
        ))}
      </ul>
    );
  }
  if (row.kind === "compaction") {
    return (
      <div className="rounded-md bg-neutral-100 px-2 py-1 text-xs text-neutral-500 dark:bg-neutral-800">
        ⏳ {row.summary ?? ""}
      </div>
    );
  }
  if (row.kind === "connect_app_request") {
    return (
      <div className="rounded-md bg-neutral-100 px-2 py-1 text-xs text-neutral-500 dark:bg-neutral-800">
        🔌 {row.reason ?? ""}
      </div>
    );
  }
  return (
    <div className="rounded-md border border-red-300 px-2 py-1 text-xs text-red-600 dark:border-red-700 dark:text-red-400">
      {row.content}
    </div>
  );
}

function TurnView({ turn }: { turn: TurnRender }) {
  const t = useTranslations("craftTape");
  const folded = useMemo(
    () => foldTurnStream(turn.items, { isStreaming: false }),
    [turn.items]
  );
  const interrupted =
    turn.reason === "interrupted" || turn.reason === "aborted";
  return (
    <div className="flex flex-col gap-2 border-t border-neutral-200 pt-3 dark:border-neutral-700">
      <div className="flex items-center gap-2 text-xs text-neutral-500">
        {turn.turnIndex !== null ? `#${turn.turnIndex}` : null}
        {turn.reason ? (
          <Tag
            title={turn.reason}
            color={
              turn.reason === "completed"
                ? "green"
                : turn.reason === "error"
                  ? "red"
                  : "amber"
            }
          />
        ) : null}
        {interrupted ? (
          <span className="text-amber-600">{t("replay.interrupted")}</span>
        ) : null}
      </div>
      <div className="flex flex-col gap-2">
        {folded.rows.map((row) => (
          <FoldRowView key={row.id} row={row} />
        ))}
      </div>
      {folded.answer ? (
        <div className="rounded-md bg-neutral-50 p-2 text-sm dark:bg-neutral-900">
          <p className="whitespace-pre-wrap">{folded.answer.content}</p>
        </div>
      ) : null}
    </div>
  );
}

export default function TapeReplayPlayer({
  sessionId,
  fetchReplay,
}: TapeReplayPlayerProps) {
  const t = useTranslations("craftTape");
  const [entries, setEntries] = useState<ReplayPacketItem[] | null>(null);
  const [skipped, setSkipped] = useState(0);
  const [cursor, setCursor] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speedMs, setSpeedMs] = useState<number>(SPEEDS[1].ms);
  const [followingTail, setFollowingTail] = useState(true);
  const entriesRef = useRef<ReplayPacketItem[]>([]);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    const collected: ReplayPacketItem[] = [];
    let after: number | null = null;
    let skippedSum = 0;

    async function drain() {
      for (;;) {
        const page = await fetchReplay(sessionId, { afterSourceId: after });
        if (cancelled) return;
        collected.push(...page.items);
        skippedSum += page.skipped;
        after = page.next_source_id;
        if (after === null || collected.length >= MAX_REPLAY_ENTRIES) {
          break;
        }
      }
      if (!cancelled) {
        entriesRef.current = collected;
        setEntries(collected);
        setSkipped(skippedSum);
        setCursor(0);
      }
    }

    drain().catch((error) =>
      toast.error(errorMessage(error, t("replay.loadFailed")))
    );
    return () => {
      cancelled = true;
    };
  }, [sessionId, fetchReplay, t]);

  useEffect(() => {
    if (!playing || entries === null) return;
    const timer = window.setInterval(() => {
      setCursor((current) => Math.min(current + 1, entries.length));
    }, speedMs);
    return () => window.clearInterval(timer);
  }, [playing, speedMs, entries]);

  // Stop playback once the cursor catches the end (kept out of the state
  // updater: updaters must stay pure).
  useEffect(() => {
    if (playing && entries !== null && cursor >= entries.length) {
      setPlaying(false);
    }
  }, [playing, cursor, entries]);

  // Follow the tail while the reader sits at the bottom (dsh chat scroll).
  useEffect(() => {
    if (!followingTail) return;
    const element = scrollRef.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [cursor, followingTail]);

  // Space toggles playback unless the user is interacting with a control.
  useEffect(() => {
    if (entries === null || entries.length === 0) return;
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.code !== "Space") return;
      const target = event.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.tagName === "BUTTON" ||
          target.isContentEditable)
      ) {
        return;
      }
      event.preventDefault();
      if (!playing && cursor >= entries.length) {
        setCursor(0);
      }
      setPlaying((value) => !value);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [entries, cursor, playing]);

  const total = entries?.length ?? 0;
  const { committed } = useMemo(
    () => (entries ? stateUpTo(entries, cursor) : { committed: [] }),
    [entries, cursor]
  );

  const jumpTurn = useCallback(
    (direction: 1 | -1) => {
      const list = entriesRef.current;
      if (!list.length) return;
      const markers = list
        .map((entry, index) => ({ entry, index }))
        .filter(({ entry }) => entry.type === "marker");
      if (!markers.length) {
        setCursor(direction > 0 ? list.length : 0);
        return;
      }
      if (direction > 0) {
        const following = markers.find(({ index }) => index > cursor);
        const target = following ?? markers[markers.length - 1];
        setCursor(target ? target.index + 1 : list.length);
      } else {
        const prior = [...markers]
          .reverse()
          .find(({ index }) => index < cursor - 1);
        setCursor(prior ? prior.index + 1 : 0);
      }
    },
    [cursor]
  );

  if (entries === null) {
    return (
      <div
        className="text-sm text-neutral-500"
        data-testid="tape-replay-loading"
      >
        {t("replay.loading")}
      </div>
    );
  }
  if (!entries.length) {
    return <div className="text-sm text-neutral-500">{t("replay.empty")}</div>;
  }

  return (
    <div className="flex flex-col gap-2" data-testid="tape-replay-player">
      {/* Transport bar */}
      <div className="flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          aria-label={playing ? t("replay.pause") : t("replay.play")}
          onClick={() => {
            if (!playing && cursor >= total) setCursor(0);
            setPlaying((value) => !value);
          }}
          className="flex h-8 w-8 items-center justify-center rounded-full text-neutral-900 hover:bg-neutral-100 dark:text-neutral-100 dark:hover:bg-neutral-800"
          data-testid="tape-replay-play"
        >
          {playing ? (
            <SvgPauseCircle className="h-6 w-6" />
          ) : (
            <SvgPlayCircle className="h-6 w-6" />
          )}
        </button>
        <button
          type="button"
          aria-label={t("replay.prevTurn")}
          onClick={() => jumpTurn(-1)}
          className="flex h-7 w-7 items-center justify-center rounded-md text-neutral-500 hover:bg-neutral-100 hover:text-neutral-900 dark:text-neutral-400 dark:hover:bg-neutral-800 dark:hover:text-neutral-100"
          data-testid="tape-replay-prev-turn"
        >
          <SvgChevronLeft className="h-4 w-4" />
        </button>
        <button
          type="button"
          aria-label={t("replay.nextTurn")}
          onClick={() => jumpTurn(1)}
          className="flex h-7 w-7 items-center justify-center rounded-md text-neutral-500 hover:bg-neutral-100 hover:text-neutral-900 dark:text-neutral-400 dark:hover:bg-neutral-800 dark:hover:text-neutral-100"
          data-testid="tape-replay-next-turn"
        >
          <SvgChevronRight className="h-4 w-4" />
        </button>
        <Popover>
          <Popover.Trigger asChild>
            <button
              type="button"
              aria-label={t("replay.speed")}
              className="flex h-7 items-center rounded-md border border-neutral-300 px-2 font-mono text-xs text-neutral-600 hover:bg-neutral-100 dark:border-neutral-600 dark:text-neutral-300 dark:hover:bg-neutral-800"
              data-testid="tape-replay-speed"
            >
              {SPEEDS.find((speed) => speed.ms === speedMs)?.label ?? "1x"}
            </button>
          </Popover.Trigger>
          <Popover.Content align="start" width="sm">
            <PopoverMenu>
              {SPEEDS.map((speed) => (
                <button
                  key={speed.label}
                  type="button"
                  role="menuitemradio"
                  aria-checked={speed.ms === speedMs}
                  onClick={() => setSpeedMs(speed.ms)}
                  className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm hover:bg-neutral-100 dark:hover:bg-neutral-800"
                >
                  <span>{speed.label}</span>
                  {speed.ms === speedMs ? (
                    <span className="text-xs">✓</span>
                  ) : null}
                </button>
              ))}
            </PopoverMenu>
          </Popover.Content>
        </Popover>
        <span className="ml-1 font-mono text-xs text-neutral-400">
          {cursor}/{total}
          {skipped > 0 ? ` · ${t("replay.skipped", { count: skipped })}` : ""}
        </span>
        <button
          type="button"
          className="ml-auto text-xs text-neutral-500 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100"
          onClick={() => {
            setPlaying(false);
            setCursor(total);
          }}
          data-testid="tape-replay-jump-end"
        >
          {t("replay.jumpEnd")}
        </button>
      </div>

      {/* Scrubber */}
      <input
        type="range"
        min={0}
        max={total}
        value={cursor}
        aria-label={t("replay.scrubber")}
        onChange={(event) => {
          setPlaying(false);
          setCursor(Number(event.target.value));
        }}
        className="w-full accent-neutral-900 dark:accent-neutral-100"
        data-testid="tape-replay-scrubber"
      />

      {/* Replay surface: a centered column that follows the tail. */}
      <div className="relative">
        <div
          ref={scrollRef}
          className="flex max-h-[32rem] min-h-[12rem] flex-col overflow-y-auto rounded-lg border border-neutral-200 p-3 dark:border-neutral-700"
          onScroll={(event) => {
            const element = event.currentTarget;
            const distance =
              element.scrollHeight - element.scrollTop - element.clientHeight;
            setFollowingTail(distance < FOLLOW_TAIL_THRESHOLD_PX);
          }}
          data-testid="tape-replay-scroll"
        >
          <div className="mx-auto flex w-full max-w-3xl flex-col gap-3">
            {committed.map((turn, index) => (
              <TurnView key={`${turn.turnIndex}-${index}`} turn={turn} />
            ))}
            {committed.length === 0 ? (
              <div className="py-8 text-center text-sm text-neutral-400">
                {t("replay.scrubHint")}
              </div>
            ) : null}
          </div>
        </div>
        {!followingTail ? (
          <button
            type="button"
            className={cn(
              "absolute bottom-3 left-1/2 -translate-x-1/2",
              "flex items-center gap-1 rounded-full bg-neutral-900 px-3 py-1.5 text-xs text-white shadow-md",
              "dark:bg-neutral-100 dark:text-neutral-900"
            )}
            onClick={() => {
              setFollowingTail(true);
              const element = scrollRef.current;
              if (element) element.scrollTop = element.scrollHeight;
            }}
            data-testid="tape-replay-to-bottom"
          >
            <SvgChevronDown className="h-3 w-3" />
            {t("replay.toBottom")}
          </button>
        ) : null}
      </div>
    </div>
  );
}
