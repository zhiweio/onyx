"use client";

import { useMemo } from "react";
import { useTranslations } from "next-intl";
import { Text } from "@opal/components";
import { cn } from "@opal/utils";
import {
  useCaseDomains,
  type PromptToolHints,
} from "@/app/craft/constants/exampleBuildPrompts";
import {
  pickerEntriesFromSelection,
  toPickerSections,
  type PickerEntry,
} from "@/lib/skills/picker";
import { resolveToolHints } from "@/lib/skills/toolHints";
import useUserSkills from "@/hooks/useUserSkills";
import useUserExternalApps from "@/hooks/useUserExternalApps";
import { useMcpServers } from "@/lib/tools/hooks";

/** Chips shown under the main chat input: the financeTax examples first,
 * then the opening prompt of each remaining domain. */
const MAX_EXAMPLES = 6;

function selectExamplePromptIds(): { domainId: string; promptId: string }[] {
  const picked: { domainId: string; promptId: string }[] = [];
  for (const domain of useCaseDomains) {
    // The primary domain contributes its whole set; the others contribute
    // one opener each.
    const prompts =
      domain.id === "financeTax" ? domain.prompts : domain.prompts.slice(0, 1);
    for (const prompt of prompts) {
      picked.push({ domainId: domain.id, promptId: prompt.id });
    }
  }
  return picked.slice(0, MAX_EXAMPLES);
}

export interface ChatExamplePrompt {
  fullText: string;
  /** Skill / MCP chips to seed in the input bar before sending. */
  entries: PickerEntry[];
  /** Whether the scenario wants fresh web results (deep research). */
  webSearch: boolean;
}

export interface ChatExamplePromptsProps {
  onPromptClick: (prompt: ChatExamplePrompt) => void;
}

/**
 * Entry examples under the chat input, localized through the same catalog as
 * the craft welcome examples. Scenario tool hints resolve against the skills
 * and MCP servers this deployment actually offers.
 */
export default function ChatExamplePrompts({
  onPromptClick,
}: ChatExamplePromptsProps) {
  const t = useTranslations("craft.suggestedPrompts");
  const { data: skillsData } = useUserSkills();
  const { data: appsData } = useUserExternalApps();
  const { mcpData } = useMcpServers();

  const sections = useMemo(
    () => toPickerSections(skillsData, appsData, mcpData?.mcp_servers),
    [skillsData, appsData, mcpData]
  );

  const examples = useMemo(
    () =>
      selectExamplePromptIds().map(({ domainId, promptId }) => {
        const domain = useCaseDomains.find((d) => d.id === domainId);
        const prompt = domain?.prompts.find((p) => p.id === promptId);
        const hints: PromptToolHints | undefined = prompt?.toolHints;
        const resolved = resolveToolHints(
          hints,
          sections.skills,
          sections.mcpServers
        );
        return {
          domainId,
          promptId,
          summary: t(`${domainId}.prompts.${promptId}.summary`),
          fullText: t(`${domainId}.prompts.${promptId}.fullText`),
          entries: pickerEntriesFromSelection(sections, {
            skillIds: resolved.skillIds,
            mcpServerIds: resolved.mcpServerIds,
          }),
          webSearch: resolved.useWebSearch,
        };
      }),
    [t, sections]
  );

  if (examples.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-row flex-wrap items-center justify-center gap-2 pt-2">
      {examples.map((example) => (
        <button
          key={`${example.domainId}.${example.promptId}`}
          type="button"
          onClick={() =>
            onPromptClick({
              fullText: example.fullText,
              entries: example.entries,
              webSearch: example.webSearch,
            })
          }
          className={cn(
            "inline-flex items-center rounded-12 px-3 py-1.5 cursor-pointer transition-colors",
            "text-text-03 hover:bg-background-tint-02 hover:text-text-04",
            "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-action-selection-01 focus-visible:ring-offset-2"
          )}
        >
          <Text font="main-ui-body" color="inherit">
            {example.summary}
          </Text>
        </button>
      ))}
    </div>
  );
}
