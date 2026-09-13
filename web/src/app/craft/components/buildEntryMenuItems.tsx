import type { useTranslations } from "next-intl";
import {
  SvgFileText,
  SvgFolder,
  SvgMcp,
  SvgPaperclip,
  SvgSparkle,
} from "@opal/icons";
import {
  pickerEntryKey,
  type PickerEntry,
  type PickerSections,
} from "@/lib/skills/picker";
import { pickerEntryIcon } from "@/lib/skills/pickerIcons";
import {
  CRAFT_LIBRARY_PATH,
  CRAFT_MCP_ACTIONS_PATH,
  CRAFT_SKILLS_PATH,
} from "@/app/craft/v1/constants";
import type {
  PlusMenuItem,
  PlusMenuPanelRow,
} from "@/sections/input/PlusMenuButton";

export type EntryMenuTranslate = ReturnType<
  typeof useTranslations<"craft.entryMenu">
>;

interface LibraryFile {
  id: string;
  name: string;
}

export interface EntryMenuHandlers {
  onAttachFiles: () => void;
  onSelectEntry: (entry: PickerEntry) => void;
  onRemoveEntry: (entryKey: string) => void;
  activeEntries?: PickerEntry[];
  libraryFiles?: LibraryFile[];
}

function entryRow(
  entry: PickerEntry,
  activeKeys: Set<string>,
  {
    onSelectEntry,
    onRemoveEntry,
  }: Pick<EntryMenuHandlers, "onSelectEntry" | "onRemoveEntry">,
  connectHint?: string
): PlusMenuPanelRow {
  const key = pickerEntryKey(entry);
  const checked = activeKeys.has(key);
  return {
    key,
    icon: pickerEntryIcon(entry),
    label: entry.name,
    description:
      (entry.kind === "app" || entry.kind === "mcp") && !entry.authenticated
        ? connectHint
        : undefined,
    checked,
    onCheckedChange: (next) => {
      if (next) onSelectEntry(entry);
      else onRemoveEntry(key);
    },
    onSelect: () => {
      if (!checked) onSelectEntry(entry);
    },
  };
}

/** Maps picker sections onto the generic PlusMenuButton model. */
export function buildEntryMenuItems(
  sections: PickerSections,
  {
    onAttachFiles,
    onSelectEntry,
    onRemoveEntry,
    activeEntries = [],
    libraryFiles = [],
  }: EntryMenuHandlers,
  t: EntryMenuTranslate
): Array<PlusMenuItem | null> {
  const activeKeys = new Set(activeEntries.map(pickerEntryKey));
  const connectHint = t("connect.hint");
  const mcpRows = [...sections.apps, ...sections.mcpServers].map((entry) =>
    entryRow(entry, activeKeys, { onSelectEntry, onRemoveEntry }, connectHint)
  );

  const items: Array<PlusMenuItem | null> = [
    {
      key: "files",
      icon: SvgPaperclip,
      label: t("addFiles.label"),
      onSelect: onAttachFiles,
    },
    {
      key: "skills",
      icon: SvgSparkle,
      label: t("skills.label"),
      panel: {
        searchPlaceholder: t("skills.searchPlaceholder"),
        manageLabel: t("skills.manage"),
        manageHref: CRAFT_SKILLS_PATH,
        manageTarget: "_blank",
        emptyLabel: t("skills.empty"),
        rows: sections.skills.map((skill) =>
          entryRow(skill, activeKeys, { onSelectEntry, onRemoveEntry })
        ),
      },
    },
    {
      key: "mcp",
      icon: SvgMcp,
      label: t("mcp.label"),
      panel: {
        searchPlaceholder: t("mcp.searchPlaceholder"),
        manageLabel: t("mcp.manage"),
        manageHref: CRAFT_MCP_ACTIONS_PATH,
        manageTarget: "_blank",
        emptyLabel: t("mcp.empty"),
        rows: mcpRows,
      },
    },
  ];

  items.push({
    key: "library",
    icon: SvgFolder,
    label: t("library.label"),
    panel: {
      searchPlaceholder: t("library.searchPlaceholder"),
      manageLabel: t("library.manage"),
      manageHref: CRAFT_LIBRARY_PATH,
      emptyLabel: t("library.empty"),
      rows: libraryFiles.map((file) => ({
        key: file.id,
        icon: SvgFileText,
        label: file.name,
        checked: false,
        onCheckedChange: () => undefined,
      })),
    },
  });

  return items;
}
