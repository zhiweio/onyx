"use client";

/**
 * The session-list browser shared by the personal and admin tape pages — the
 * dsh WorkspaceBrowser pattern ported to Tailwind + opal: an expanding search
 * pill with debounced matching and skeleton rows, a view-options popover
 * (grouping, sorting, time range, origin, admin user filter), and dsh session
 * rows — 32px, a status-dot slot, a marquee title, and a trailing cell that
 * swaps the relative time for row actions on hover.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { InputTypeIn, Popover, PopoverMenu, Tooltip } from "@opal/components";
import { toast } from "@opal/layouts";
import {
  SvgCheck,
  SvgChevronRight,
  SvgCopy,
  SvgDownload,
  SvgSearch,
  SvgSliders,
} from "@opal/icons";
import { cn } from "@opal/utils";
import { humanReadableFormatWithTime } from "@opal/time";
import {
  exportMyTapeSession,
  exportTapeSession,
  listMyTapeSessions,
  listTapeSessions,
} from "@/lib/craft-tape/api";
import type { TapeSessionItem, TapeSessionList } from "@/lib/craft-tape/types";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { errorMessage } from "@/views/admin/McpGatewayPage/format";
import {
  ORIGINS,
  WINDOW_OPTIONS,
  isoDaysAgo,
  originKeyLabel,
  sessionTitle,
} from "./constants";
import { dayGroupOf, relativeTimeFromIso } from "./relativeTime";
import { sessionTapeStatus } from "./tapeStatus";
import TapeStatusDot from "./TapeStatusDot";
import { useTickingNow } from "./useTickingNow";
import { useTitleMarquee } from "./useTitleMarquee";

const PAGE_SIZE = 50;
const SEARCH_DEBOUNCE_MS = 250;
const USER_FILTER_DEBOUNCE_MS = 300;

/* dsh: idle sessions in a group cap at this many visible rows; live
   (running) rows are exempt so ongoing work never hides. */
const COLLAPSED_SESSION_LIMIT = 5;

type GroupBy = "time" | "origin" | "flat";

interface SortPreset {
  key: "recent" | "newest" | "oldest" | "name";
  sort: string;
  order: "asc" | "desc";
}

const SORT_PRESETS: SortPreset[] = [
  { key: "recent", sort: "last_activity", order: "desc" },
  { key: "newest", sort: "created_at", order: "desc" },
  { key: "oldest", sort: "created_at", order: "asc" },
  { key: "name", sort: "name", order: "asc" },
];

const DEFAULT_SORT: SortPreset = {
  key: "recent",
  sort: "last_activity",
  order: "desc",
};

const DAY_GROUP_ORDER = [
  "today",
  "yesterday",
  "thisWeek",
  "thisMonth",
  "earlier",
] as const;

interface TapeGroup {
  key: string;
  label: string | null;
  sessions: TapeSessionItem[];
}

interface ListArgs {
  from?: string;
  origin?: string;
  userQ?: string;
  search?: string;
  sort: string;
  order: "asc" | "desc";
}

export interface TapeListBrowserProps {
  variant: "admin" | "personal";
  selectedId: string | null;
  onSelect: (session: TapeSessionItem) => void;
  /** Lets the page cache items so a deep-linked detail can hydrate its header. */
  onItemsKnown?: (items: TapeSessionItem[]) => void;
}

export default function TapeListBrowser({
  variant,
  selectedId,
  onSelect,
  onItemsKnown,
}: TapeListBrowserProps) {
  const t = useTranslations("craftTape");
  const isAdmin = variant === "admin";
  const now = useTickingNow();

  const [days, setDays] = useState<number | null>(30);
  const [origin, setOrigin] = useState<string>("");
  const [userQInput, setUserQInput] = useState("");
  const userQ = useDebouncedValue(userQInput, USER_FILTER_DEBOUNCE_MS);
  const [sortPreset, setSortPreset] = useState<SortPreset>(DEFAULT_SORT);
  const [groupBy, setGroupBy] = useState<GroupBy>("time");

  const [searchOpen, setSearchOpen] = useState(false);
  const [searchInput, setSearchInput] = useState("");
  const search = useDebouncedValue(searchInput, SEARCH_DEBOUNCE_MS);
  const searchInputRef = useRef<HTMLInputElement | null>(null);

  const [items, setItems] = useState<TapeSessionItem[]>([]);
  const [total, setTotal] = useState(0);
  const [initialLoading, setInitialLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(
    () => new Set()
  );
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(
    () => new Set()
  );

  // Memoized on `days` alone: recomputing per render would churn the request
  // key (the timestamp has ms precision) and refetch in a loop.
  const from = useMemo(
    () => (days === null ? undefined : isoDaysAgo(days)),
    [days]
  );
  const listArgs = useMemo<ListArgs>(
    () => ({
      from,
      origin,
      userQ: userQ || undefined,
      search: search || undefined,
      sort: sortPreset.sort,
      order: sortPreset.order,
    }),
    [from, origin, userQ, search, sortPreset]
  );
  const requestKey = useMemo(
    () => JSON.stringify([variant, listArgs]),
    [variant, listArgs]
  );

  useEffect(() => {
    let cancelled = false;
    setInitialLoading(true);
    setError(null);
    fetchPage({ variant, offset: 0, limit: PAGE_SIZE, args: listArgs })
      .then((page) => {
        if (cancelled) return;
        setItems(page.items);
        setTotal(page.total);
      })
      .catch((err) => {
        if (!cancelled) setError(err);
      })
      .finally(() => {
        if (!cancelled) setInitialLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [requestKey, variant, listArgs]);

  useEffect(() => {
    onItemsKnown?.(items);
  }, [items, onItemsKnown]);

  useEffect(() => {
    if (searchOpen) searchInputRef.current?.focus();
  }, [searchOpen]);

  // "/" opens search from anywhere on the page unless the user is typing.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key !== "/") return;
      const target = event.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable)
      ) {
        return;
      }
      event.preventDefault();
      setSearchOpen(true);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const refetch = useCallback(() => {
    setInitialLoading(true);
    setError(null);
    return fetchPage({
      variant,
      offset: 0,
      limit: PAGE_SIZE,
      args: listArgs,
    })
      .then((page) => {
        setItems(page.items);
        setTotal(page.total);
      })
      .catch((err) => setError(err))
      .finally(() => setInitialLoading(false));
  }, [variant, listArgs]);

  const loadMore = useCallback(() => {
    if (loadingMore) return;
    setLoadingMore(true);
    fetchPage({
      variant,
      offset: items.length,
      limit: PAGE_SIZE,
      args: listArgs,
    })
      .then((page) => {
        setItems((current) => {
          const known = new Set(current.map((s) => s.session_id));
          return [
            ...current,
            ...page.items.filter((s) => !known.has(s.session_id)),
          ];
        });
        setTotal(page.total);
      })
      .catch((err) => toast.error(errorMessage(err, t("loadFailed"))))
      .finally(() => setLoadingMore(false));
  }, [loadingMore, items.length, variant, listArgs, t]);

  const groups = useMemo(
    () => buildGroups(items, groupBy, now, t),
    [items, groupBy, now, t]
  );

  const toggleGroup = useCallback((key: string) => {
    setCollapsedGroups((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const toggleExpanded = useCallback((key: string) => {
    setExpandedGroups((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const copyLink = useCallback(
    (sessionId: string) => {
      const url = `${window.location.origin}${window.location.pathname}?sessionId=${sessionId}`;
      navigator.clipboard
        .writeText(url)
        .then(() => toast.success(t("browser.linkCopied")))
        .catch(() => toast.error(t("browser.linkCopyFailed")));
    },
    [t]
  );

  return (
    <div
      className="flex h-full min-h-0 flex-col"
      data-testid="tape-list-browser"
    >
      {/* Header: section label, expanding search pill, view options (dsh). */}
      <div className="flex items-center gap-1 px-2 pb-1 pt-2">
        {!searchOpen ? (
          <span className="truncate px-1 text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
            {t("browser.title")}
          </span>
        ) : null}
        <div
          className={cn(
            "flex min-w-0 items-center",
            searchOpen ? "flex-1 justify-start" : "ml-auto justify-end"
          )}
        >
          <div
            className={cn(
              "flex min-w-0 items-center overflow-hidden rounded-md border transition-all duration-[180ms] ease-in-out",
              searchOpen
                ? "mr-1 w-full border-neutral-300 dark:border-neutral-600"
                : "w-0 border-transparent"
            )}
          >
            {searchOpen ? (
              <input
                ref={searchInputRef}
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key !== "Escape") return;
                  if (searchInput) setSearchInput("");
                  else setSearchOpen(false);
                }}
                placeholder={t("browser.searchPlaceholder")}
                aria-label={t("browser.search")}
                className="h-7 w-full bg-transparent px-2 text-sm outline-none"
                data-testid="tape-search-input"
              />
            ) : null}
          </div>
          <IconButton
            label={t("browser.search")}
            testId="tape-search-toggle"
            onClick={() => {
              if (searchOpen) {
                setSearchInput("");
                setSearchOpen(false);
              } else {
                setSearchOpen(true);
              }
            }}
          >
            <SvgSearch className="h-4 w-4" />
          </IconButton>
          <ViewOptionsPopover
            t={t}
            isAdmin={isAdmin}
            days={days}
            origin={origin}
            userQInput={userQInput}
            groupBy={groupBy}
            sortPresetKey={sortPreset.key}
            onDays={setDays}
            onOrigin={setOrigin}
            onUserQInput={setUserQInput}
            onGroupBy={setGroupBy}
            onSortPreset={(key) => {
              const preset = SORT_PRESETS.find((p) => p.key === key);
              if (preset) setSortPreset(preset);
            }}
          />
        </div>
      </div>

      {/* List body */}
      <div
        className="min-h-0 flex-1 overflow-y-auto px-2 pb-2"
        role="tree"
        aria-label={t("browser.title")}
        data-testid="tape-list"
      >
        {initialLoading ? (
          <>
            {[0, 1].map((index) => (
              <div
                key={index}
                className="my-1 h-8 animate-pulse rounded-md bg-neutral-200/70 dark:bg-neutral-800"
                data-testid="tape-list-skeleton"
              />
            ))}
          </>
        ) : error ? (
          <div className="flex flex-col items-center gap-2 px-4 py-8 text-center">
            <span className="text-sm text-neutral-500">{t("loadFailed")}</span>
            <button
              type="button"
              className="text-xs text-neutral-900 underline dark:text-neutral-100"
              onClick={() => {
                void refetch();
              }}
              data-testid="tape-list-retry"
            >
              {t("browser.retry")}
            </button>
          </div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center gap-1 px-4 py-10 text-center">
            <span className="text-sm text-neutral-500">
              {t("browser.empty")}
            </span>
            <span className="text-xs text-neutral-400">
              {t("browser.emptyHint")}
            </span>
          </div>
        ) : (
          groups.map((group) => (
            <GroupBlock
              key={group.key}
              group={group}
              collapsed={collapsedGroups.has(group.key)}
              expanded={expandedGroups.has(group.key)}
              selectedId={selectedId}
              now={now}
              isAdmin={isAdmin}
              onToggleGroup={() => toggleGroup(group.key)}
              onToggleExpanded={() => toggleExpanded(group.key)}
              onSelect={onSelect}
              onExport={(sessionId) => {
                const exporter =
                  variant === "admin"
                    ? exportTapeSession(sessionId)
                    : exportMyTapeSession(sessionId);
                exporter.catch((err) =>
                  toast.error(errorMessage(err, t("loadFailed")))
                );
              }}
              onCopyLink={copyLink}
            />
          ))
        )}

        {!initialLoading && !error && items.length < total ? (
          <button
            type="button"
            className="w-full py-2 text-xs text-neutral-500 hover:text-neutral-900 disabled:opacity-50 dark:hover:text-neutral-100"
            onClick={loadMore}
            disabled={loadingMore}
            data-testid="tape-list-load-more"
          >
            {loadingMore
              ? t("table.loading")
              : t("browser.loadMore", { loaded: items.length, total })}
          </button>
        ) : null}
        {!initialLoading &&
        !error &&
        items.length > 0 &&
        items.length >= total ? (
          <div className="py-2 text-center text-xs text-neutral-400">
            {t("browser.endOfList")}
          </div>
        ) : null}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Group of rows
// ---------------------------------------------------------------------------

function GroupBlock({
  group,
  collapsed,
  expanded,
  selectedId,
  now,
  isAdmin,
  onToggleGroup,
  onToggleExpanded,
  onSelect,
  onExport,
  onCopyLink,
}: {
  group: TapeGroup;
  collapsed: boolean;
  expanded: boolean;
  selectedId: string | null;
  now: number;
  isAdmin: boolean;
  onToggleGroup: () => void;
  onToggleExpanded: () => void;
  onSelect: (session: TapeSessionItem) => void;
  onExport: (sessionId: string) => void;
  onCopyLink: (sessionId: string) => void;
}) {
  const t = useTranslations("craftTape");
  // Live rows stay visible at the cap (dsh exempts running sessions).
  const active = group.sessions.filter(
    (session) => sessionTapeStatus(session) === "running"
  );
  const rest = group.sessions.filter(
    (session) => sessionTapeStatus(session) !== "running"
  );
  const visible = expanded
    ? group.sessions
    : [
        ...active,
        ...rest.slice(0, Math.max(0, COLLAPSED_SESSION_LIMIT - active.length)),
      ];
  const hidden = group.sessions.length - visible.length;
  const overCap = group.sessions.length > COLLAPSED_SESSION_LIMIT;

  return (
    <div className="mb-1" data-testid={`tape-group-${group.key}`}>
      {group.label ? (
        <button
          type="button"
          className="flex h-7 w-full items-center gap-1 rounded-md px-1 text-left"
          onClick={onToggleGroup}
          aria-expanded={!collapsed}
        >
          <SvgChevronRight
            className={cn(
              "h-3 w-3 flex-none text-neutral-400 transition-transform",
              !collapsed && "rotate-90"
            )}
          />
          <span className="truncate text-[11px] font-medium uppercase tracking-wide text-neutral-400 dark:text-neutral-500">
            {group.label}
          </span>
          <span className="ml-auto text-[11px] text-neutral-400 dark:text-neutral-500">
            {group.sessions.length}
          </span>
        </button>
      ) : null}

      {!collapsed
        ? visible.map((session) => (
            <TapeSessionRow
              key={session.session_id}
              session={session}
              selected={session.session_id === selectedId}
              now={now}
              isAdmin={isAdmin}
              onSelect={onSelect}
              onExport={onExport}
              onCopyLink={onCopyLink}
            />
          ))
        : null}

      {!collapsed && hidden > 0 ? (
        <button
          type="button"
          className="w-full py-1 pl-6 text-left text-xs text-neutral-500 hover:text-neutral-900 dark:hover:text-neutral-100"
          onClick={onToggleExpanded}
          data-testid={`tape-group-more-${group.key}`}
        >
          {t("browser.showMore", { count: hidden })}
        </button>
      ) : null}
      {!collapsed && expanded && overCap ? (
        <button
          type="button"
          className="w-full py-1 pl-6 text-left text-xs text-neutral-500 hover:text-neutral-900 dark:hover:text-neutral-100"
          onClick={onToggleExpanded}
        >
          {t("browser.showLess")}
        </button>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Session row (dsh SessionNodeItem port)
// ---------------------------------------------------------------------------

function TapeSessionRow({
  session,
  selected,
  now,
  isAdmin,
  onSelect,
  onExport,
  onCopyLink,
}: {
  session: TapeSessionItem;
  selected: boolean;
  now: number;
  isAdmin: boolean;
  onSelect: (session: TapeSessionItem) => void;
  onExport: (sessionId: string) => void;
  onCopyLink: (sessionId: string) => void;
}) {
  const t = useTranslations("craftTape");
  const status = sessionTapeStatus(session);
  const title = sessionTitle(session);
  const bucket = relativeTimeFromIso(
    session.last_activity ?? session.created_at,
    now
  );
  const rowRef = useRef<HTMLDivElement | null>(null);
  const titleRef = useRef<HTMLSpanElement | null>(null);
  const marquee = useTitleMarquee(titleRef);

  // Deep link: bring the selected row into view once it mounts.
  useEffect(() => {
    if (selected) rowRef.current?.scrollIntoView({ block: "nearest" });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount-only reveal
  }, []);

  return (
    <Tooltip
      side="bottom"
      delayDuration={800}
      tooltip={
        <div className="flex flex-col gap-1">
          <div className="text-sm font-medium">{title}</div>
          {isAdmin && session.user_email ? (
            <div className="text-xs opacity-80">{session.user_email}</div>
          ) : null}
          {session.created_at ? (
            <div className="text-xs opacity-80">
              {t("browser.created", {
                time: humanReadableFormatWithTime(session.created_at),
              })}
            </div>
          ) : null}
          <div className="flex items-center gap-2 text-xs opacity-80">
            <TapeStatusDot status={status} />
            {t(`status.${status}`)}
          </div>
        </div>
      }
    >
      <div
        ref={rowRef}
        className={cn(
          "tape-row group flex cursor-pointer select-none items-center rounded-md px-2",
          isAdmin ? "h-11" : "h-8",
          selected
            ? "bg-neutral-200/70 dark:bg-neutral-700/50"
            : "hover:bg-neutral-100 dark:hover:bg-neutral-800"
        )}
        role="treeitem"
        aria-selected={selected}
        tabIndex={0}
        onClick={(event) => {
          // Row actions stop here: clicks on the export/copy buttons must not
          // also select the row.
          if ((event.target as HTMLElement).closest("button")) return;
          onSelect(session);
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onSelect(session);
          }
        }}
        onPointerEnter={marquee.enter}
        onPointerLeave={marquee.leave}
        data-testid={`tape-row-${session.session_id}`}
      >
        <span className="flex h-5 w-4 flex-none items-center justify-center">
          <TapeStatusDot status={status} />
        </span>
        <span className="flex min-w-0 flex-1 flex-col pl-1">
          <span
            ref={titleRef}
            className="tape-row-title min-w-0 flex-none overflow-hidden text-ellipsis whitespace-nowrap text-sm leading-5"
          >
            {title}
          </span>
          {isAdmin ? (
            <span className="overflow-hidden text-ellipsis whitespace-nowrap text-xs leading-4 text-neutral-500 dark:text-neutral-400">
              {session.user_email ?? session.user_id ?? "—"}
            </span>
          ) : null}
        </span>
        {/* Trailing cell: the relative time hides and the actions fade in on
            hover, exactly as in dsh Rows.module.css. */}
        <span className="relative flex h-5 flex-none items-center">
          <span className="text-[10px] leading-4 text-neutral-400 transition-opacity group-hover:opacity-0 dark:text-neutral-500">
            {compactTimeLabel(bucket, t)}
          </span>
          <span className="absolute inset-y-0 right-0 hidden items-center gap-1.5 text-neutral-500 group-hover:flex dark:text-neutral-400">
            <IconButton
              label={t("browser.copyLink")}
              testId={`tape-row-copy-${session.session_id}`}
              onClick={() => onCopyLink(session.session_id)}
            >
              <SvgCopy className="h-3.5 w-3.5" />
            </IconButton>
            <IconButton
              label={t("export")}
              testId={`tape-row-export-${session.session_id}`}
              onClick={() => onExport(session.session_id)}
            >
              <SvgDownload className="h-3.5 w-3.5" />
            </IconButton>
          </span>
        </span>
      </div>
    </Tooltip>
  );
}

// ---------------------------------------------------------------------------
// View options popover (dsh view-options menu)
// ---------------------------------------------------------------------------

interface ViewOptionsPopoverProps {
  t: ReturnType<typeof useTranslations>;
  isAdmin: boolean;
  days: number | null;
  origin: string;
  userQInput: string;
  groupBy: GroupBy;
  sortPresetKey: SortPreset["key"];
  onDays: (days: number | null) => void;
  onOrigin: (origin: string) => void;
  onUserQInput: (value: string) => void;
  onGroupBy: (groupBy: GroupBy) => void;
  onSortPreset: (key: SortPreset["key"]) => void;
}

function ViewOptionsPopover({
  t,
  isAdmin,
  days,
  origin,
  userQInput,
  groupBy,
  sortPresetKey,
  onDays,
  onOrigin,
  onUserQInput,
  onGroupBy,
  onSortPreset,
}: ViewOptionsPopoverProps) {
  return (
    <Popover>
      <Popover.Trigger asChild>
        <IconButton label={t("browser.viewOptions")} testId="tape-view-options">
          <SvgSliders className="h-4 w-4" />
        </IconButton>
      </Popover.Trigger>
      <Popover.Content
        align="end"
        width="md"
        data-testid="tape-view-options-menu"
      >
        <PopoverMenu>
          <MenuLabel>{t("browser.groupBy")}</MenuLabel>
          <MenuOption
            active={groupBy === "time"}
            onClick={() => onGroupBy("time")}
          >
            {t("browser.groupTime")}
          </MenuOption>
          <MenuOption
            active={groupBy === "origin"}
            onClick={() => onGroupBy("origin")}
          >
            {t("browser.groupOrigin")}
          </MenuOption>
          <MenuOption
            active={groupBy === "flat"}
            onClick={() => onGroupBy("flat")}
          >
            {t("browser.groupFlat")}
          </MenuOption>
          {null}
          <MenuLabel>{t("browser.sortBy")}</MenuLabel>
          {SORT_PRESETS.map((preset) => (
            <MenuOption
              key={preset.key}
              active={sortPresetKey === preset.key}
              onClick={() => onSortPreset(preset.key)}
            >
              {t(`browser.sort_${preset.key}`)}
            </MenuOption>
          ))}
          {null}
          <MenuLabel>{t("filters.origin")}</MenuLabel>
          <MenuOption active={origin === ""} onClick={() => onOrigin("")}>
            {t("filters.allOrigins")}
          </MenuOption>
          {ORIGINS.map((value) => (
            <MenuOption
              key={value}
              active={origin === value}
              onClick={() => onOrigin(value)}
            >
              {t(`origins.${value}`)}
            </MenuOption>
          ))}
          {null}
          <MenuLabel>{t("browser.timeRange")}</MenuLabel>
          {WINDOW_OPTIONS.map((option) => (
            <MenuOption
              key={option}
              active={days === option}
              onClick={() => onDays(option)}
            >
              {t(`browser.last_${option}`)}
            </MenuOption>
          ))}
          <MenuOption active={days === null} onClick={() => onDays(null)}>
            {t("browser.allTime")}
          </MenuOption>
          {isAdmin ? (
            <>
              {null}
              <MenuLabel>{t("browser.userFilter")}</MenuLabel>
              <div className="px-1 pb-1">
                <InputTypeIn
                  value={userQInput}
                  onChange={(event) => onUserQInput(event.target.value)}
                  placeholder={t("browser.userPlaceholder")}
                  aria-label={t("browser.userFilter")}
                  data-testid="tape-user-filter"
                />
              </div>
            </>
          ) : null}
        </PopoverMenu>
      </Popover.Content>
    </Popover>
  );
}

// ---------------------------------------------------------------------------
// Small shared pieces
// ---------------------------------------------------------------------------

function IconButton({
  label,
  testId,
  className,
  children,
  ...buttonProps
}: {
  label: string;
  testId?: string;
  children: React.ReactNode;
} & React.ComponentPropsWithoutRef<"button">) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      data-testid={testId}
      className={cn(
        "flex h-6 w-6 flex-none items-center justify-center rounded-md text-neutral-500",
        "hover:bg-neutral-100 hover:text-neutral-900 dark:hover:bg-neutral-800 dark:hover:text-neutral-100",
        className
      )}
      {...buttonProps}
    >
      {children}
    </button>
  );
}

function MenuLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-2 pb-0.5 pt-1.5 text-[11px] font-medium uppercase tracking-wide text-neutral-400 dark:text-neutral-500">
      {children}
    </div>
  );
}

function MenuOption({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-neutral-100 dark:hover:bg-neutral-800"
      role="menuitemradio"
      aria-checked={active}
    >
      <span className="truncate">{children}</span>
      {active ? (
        <SvgCheck className="h-3.5 w-3.5 flex-none text-neutral-900 dark:text-neutral-100" />
      ) : null}
    </button>
  );
}

function compactTimeLabel(
  bucket: ReturnType<typeof relativeTimeFromIso>,
  t: ReturnType<typeof useTranslations>
): string {
  if (!bucket) return "—";
  if (bucket.unit === "now") return t("time.now");
  return t(`time.${bucket.unit}`, { n: bucket.n });
}

function buildGroups(
  items: TapeSessionItem[],
  groupBy: GroupBy,
  now: number,
  t: ReturnType<typeof useTranslations>
): TapeGroup[] {
  if (groupBy === "flat") {
    return [{ key: "flat", label: null, sessions: items }];
  }
  if (groupBy === "origin") {
    const buckets = new Map<string, TapeSessionItem[]>();
    for (const session of items) {
      const key = session.origin ?? "unknown";
      const bucket = buckets.get(key);
      if (bucket) bucket.push(session);
      else buckets.set(key, [session]);
    }
    return [...buckets.entries()].map(([key, sessions]) => ({
      key: `origin:${key}`,
      label: originKeyLabel(key, (k) => t(k)),
      sessions,
    }));
  }
  const buckets = new Map<string, TapeSessionItem[]>();
  for (const session of items) {
    const iso = session.last_activity ?? session.created_at;
    const at = iso ? new Date(iso).getTime() : NaN;
    const group = Number.isFinite(at)
      ? dayGroupOf(at, now)
      : ("earlier" as const);
    const bucket = buckets.get(group);
    if (bucket) bucket.push(session);
    else buckets.set(group, [session]);
  }
  return DAY_GROUP_ORDER.filter((key) => buckets.has(key)).map((key) => ({
    key,
    label: t(`browser.${key}`),
    sessions: buckets.get(key) ?? [],
  }));
}

async function fetchPage(args: {
  variant: "admin" | "personal";
  offset: number;
  limit: number;
  args: ListArgs;
}): Promise<TapeSessionList> {
  const shared = {
    from: args.args.from,
    to: new Date().toISOString(),
    origin: args.args.origin || undefined,
    q: args.args.search,
    sort: args.args.sort,
    order: args.args.order,
    offset: args.offset,
    limit: args.limit,
  };
  return args.variant === "admin"
    ? listTapeSessions({ ...shared, userQ: args.args.userQ })
    : listMyTapeSessions(shared);
}
