import {
  SvgBot,
  SvgFile,
  SvgMcp,
  SvgSquareArrowUpRight,
  SvgWandSparkles,
} from "@opal/icons";

/**
 * Single source of truth for category icons — the same mark everywhere a
 * category appears (picker rows, plus menu, tool cards, badges, chips,
 * switcher): skills = wand sparkles, commands = square arrow, agents /
 * subagents / task tool = bot, files = file, MCP = mcp. Mirrors ZCode's
 * category icon set.
 */
export const CATEGORY_SKILL_ICON = SvgWandSparkles;
export const CATEGORY_COMMAND_ICON = SvgSquareArrowUpRight;
export const CATEGORY_AGENT_ICON = SvgBot;
export const CATEGORY_FILE_ICON = SvgFile;
export const CATEGORY_MCP_ICON = SvgMcp;
