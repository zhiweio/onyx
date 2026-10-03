"use client";

import { useMemo, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { BuildFile } from "@/app/craft/contexts/UploadFilesContext";
import { useVideoBackgroundToggleClick } from "@/app/craft/components/video-background/useVideoBackgroundToggleClick";
import Text from "@/refresh-components/texts/Text";
import { Logo } from "@/lib/app/components";
import CraftComposer from "@/app/craft/components/composer/CraftComposer";
import ModelPickerButton from "@/app/craft/components/ModelPickerButton";
import SuggestedPrompts from "@/app/craft/components/SuggestedPrompts";
import ConnectDataBanner from "@/app/craft/components/ConnectDataBanner";
import CraftLlmSetup from "@/app/craft/onboarding/components/CraftLlmSetup";
import CraftLlmLockedState from "@/app/craft/onboarding/components/CraftLlmLockedState";
import { useOnboarding } from "@/app/craft/onboarding/BuildOnboardingProvider";
import { BuildLlmSelection } from "@/app/craft/onboarding/constants";
import {
  pickerEntriesFromSelection,
  toPickerSections,
  type SlashSelection,
} from "@/lib/skills/picker";
import { resolveToolHints } from "@/lib/skills/toolHints";
import useUserSkills from "@/hooks/useUserSkills";
import useUserExternalApps from "@/hooks/useUserExternalApps";
import { useCraftMcpServers } from "@/lib/tools/hooks";
import { defaultEntryToMention } from "@/sections/input/lexical";
import type { LexicalPromptInputHandle } from "@/sections/input/lexical";
import type { ReasoningEffortOverride } from "@/lib/languageModels/types";
import type { ExamplePromptSelection } from "@/app/craft/constants/exampleBuildPrompts";

interface BuildWelcomeProps {
  onSubmit: (
    message: string,
    files: BuildFile[],
    selection: SlashSelection,
    model?: BuildLlmSelection | null
  ) => void;
  isRunning: boolean;
  /** When true, the composer is disabled while the sandbox starts. */
  sandboxInitializing?: boolean;
  /** Deep-task switch for the first message (long job vs plain turn). */
  deepTask?: boolean;
  onDeepTaskToggle?: () => void;
  thoughtLevel?: {
    value: ReasoningEffortOverride | null;
    onChange: (effort: ReasoningEffortOverride) => void;
    supportsReasoning: boolean;
    supportedEfforts?: ReasoningEffortOverride[];
    effortMax?: ReasoningEffortOverride | null;
    fallback?: ReasoningEffortOverride | null;
  } | null;
}

/**
 * BuildWelcome - Welcome screen shown when no session exists
 *
 * Displays a centered welcome message and composer to start a new build.
 */
export default function BuildWelcome({
  onSubmit,
  isRunning,
  sandboxInitializing = false,
  deepTask = false,
  onDeepTaskToggle,
  thoughtLevel,
}: BuildWelcomeProps) {
  const t = useTranslations("craft.welcome");
  const editorRef = useRef<LexicalPromptInputHandle | null>(null);
  const [selectedModel, setSelectedModel] = useState<BuildLlmSelection | null>(
    null
  );
  const handleWordmarkClick = useVideoBackgroundToggleClick();
  const { isAdmin, hasAnyProvider, isLoading } = useOnboarding();

  const { data: skillsData } = useUserSkills();
  const { data: appsData } = useUserExternalApps();
  const { data: craftMcpData } = useCraftMcpServers();
  const pickerSections = useMemo(
    () => toPickerSections(skillsData, appsData, craftMcpData?.mcp_servers),
    [skillsData, appsData, craftMcpData]
  );

  // Craft can't build without a supported provider: inputs stay gated until
  // one exists (undefined while loading counts as none), and once provider
  // state loads, setup (admins) or the locked notice replaces the prompts.
  const setupPending = !isLoading && !hasAnyProvider;

  const handlePromptClick = (prompt: ExamplePromptSelection) => {
    const handle = editorRef.current;
    if (!handle) {
      return;
    }
    handle.setText(prompt.fullText);
    const resolved = resolveToolHints(
      prompt.toolHints,
      pickerSections.skills,
      pickerSections.mcpServers
    );
    const entries = pickerEntriesFromSelection(pickerSections, {
      skillIds: resolved.skillIds,
      mcpServerIds: resolved.mcpServerIds,
    });
    for (const entry of entries) {
      handle.insertMention(defaultEntryToMention(entry, "/"));
    }
  };

  return (
    // Mirror the main app's empty-state grid (`1fr auto 1fr`) so the composer
    // centers vertically at the same position: wordmark pinned above it, the
    // supporting content below.
    <div
      className="h-full grid px-4"
      style={{ gridTemplateRows: "1fr auto 1fr" }}
    >
      <div className="row-start-1 min-h-0 w-full flex flex-col items-center justify-end">
        <div className="w-full max-w-(--app-page-main-content-width)">
          <div className="flex flex-row items-center justify-between gap-4 pb-6">
            {/* The wordmark's baseline sits ~79% down its box, so nudge it
                down (~0.21 × size) to share craft's baseline. */}
            <button
              type="button"
              className="flex flex-row items-baseline gap-2 select-none"
              onClick={handleWordmarkClick}
            >
              <Logo onyxBranded size={28} className="translate-y-[6px]" />
              <Text
                text05
                style={{
                  fontFamily: "var(--font-kh-teka)",
                  fontWeight: 400,
                  // Sized so the x-height matches the custom "onyx" logotype
                  // (its x-height ≈ 0.595em vs KH Teka's 0.504em at size 28).
                  fontSize: "34px",
                  lineHeight: "1",
                  letterSpacing: "-0.02em",
                }}
              >
                craft
              </Text>
            </button>
            <div className="flex items-center gap-3">
              <ModelPickerButton
                selection={selectedModel}
                onChange={setSelectedModel}
                disabled={!hasAnyProvider}
              />
            </div>
          </div>
        </div>
      </div>

      <div className="row-start-2 w-full flex flex-col items-center">
        <div className="w-full max-w-(--app-page-main-content-width)">
          <CraftComposer
            sessionId={null}
            editorHandleRef={editorRef}
            onSubmit={(message, files, selection) =>
              onSubmit(message, files, selection, selectedModel)
            }
            isRunning={isRunning}
            placeholder={t("input.placeholder")}
            disabled={!hasAnyProvider || sandboxInitializing}
            deepTask={deepTask}
            onDeepTaskToggle={onDeepTaskToggle}
            thoughtLevel={thoughtLevel}
            modelSelection={null}
            onModelChange={() => undefined}
          />
        </div>
      </div>

      <div className="row-start-3 min-h-0 w-full flex flex-col items-center">
        <div className="w-full max-w-(--app-page-main-content-width)">
          {setupPending ? (
            <div className="pt-4">
              {isAdmin ? <CraftLlmSetup /> : <CraftLlmLockedState />}
            </div>
          ) : (
            <>
              <ConnectDataBanner />
              <SuggestedPrompts onPromptClick={handlePromptClick} />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
