import type { PromptToolHints } from "@/app/craft/constants/exampleBuildPrompts";

export interface HintSkill {
  slug: string;
  name: string;
}

export interface HintMcpServer {
  mcpServerId: number;
  name: string;
}

export interface ResolvedToolSelection {
  skillIds: string[];
  mcpServerIds: number[];
  useWebSearch: boolean;
}

function matches(reference: string, hint: string): boolean {
  const r = reference.toLowerCase();
  const h = hint.toLowerCase();
  return r.includes(h) || h.includes(r);
}

/**
 * Resolve a prompt's scenario tool hints against what this deployment
 * actually offers. Unmatched references drop out silently — an example
 * still works as plain text when its tools are not installed.
 */
export function resolveToolHints(
  hints: PromptToolHints | undefined,
  skills: HintSkill[],
  mcpServers: HintMcpServer[]
): ResolvedToolSelection {
  const skillIds = (hints?.skillSlugs ?? [])
    .map((hint) => skills.find((skill) => matches(skill.slug, hint))?.slug)
    .filter((slug): slug is string => Boolean(slug));

  const mcpServerIds = (hints?.mcpServerNames ?? [])
    .map(
      (hint) =>
        mcpServers.find((server) => matches(server.name, hint))?.mcpServerId
    )
    .filter((id): id is number => id !== undefined);

  return {
    skillIds: [...new Set(skillIds)],
    mcpServerIds: [...new Set(mcpServerIds)],
    useWebSearch: hints?.webSearch ?? false,
  };
}
