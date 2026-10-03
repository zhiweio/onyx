import type { IconFunctionComponent } from "@opal/types";
import { SvgScrollText } from "@opal/icons";
import { getAppTypeLogo } from "@/app/craft/v1/apps/registry";
import type { PickerEntry } from "@/lib/skills/picker";
import {
  CATEGORY_COMMAND_ICON,
  CATEGORY_FILE_ICON,
  CATEGORY_SKILL_ICON,
} from "@/lib/skills/categoryIcons";

/** Icon for a picker entry, mirroring ZCode's category icons: the wand
 * (sparkles) mark for skills, the square-arrow mark for commands, the
 * provider logo for apps, the server logo for MCP, the file glyph for
 * files, and the scroll mark for scenarios. Kept out of `picker.ts` so the
 * data module stays free of view imports, and shared so the surfaces
 * rendering picker entries can't drift as the entry union grows. */
export function pickerEntryIcon(entry: PickerEntry): IconFunctionComponent {
  switch (entry.kind) {
    case "app":
      return getAppTypeLogo(entry.appType);
    case "skill":
      return CATEGORY_SKILL_ICON;
    case "command":
      return CATEGORY_COMMAND_ICON;
    case "file":
      return CATEGORY_FILE_ICON;
    case "scenario":
      return SvgScrollText;
  }
}
