import type { useTranslations } from "next-intl";
import { SvgFileText, SvgFolder, SvgPaperclip } from "@opal/icons";
import { CRAFT_LIBRARY_PATH } from "@/app/craft/v1/constants";
import type { PlusMenuItem } from "@/sections/input/PlusMenuButton";

export type EntryMenuTranslate = ReturnType<
  typeof useTranslations<"craft.entryMenu">
>;

interface LibraryFile {
  id: string;
  name: string;
  /** Whether the file is already attached to the prompt as a chip. */
  checked: boolean;
  onToggle: (checked: boolean) => void;
}

export interface EntryMenuHandlers {
  onAttachFiles: () => void;
  libraryFiles?: LibraryFile[];
}

/**
 * Maps the chat-style plus menu onto the generic PlusMenuButton model: direct
 * file attach plus the user-library drill-in. Skills and MCP servers are
 * deliberately NOT selectable here: skills come from the composer's / and $
 * menus, and MCP enablement lives on /craft/v1/mcp-actions (single source of
 * truth).
 */
export function buildEntryMenuItems(
  {
    onAttachFiles,
    libraryFiles = [],
  }: Pick<EntryMenuHandlers, "onAttachFiles" | "libraryFiles">,
  t: EntryMenuTranslate
): Array<PlusMenuItem | null> {
  return [
    {
      key: "files",
      icon: SvgPaperclip,
      label: t("addFiles.label"),
      onSelect: onAttachFiles,
    },
    {
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
          checked: file.checked,
          onCheckedChange: file.onToggle,
        })),
      },
    },
  ];
}
