"use client";

import { Text } from "@opal/components";
import { cn } from "@opal/utils";
import { useCaseDomains } from "@/app/craft/constants/exampleBuildPrompts";

export interface ChatExamplePromptsProps {
  onPromptClick: (promptText: string) => void;
}

/**
 * Simple-task entry examples under the chat input, mirroring the craft
 * welcome examples so non-technical users see the same starting points.
 */
export default function ChatExamplePrompts({
  onPromptClick,
}: ChatExamplePromptsProps) {
  const prompts =
    useCaseDomains.find((domain) => domain.id === "financeTax")?.prompts ?? [];
  if (prompts.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-row flex-wrap items-center justify-center gap-2 pt-2">
      {prompts.map((prompt) => (
        <button
          key={prompt.id}
          type="button"
          onClick={() => onPromptClick(prompt.fullText)}
          className={cn(
            "inline-flex items-center rounded-12 px-3 py-1.5 cursor-pointer transition-colors",
            "text-text-03 hover:bg-background-tint-02 hover:text-text-04",
            "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-action-selection-01 focus-visible:ring-offset-2"
          )}
        >
          <Text font="main-ui-body" color="inherit">
            {prompt.summary}
          </Text>
        </button>
      ))}
    </div>
  );
}
