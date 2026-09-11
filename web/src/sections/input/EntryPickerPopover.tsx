"use client";

import {
  memo,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { useTranslations } from "next-intl";
import { Popover, Text, Tooltip } from "@opal/components";
import {
  filterPickerSections,
  flattenSections,
  pickerEntryKey,
  type PickerEntry,
  type PickerSections,
} from "@/lib/skills/picker";
import { pickerEntryIcon } from "@/lib/skills/pickerIcons";
import { cn } from "@opal/utils";

interface EntryPickerPopoverProps {
  open: boolean;
  anchorRect: DOMRect | null;
  query: string;
  sections: PickerSections;
  onSelect: (entry: PickerEntry) => void;
  onClose: () => void;
}

function EntryPickerPopover({
  open,
  anchorRect,
  query,
  sections,
  onSelect,
  onClose,
}: EntryPickerPopoverProps) {
  const t = useTranslations("chat.input");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  const filtered = useMemo(
    () => filterPickerSections(sections, query),
    [sections, query]
  );
  const flatEntries = useMemo(() => flattenSections(filtered), [filtered]);

  useEffect(() => {
    setSelectedIndex(0);
  }, [open, query]);

  // SWR may revalidate while open and shrink the row count; clamp so Enter
  // doesn't silently fall back to a different row than the one highlighted.
  useEffect(() => {
    setSelectedIndex((i) =>
      flatEntries.length === 0 ? 0 : Math.min(i, flatEntries.length - 1)
    );
  }, [flatEntries.length]);

  useEffect(() => {
    if (!open) return;
    const container = scrollContainerRef.current;
    if (!container) return;
    const row = container.querySelector<HTMLElement>(
      `[data-row-index="${selectedIndex}"]`
    );
    row?.scrollIntoView({ block: "nearest" });
  }, [open, selectedIndex]);

  useEffect(() => {
    if (!open) return;

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        e.stopPropagation();
        if (flatEntries.length === 0) return;
        setSelectedIndex((i) => (i + 1) % flatEntries.length);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        e.stopPropagation();
        if (flatEntries.length === 0) return;
        setSelectedIndex(
          (i) => (i - 1 + flatEntries.length) % flatEntries.length
        );
      } else if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        e.stopPropagation();
        if (flatEntries.length === 0) {
          onClose();
          return;
        }
        const entry = flatEntries[selectedIndex] ?? flatEntries[0];
        if (entry) onSelect(entry);
      } else if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        onClose();
      }
    }

    document.addEventListener("keydown", handleKeyDown, true);
    return () => document.removeEventListener("keydown", handleKeyDown, true);
  }, [open, flatEntries, selectedIndex, onSelect, onClose]);

  if (!anchorRect) return null;

  // `position: fixed` is containing-block-relative under a transformed
  // ancestor (Storybook docs view, some app shells), so portal to body to
  // keep the anchor's coords viewport-relative.
  if (typeof document === "undefined") return null;

  const labels = {
    commands: t("entryPickerPopover.commandsGroup.label"),
    skills: t("entryPickerPopover.skillsGroup.label"),
    apps: t("entryPickerPopover.appsGroup.label"),
    mcpServers: t("entryPickerPopover.mcpServersGroup.label"),
    connected: t("entryPickerPopover.connectedRow.description"),
    connectionRequired: t("entryPickerPopover.connectionRequiredRow.description"),
    connectAction: t("entryPickerPopover.connectAction.label"),
    kindSkill: t("entryPickerPopover.tooltip.kindSkill"),
    kindCommand: t("entryPickerPopover.tooltip.kindCommand"),
    kindApp: t("entryPickerPopover.tooltip.kindApp"),
    kindMcp: t("entryPickerPopover.tooltip.kindMcp"),
  };

  return createPortal(
    <Popover
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <Popover.Anchor asChild>
        <div
          aria-hidden
          style={{
            position: "fixed",
            left: anchorRect.left,
            top: anchorRect.top,
            width: anchorRect.width,
            height: 1,
            pointerEvents: "none",
          }}
        />
      </Popover.Anchor>
      <Popover.Content
        side="top"
        align="start"
        width="fit"
        sideOffset={6}
        onOpenAutoFocus={(e) => e.preventDefault()}
        data-testid="skill-picker-popover"
        aria-label={t("entryPickerPopover.content.ariaLabel")}
      >
        {/* Popover chrome is p-1 + 1px border (10px). Size the list to the
            composer so the panel matches the input card. */}
        <div
          style={{ width: Math.max(anchorRect.width - 10, 240) }}
          className="min-w-0"
        >
          <Popover.Menu scrollContainerRef={scrollContainerRef}>
            {buildMenuChildren({
              filtered,
              flatEntries,
              selectedIndex,
              onSelect,
              onHover: setSelectedIndex,
              emptyMessage: t("entryPickerPopover.empty.text"),
              labels,
            })}
          </Popover.Menu>
        </div>
      </Popover.Content>
    </Popover>,
    document.body
  );
}

interface PickerLabels {
  commands: string;
  skills: string;
  apps: string;
  mcpServers: string;
  connected: string;
  connectionRequired: string;
  connectAction: string;
  kindSkill: string;
  kindCommand: string;
  kindApp: string;
  kindMcp: string;
}

interface BuildMenuChildrenArgs {
  filtered: PickerSections;
  flatEntries: PickerEntry[];
  selectedIndex: number;
  onSelect: (entry: PickerEntry) => void;
  onHover: (idx: number) => void;
  emptyMessage: string;
  labels: PickerLabels;
}

// `Popover.Menu` renders a literal `null` between children as a divider.
function buildMenuChildren({
  filtered,
  flatEntries,
  selectedIndex,
  onSelect,
  onHover,
  emptyMessage,
  labels,
}: BuildMenuChildrenArgs): ReactNode[] {
  if (flatEntries.length === 0) {
    return [
      <div key="empty" className="p-2">
        <Text font="secondary-body" color="text-03">
          {emptyMessage}
        </Text>
      </div>,
    ];
  }

  // Groups must stay in `flattenSections` order — keyboard nav indexes into that
  // flat list, so a running index is what keeps the two aligned.
  const groups: { key: string; label: string; entries: PickerEntry[] }[] = [
    {
      key: "commands",
      label: labels.commands,
      entries: filtered.commands,
    },
    { key: "skills", label: labels.skills, entries: filtered.skills },
    { key: "apps", label: labels.apps, entries: filtered.apps },
    {
      key: "mcpServers",
      label: labels.mcpServers,
      entries: filtered.mcpServers,
    },
  ];

  const children: ReactNode[] = [];
  let idx = 0;

  for (const group of groups) {
    if (group.entries.length === 0) continue;
    if (children.length > 0) children.push(null);
    children.push(
      <SectionHeader key={`${group.key}-header`} label={group.label} />
    );
    for (const entry of group.entries) {
      children.push(
        <PickerRow
          key={pickerEntryKey(entry)}
          entry={entry}
          selected={idx === selectedIndex}
          rowIndex={idx}
          labels={labels}
          onHover={() => onHover(idx)}
          onPick={() => onSelect(entry)}
        />
      );
      idx += 1;
    }
  }

  return children;
}

function SectionHeader({ label }: { label: string }) {
  return (
    <div className="px-2 pt-1 pb-0.5">
      <Text font="secondary-action" color="text-03">
        {label}
      </Text>
    </div>
  );
}

function pickerRowTitle(entry: PickerEntry): string {
  switch (entry.kind) {
    case "skill":
    case "command":
      return `/${entry.slug}`;
    case "app":
    case "mcp":
      return entry.name;
  }
}

function pickerRowDescription(entry: PickerEntry, labels: PickerLabels): string {
  switch (entry.kind) {
    case "skill":
    case "command":
      return entry.description;
    case "mcp":
      return entry.description?.trim()
        ? entry.description
        : entry.authenticated
          ? labels.connected
          : labels.connectionRequired;
    case "app":
      return entry.authenticated
        ? labels.connected
        : labels.connectionRequired;
  }
}

function pickerRowKind(entry: PickerEntry, labels: PickerLabels): string {
  switch (entry.kind) {
    case "skill":
      return labels.kindSkill;
    case "command":
      return labels.kindCommand;
    case "app":
      return labels.kindApp;
    case "mcp":
      return labels.kindMcp;
  }
}

function pickerRowTestId(entry: PickerEntry): string {
  switch (entry.kind) {
    case "skill":
      return `skill-picker-row-${entry.slug}`;
    case "command":
      return `command-picker-row-${entry.slug}`;
    case "app":
      return `app-picker-row-${entry.externalAppId}`;
    case "mcp":
      return `mcp-picker-row-${entry.mcpServerId}`;
  }
}

interface PickerRowProps {
  entry: PickerEntry;
  selected: boolean;
  rowIndex: number;
  labels: PickerLabels;
  onHover: () => void;
  onPick: () => void;
}

function PickerRow({
  entry,
  selected,
  rowIndex,
  labels,
  onHover,
  onPick,
}: PickerRowProps) {
  const Icon = pickerEntryIcon(entry);
  const title = pickerRowTitle(entry);
  const description = pickerRowDescription(entry, labels);
  const kind = pickerRowKind(entry, labels);
  const unauth =
    (entry.kind === "mcp" || entry.kind === "app") && !entry.authenticated;

  const tooltip = (
    <div className="flex max-w-80 flex-col gap-1">
      <Text font="secondary-action" color="inherit" as="p">
        {title}
      </Text>
      {(entry.kind === "skill" || entry.kind === "command") &&
      entry.name !== entry.slug ? (
        <Text font="secondary-body" color="inherit" as="p">
          {entry.name}
        </Text>
      ) : null}
      {description ? (
        <Text font="secondary-body" color="inherit" as="p">
          {description}
        </Text>
      ) : null}
      <Text font="secondary-body" color="inherit" as="p">
        {kind}
      </Text>
      {entry.kind === "mcp" ? (
        <Text font="secondary-body" color="inherit" as="p">
          {entry.serverUrl}
        </Text>
      ) : null}
    </div>
  );

  return (
    <Tooltip tooltip={tooltip} side="right" align="start" delayDuration={300}>
      <div
        className="cursor-pointer"
        aria-label={[title, description, kind].filter(Boolean).join(" ")}
        onMouseEnter={onHover}
        onMouseDown={(e) => {
          e.preventDefault();
          onPick();
        }}
      >
        <div
          className={cn(
            "flex w-full min-w-0 items-center gap-2 rounded-08 px-2 py-1",
            selected
              ? "line-item-row-main-emphasized"
              : "line-item-row-main"
          )}
          data-row-index={rowIndex}
          data-testid={pickerRowTestId(entry)}
          data-selected={selected}
        >
          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-08 bg-background-tint-02">
            <Icon className="h-3.5 w-3.5 text-text-03" />
          </span>
          <span className="flex min-w-0 flex-1 items-baseline gap-2">
            <span className="max-w-[45%] shrink-0 truncate font-secondary-action text-text-05">
              {title}
            </span>
            {description ? (
              <span className="min-w-0 flex-1 truncate font-secondary-body text-text-03">
                {description}
              </span>
            ) : null}
          </span>
          {unauth ? (
            <Text font="secondary-action" color="text-03" nowrap>
              {labels.connectAction}
            </Text>
          ) : null}
        </div>
      </div>
    </Tooltip>
  );
}

export default memo(EntryPickerPopover);
