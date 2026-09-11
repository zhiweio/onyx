import type {
  ExternalAppType,
  ExternalAppUserResponse,
} from "@/app/craft/v1/apps/registry";
import type { SkillsList } from "@/lib/skills/types";
import type { MCPServer } from "@/lib/tools/types";
import { CRAFT_APPS_TAB_PARAM } from "@/app/craft/v1/apps/connectableApps";
import { CRAFT_APPS_PATH } from "@/app/craft/v1/constants";

export interface PickerSkill {
  kind: "skill";
  slug: string;
  name: string;
  description: string;
}

export interface PickerApp {
  kind: "app";
  externalAppId: number;
  name: string;
  appType: ExternalAppType;
  authenticated: boolean;
}

/** A craft-enabled MCP server. Kept a distinct kind from `PickerApp` rather
 * than folded in: the two are connected differently, reach the agent by
 * different channels, and the user is told which is which. */
export interface PickerMcpServer {
  kind: "mcp";
  mcpServerId: number;
  name: string;
  serverUrl: string;
  authenticated: boolean;
  description?: string;
}

export interface PickerCommand {
  kind: "command";
  slug: string;
  name: string;
  description: string;
}

export type PickerEntry =
  | PickerSkill
  | PickerApp
  | PickerMcpServer
  | PickerCommand;

export interface PickerSections {
  commands: PickerCommand[];
  skills: PickerSkill[];
  apps: PickerApp[];
  mcpServers: PickerMcpServer[];
}

export const COMPACT_COMMAND_SLUG = "compact";

const EMPTY_SECTIONS: PickerSections = {
  commands: [],
  skills: [],
  apps: [],
  mcpServers: [],
};

/** Case-insensitive name ordering, shared so every surface listing apps and MCP
 * servers sorts them the same way. */
export function compareByName<T extends { name: string }>(a: T, b: T): number {
  return a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
}

// Associated custom skills remain normal per-user selections, with app
// readiness as an additional runtime requirement.
export function toPickerSections(
  skillsData: SkillsList | undefined,
  externalApps: ExternalAppUserResponse[] | undefined,
  mcpServers?: MCPServer[] | undefined
): PickerSections {
  if (!skillsData && !externalApps && !mcpServers) return EMPTY_SECTIONS;

  const skills: PickerSkill[] = [];
  const apps: PickerApp[] = [];
  const mcp: PickerMcpServer[] = [];
  for (const b of skillsData?.builtins ?? []) {
    if (!b.is_available || !b.enabled) continue;
    if (b.name === "long-job-protocol") continue;
    skills.push({
      kind: "skill",
      slug: b.name,
      name: b.name,
      description: b.description,
    });
  }

  for (const c of skillsData?.customs ?? []) {
    if (
      !c.enabled ||
      c.is_valid === false ||
      (c.external_app !== null && !c.external_app.ready)
    ) {
      continue;
    }
    skills.push({
      kind: "skill",
      slug: c.name,
      name: c.name,
      description: c.description,
    });
  }

  for (const app of externalApps ?? []) {
    apps.push({
      kind: "app",
      externalAppId: app.id,
      name: app.name,
      appType: app.app_type,
      authenticated: app.authenticated,
    });
  }

  for (const server of mcpServers ?? []) {
    mcp.push({
      kind: "mcp",
      mcpServerId: server.id,
      name: server.name,
      serverUrl: server.server_url,
      description: server.description ?? "",
      // Whether Craft can actually authenticate this user against the server,
      // not whether a credential row exists. See `craft_connected`.
      authenticated: server.craft_connected ?? false,
    });
  }

  skills.sort((a, b) => a.slug.localeCompare(b.slug));
  apps.sort((a, b) => compareByName(a, b) || a.externalAppId - b.externalAppId);
  mcp.sort((a, b) => compareByName(a, b) || a.mcpServerId - b.mcpServerId);

  return { commands: [], skills, apps, mcpServers: mcp };
}

export interface SlashTrigger {
  slashIndex: number;
  query: string;
}

// Trigger rules: "/" must be at start-of-text or after whitespace; the query
// (chars between "/" and the cursor) must not contain whitespace.
export function detectSlashTrigger(
  textBeforeCursor: string
): SlashTrigger | null {
  const slashIndex = textBeforeCursor.lastIndexOf("/");
  if (slashIndex === -1) return null;

  if (slashIndex > 0) {
    const prev = textBeforeCursor[slashIndex - 1] ?? "";
    if (!/\s/.test(prev)) return null;
  }

  const query = textBeforeCursor.slice(slashIndex + 1);
  if (/\s/.test(query)) return null;

  return { slashIndex, query };
}

function matchesQuery(entry: PickerEntry, query: string): boolean {
  if (!query) return true;
  let fields: string[];
  switch (entry.kind) {
    case "skill":
      fields = [entry.slug, entry.name, entry.description];
      break;
    case "app":
      fields = [String(entry.externalAppId), entry.name];
      break;
    case "mcp":
      fields = [String(entry.mcpServerId), entry.name, entry.description ?? ""];
      break;
    case "command":
      fields = [entry.slug, entry.name, entry.description];
      break;
  }
  return fields.some((field) => field.toLowerCase().includes(query));
}

export function pickerEntryKey(entry: PickerEntry): string {
  switch (entry.kind) {
    case "skill":
      return `skill:${entry.slug}`;
    case "app":
      return `app:${entry.externalAppId}`;
    case "mcp":
      return `mcp:${entry.mcpServerId}`;
    case "command":
      return `command:${entry.slug}`;
  }
}

export interface SlashSelection {
  skillIds: string[];
  mcpServerIds: number[];
}

export function slashSelectionFromEntries(
  entries: PickerEntry[]
): SlashSelection {
  const skillIds: string[] = [];
  const mcpServerIds: number[] = [];
  for (const entry of entries) {
    if (entry.kind === "skill") {
      skillIds.push(entry.slug);
    } else if (entry.kind === "mcp") {
      mcpServerIds.push(entry.mcpServerId);
    }
  }
  return { skillIds, mcpServerIds };
}

export function pickerEntryPromptPrefix(entry: PickerEntry): string {
  switch (entry.kind) {
    case "skill":
      return `/${entry.slug}`;
    case "app":
      return `[Use external app ${JSON.stringify(entry.name)} (ID: ${entry.externalAppId})]`;
    case "mcp":
      return `[Use the MCP server ${JSON.stringify(entry.name)} and its tools]`;
    case "command":
      return `/${entry.slug}`;
  }
}

type PickerConnectionPath =
  | `${typeof CRAFT_APPS_PATH}?connect=${number}`
  | `${typeof CRAFT_APPS_PATH}?${typeof CRAFT_APPS_TAB_PARAM}=mcp`;

export function pickerEntryConnectionPath(
  entry: PickerEntry
): PickerConnectionPath | null {
  switch (entry.kind) {
    case "skill":
      return null;
    case "app":
      return entry.authenticated
        ? null
        : `${CRAFT_APPS_PATH}?connect=${entry.externalAppId}`;
    // MCP servers have no per-server deep link; land on the MCP tab instead.
    case "mcp":
      return entry.authenticated
        ? null
        : `${CRAFT_APPS_PATH}?${CRAFT_APPS_TAB_PARAM}=mcp`;
    case "command":
      return null;
  }
}

export function filterPickerSections(
  sections: PickerSections,
  query: string
): PickerSections {
  const q = query.trim().toLowerCase();
  if (!q) return sections;
  return {
    commands: sections.commands.filter((c) => matchesQuery(c, q)),
    skills: sections.skills.filter((s) => matchesQuery(s, q)),
    apps: sections.apps.filter((a) => matchesQuery(a, q)),
    mcpServers: sections.mcpServers.filter((m) => matchesQuery(m, q)),
  };
}

// Commands, then skills, then apps, then MCP servers; must match the
// popover's visual render order so keyboard nav indices line up.
export function flattenSections(sections: PickerSections): PickerEntry[] {
  return [
    ...sections.commands,
    ...sections.skills,
    ...sections.apps,
    ...sections.mcpServers,
  ];
}
