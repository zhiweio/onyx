import type { PromptToolHints } from "@/app/craft/constants/exampleBuildPrompts";

export interface HintSkill {
  slug: string;
  name: string;
}

export interface ResolvedToolSelection {
  skillIds: string[];
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
): ResolvedToolSelection {
  const skillIds = (hints?.skillSlugs ?? [])
    .map((hint) => skills.find((skill) => matches(skill.slug, hint))?.slug)
    .filter((slug): slug is string => Boolean(slug));

  // MCP hints are obsolete: servers are enabled globally on
  // /craft/v1/mcp-actions and injected once per session, so example prompts
  // no longer carry per-prompt MCP selections.
  return {
    skillIds: [...new Set(skillIds)],
    useWebSearch: hints?.webSearch ?? false,
  };
}
