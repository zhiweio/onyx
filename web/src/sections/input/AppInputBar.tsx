"use client";

import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useTranslations } from "next-intl";
import { MinimalAgent } from "@/lib/agents/types";
import { LlmManager } from "@/lib/hooks";
import { ChatState } from "@/app/app/interfaces";
import usePromptShortcuts from "@/hooks/usePromptShortcuts";
import { useAvailableSources } from "@/lib/connectors/hooks";
import { MinimalOnyxDocument } from "@/lib/search/interfaces";
import type { ToolConfigurationHandle } from "@/lib/tools/hooks";
import { useAppPosition } from "@/lib/position/hooks";
import { cn } from "@opal/utils";
import { Disabled } from "@opal/core";
import { useUser } from "@/providers/UserProvider";
import { useSettings } from "@/lib/settings/hooks";
import { useProjectsContext } from "@/lib/projects/providers";
import { useActiveProject, useProjects } from "@/lib/projects/hooks";
import { FileCard } from "@/sections/cards/FileCard";
import { ProjectFile, UserFileStatus } from "@/lib/projects/types";
import { ToolsPopover } from "@/lib/tools/components";
import {
  getIconForAction,
  hasSearchToolsAvailable,
} from "@/app/app/services/actionUtils";
import {
  SvgGlobe,
  SvgHourglass,
  SvgMicrophone,
  SvgSearch,
  SvgX,
  SvgSimpleLoader,
} from "@opal/icons";
import { Button, SelectButton, Spacer, Text } from "@opal/components";
import { Section as LayoutSection } from "@/layouts/general-layouts";
import { useQueryController } from "@/providers/QueryControllerProvider";
import { useIncognito } from "@/providers/IncognitoProvider";
import MicrophoneButton from "@/sections/input/MicrophoneButton";
import Waveform from "@/components/voice/Waveform";
import { useVoiceMode } from "@/providers/VoiceModeProvider";
import { useVoiceStatus } from "@/hooks/useVoiceStatus";
import {
  useCurrentQueuedMessages,
  useCurrentLatestMessageRenderComplete,
  useCurrentContextTokensUsed,
  useChatSessionStore,
} from "@/app/app/stores/useChatSessionStore";
import { findModelConfiguration } from "@/lib/languageModels/utils";
import ContextUsageMeter from "@/sections/input/ContextUsageMeter";
import ThoughtLevelSelect from "@/sections/input/ThoughtLevelSelect";
import { DEFAULT_THOUGHT_LEVEL } from "@/sections/input/thoughtLevel";
import {
  ChatPromptEditor,
  clearComposerDraft,
  defaultEntryToMention,
  type ComposerMention,
  type LexicalPromptInputHandle,
} from "@/sections/input/lexical";
import useUserSkills from "@/hooks/useUserSkills";
import { useCraftMcpServers } from "@/lib/tools/hooks";
import {
  pickerEntryConnectionPath,
  toPickerSections,
  type PickerEntry,
  type SlashSelection,
} from "@/lib/skills/picker";
import { uniqueMcpServerIds } from "@/lib/tools/mcpSelection";

export interface AppInputBarHandle {
  reset: () => void;
  focus: () => void;
  setMessage: (message: string) => void;
  setEntries: (entries: PickerEntry[]) => void;
}

export interface AppInputBarProps {
  initialMessage?: string;
  stopGenerating: () => void;
  onSubmit: (message: string, selection?: SlashSelection) => void;
  llmManager: LlmManager;
  chatState: ChatState;
  currentSessionFileTokenCount: number;
  availableContextTokens: number;

  // agents
  activeAgent: MinimalAgent | undefined;

  handleFileUpload: (files: File[]) => void;
  deepResearchEnabled: boolean;
  setPresentingDocument?: (document: MinimalOnyxDocument) => void;
  toggleDeepResearch: () => void;
  isMultiModelActive?: boolean;
  disabled: boolean;
  /**
   * Owned by the surface rather than read here, because the send path reads
   * the same one and two instances would drift.
   */
  toolConfiguration: ToolConfigurationHandle;
  ref?: React.Ref<AppInputBarHandle>;
  // Side panel tab reading
  tabReadingEnabled?: boolean;
  currentTabUrl?: string | null;
  onToggleTabReading?: () => void;
}

/** Slash selection derived from the editor's chips. */
function selectionFromMentions(
  mentions: readonly ComposerMention[],
): SlashSelection {
  const skillIds: string[] = [];
  const mcpServerIds: number[] = [];
  for (const mention of mentions) {
    if (mention.category === "skills") {
      skillIds.push(mention.value);
    } else if (mention.category === "mcp" && /^\d+$/.test(mention.value)) {
      mcpServerIds.push(Number(mention.value));
    }
  }
  return { skillIds, mcpServerIds };
}

const AppInputBar = React.memo(
  ({
    initialMessage = "",
    stopGenerating,
    onSubmit,
    chatState,
    currentSessionFileTokenCount,
    availableContextTokens,
    activeAgent,
    handleFileUpload,
    llmManager,
    deepResearchEnabled,
    toggleDeepResearch,
    isMultiModelActive,
    setPresentingDocument,
    disabled,
    toolConfiguration,
    ref,
    tabReadingEnabled,
    currentTabUrl,
    onToggleTabReading,
  }: AppInputBarProps) => {
    const t = useTranslations("chat.input");
    const { incognitoEnabled } = useIncognito();
    const [isRecording, setIsRecording] = useState(false);
    const [recordingCycleCount, setRecordingCycleCount] = useState(0);
    const [isMuted, setIsMuted] = useState(false);
    const [audioLevel, setAudioLevel] = useState(0);
    const stopRecordingRef = useRef<(() => Promise<string | null>) | null>(
      null,
    );
    const setMutedRef = useRef<((muted: boolean) => void) | null>(null);
    const queuedMessages = useCurrentQueuedMessages();
    const latestMessageRenderComplete = useCurrentLatestMessageRenderComplete();
    const enqueueCurrentMessage = useChatSessionStore(
      (state) => state.enqueueCurrentMessage,
    );
    const removeCurrentQueuedMessage = useChatSessionStore(
      (state) => state.removeCurrentQueuedMessage,
    );
    const { user, isAdmin } = useUser();
    const isAutoSending = useRef(false);

    const editorRef = useRef<LexicalPromptInputHandle | null>(null);
    // Mirror of the editor markdown for placeholder/search gating and the
    // mic flow; the submit path always reads the live editor text.
    const [message, setMessage] = useState(initialMessage);
    const isRecordingRef = useRef(isRecording);

    const { data: skillsData } = useUserSkills();
    const { data: craftMcpData } = useCraftMcpServers();
    const pickerSections = useMemo(
      () => toPickerSections(skillsData, undefined, craftMcpData?.mcp_servers),
      [skillsData, craftMcpData],
    );

    const { activePromptShortcuts } = usePromptShortcuts();
    const shortcutsEnabled = user?.preferences?.shortcut_enabled ?? false;
    // Custom prompt shortcuts ride the shared slash menu as commands: typing
    // "/" lists skills, MCP servers, and the user's saved prompts together.
    const promptCommands = useMemo(() => {
      if (!shortcutsEnabled) {
        return [];
      }
      return activePromptShortcuts.map((prompt) => ({
        kind: "command" as const,
        slug: prompt.prompt,
        name: prompt.prompt,
        description: prompt.content?.trim() ?? "",
      }));
    }, [activePromptShortcuts, shortcutsEnabled]);

    const slashTrigger = useMemo(
      () => ({
        id: "app-slash",
        triggerChars: ["/"] as const,
        sections: {
          ...pickerSections,
          commands: promptCommands,
        },
        onPick: (entry: PickerEntry): boolean => {
          if (entry.kind === "command") {
            const prompt = activePromptShortcuts.find(
              (candidate) => candidate.prompt === entry.slug,
            );
            const content = prompt?.content ?? "";
            editorRef.current?.setText(content);
            setMessage(content);
            return true;
          }
          const connectionPath = pickerEntryConnectionPath(entry);
          if (connectionPath) {
            window.location.assign(connectionPath);
            return true;
          }
          if (entry.kind === "mcp") {
            // Picking an MCP server both inserts the chip and enables the
            // server for the next message, matching the tools toggle.
            toolConfiguration.setMcpServerEnabled(entry.mcpServerId, true);
          }
          return false;
        },
      }),
      [
        pickerSections,
        promptCommands,
        activePromptShortcuts,
        toolConfiguration,
      ],
    );

    const { state } = useQueryController();
    const isClassifying = state.phase === "classifying";
    const isSearchActive =
      state.phase === "searching" || state.phase === "search-results";
    const {
      stopTTS,
      isTTSPlaying,
      isManualTTSPlaying,
      isTTSLoading,
      isAwaitingAutoPlaybackStart,
      isTTSMuted,
      toggleTTSMute,
    } = useVoiceMode();
    const { sttEnabled } = useVoiceStatus();
    // Show mic button: always if STT configured, or greyed-out for admins to prompt setup
    const showMicButton = sttEnabled || isAdmin;
    const isVoicePlaybackActive =
      isTTSPlaying || isTTSLoading || isAwaitingAutoPlaybackStart;
    const isVoicePlaybackControllable = isVoicePlaybackActive && !isRecording;
    const isTTSActuallySpeaking = isTTSPlaying || isManualTTSPlaying;
    const appPosition = useAppPosition();
    const isNewSession = appPosition.isNewSession();
    const appMode = state.phase === "idle" ? state.appMode : undefined;
    const isSearchMode =
      (isNewSession && appMode === "search") || isSearchActive;

    const activePlaceholder =
      queuedMessages.length > 0 && !message
        ? t("appInputBar.input.queuedPlaceholder")
        : isRecording
          ? t("appInputBar.input.listeningPlaceholder")
          : isVoicePlaybackActive
            ? t("appInputBar.input.speakingPlaceholder")
            : isSearchMode
              ? t("appInputBar.input.searchPlaceholder")
              : t("appInputBar.input.placeholder");

    const chatSessionId = appPosition.chat();
    const draftScope = chatSessionId ?? "new";
    const prevDraftScopeRef = useRef(draftScope);

    useEffect(() => {
      isRecordingRef.current = isRecording;
    }, [isRecording]);

    const handleRecordingChange = useCallback((nextIsRecording: boolean) => {
      const wasRecording = isRecordingRef.current;
      isRecordingRef.current = nextIsRecording;
      if (!wasRecording && nextIsRecording) {
        setRecordingCycleCount((count) => count + 1);
      }
      setIsRecording(nextIsRecording);
    }, []);

    // Submit wrapper: stops TTS first to prevent overlapping voices.
    const handleSubmit = useCallback(
      (text: string): boolean => {
        if (!text.trim()) {
          return false;
        }
        stopTTS();
        const slash = selectionFromMentions(
          editorRef.current?.getMentions() ?? [],
        );
        onSubmit(text, {
          skillIds: slash.skillIds,
          mcpServerIds: uniqueMcpServerIds(
            slash.mcpServerIds,
            toolConfiguration.selectedMcpServerIds,
          ),
        });
        clearComposerDraft("chat", draftScope);
        return true;
      },
      [stopTTS, onSubmit, toolConfiguration.selectedMcpServerIds, draftScope],
    );

    const handleQueueMessage = useCallback(
      (text: string): boolean => {
        enqueueCurrentMessage(text.trim());
        // Drop the draft now; a reload could outrace the debounced empty-save.
        clearComposerDraft("chat", draftScope);
        return true;
      },
      [enqueueCurrentMessage, draftScope],
    );

    const handleEditorChange = useCallback((text: string) => {
      setMessage(text);
    }, []);

    // Sync non-empty prop changes into the editor (e.g. NRFPage reads URL
    // params after mount). Clearing is handled via the imperative reset().
    useEffect(() => {
      if (initialMessage) {
        editorRef.current?.setText(initialMessage);
        setMessage(initialMessage);
      }
    }, [initialMessage]);

    // Session switch: clear leftover text so the previous chat's draft cannot
    // leak into the new one.
    useEffect(() => {
      if (prevDraftScopeRef.current !== draftScope) {
        prevDraftScopeRef.current = draftScope;
        editorRef.current?.clear();
        setMessage("");
      }
    }, [draftScope]);

    // Expose reset and focus methods to parent via ref
    React.useImperativeHandle(ref, () => ({
      reset: () => {
        if (!isAutoSending.current) {
          editorRef.current?.clear();
          setMessage("");
          clearComposerDraft("chat", draftScope);
        }
      },
      focus: () => {
        editorRef.current?.focus();
      },
      setMessage: (nextMessage: string) => {
        editorRef.current?.setText(nextMessage);
        setMessage(nextMessage);
        editorRef.current?.focus();
      },
      setEntries: (entries: PickerEntry[]) => {
        for (const entry of entries) {
          if (entry.kind === "mcp") {
            toolConfiguration.setMcpServerEnabled(entry.mcpServerId, true);
          }
          editorRef.current?.insertMention(defaultEntryToMention(entry, "/"));
        }
      },
    }));

    const { forcedToolId, clearForcedTool } = toolConfiguration;
    const { currentMessageFiles, setCurrentMessageFiles } =
      useProjectsContext();
    const { isLoading: isLoadingProjects } = useProjects();
    const activeProject = useActiveProject();

    const currentIndexingFiles = useMemo(() => {
      return currentMessageFiles.filter(
        (file) => file.status === UserFileStatus.PROCESSING,
      );
    }, [currentMessageFiles]);

    const hasUploadingFiles = useMemo(() => {
      return currentMessageFiles.some(
        (file) => file.status === UserFileStatus.UPLOADING,
      );
    }, [currentMessageFiles]);

    // A file isn't queryable until indexing completes, so gate send on it.
    const hasIndexingFiles = currentIndexingFiles.length > 0;

    // Convert ProjectFile to MinimalOnyxDocument format for viewing
    const handleFileClick = useCallback(
      (file: ProjectFile) => {
        if (!setPresentingDocument) return;

        const documentForViewer: MinimalOnyxDocument = {
          document_id: `project_file__${file.file_id}`,
          semantic_identifier: file.name,
        };

        setPresentingDocument(documentForViewer);
      },
      [setPresentingDocument],
    );

    const handleRemoveMessageFile = useCallback(
      (fileId: string) => {
        setCurrentMessageFiles((prev) => prev.filter((f) => f.id !== fileId));
      },
      [setCurrentMessageFiles],
    );

    const combinedSettingsData = useSettings();

    const prevChatStateRef = useRef(chatState);
    const prevRenderCompleteRef = useRef(latestMessageRenderComplete);

    useEffect(() => {
      // "Ready" requires the backend to be idle AND the previous answer
      // to have finished drawing on screen. Without the render-complete
      // gate, a queued follow-up fires while the smooth-streaming
      // typewriter is still flushing the prior answer.
      const wasReady =
        prevChatStateRef.current === "input" && prevRenderCompleteRef.current;
      const isReady = chatState === "input" && latestMessageRenderComplete;

      prevChatStateRef.current = chatState;
      prevRenderCompleteRef.current = latestMessageRenderComplete;

      if (!wasReady && isReady && queuedMessages.length > 0) {
        const nextMessage = queuedMessages[0]!.text;
        isAutoSending.current = true;
        stopTTS();
        onSubmit(nextMessage);
        isAutoSending.current = false;
        removeCurrentQueuedMessage(0);
      }
    }, [
      chatState,
      latestMessageRenderComplete,
      queuedMessages,
      removeCurrentQueuedMessage,
      stopTTS,
      onSubmit,
    ]);

    const { isLoading: sourcesLoading } = useAvailableSources();

    // Bottom controls are hidden until all data is loaded
    const controlsLoading =
      sourcesLoading || !activeAgent || llmManager.isLoadingProviders;
    const currentModel = useMemo(() => {
      const providers = llmManager.llmProviders ?? [];
      const { modelConfigurationId, modelName, name } = llmManager.currentLlm;
      if (modelConfigurationId != null) {
        for (const provider of providers) {
          const model = provider.model_configurations.find(
            (candidate) => candidate.id === modelConfigurationId,
          );
          if (model) return model;
        }
      }
      return (
        findModelConfiguration(providers, modelName, name) ??
        findModelConfiguration(providers, modelName)
      );
    }, [
      llmManager.llmProviders,
      llmManager.currentLlm.modelConfigurationId,
      llmManager.currentLlm.modelName,
      llmManager.currentLlm.name,
    ]);
    const contextTokensUsed = useCurrentContextTokensUsed();

    const isGenerating = chatState !== "input";
    const canStopGeneration = isGenerating || isVoicePlaybackControllable;

    const handleStopGeneration = useCallback(() => {
      stopTTS({ manual: true });
      if (chatState !== "input") {
        stopGenerating();
      }
    }, [chatState, stopGenerating, stopTTS]);

    const shouldShowRecordingWaveformBelow =
      isRecording &&
      !isVoicePlaybackActive &&
      (isNewSession || recordingCycleCount === 1);

    // Determine if we should hide processing state based on context limits
    const hideProcessingState = useMemo(() => {
      if (currentMessageFiles.length > 0 && currentIndexingFiles.length > 0) {
        // token_count is null until indexing finishes; don't hide the
        // processing indicator while a file's size is still unknown.
        const allTokenCountsKnown = currentIndexingFiles.every(
          (file) => file.token_count !== null,
        );
        if (!allTokenCountsKnown) {
          return false;
        }
        const currentFilesTokenTotal = currentMessageFiles.reduce(
          (acc, file) => acc + (file.token_count || 0),
          0,
        );
        const totalTokens =
          (currentSessionFileTokenCount || 0) + currentFilesTokenTotal;
        // Hide processing state when files are within context limits
        return totalTokens < availableContextTokens;
      }
      return false;
    }, [
      currentMessageFiles,
      currentSessionFileTokenCount,
      currentIndexingFiles,
      availableContextTokens,
    ]);

    const shouldCompactImages = useMemo(() => {
      return currentMessageFiles.length > 1;
    }, [currentMessageFiles]);

    // Check if the agent has search tools available (internal search or web search)
    // AND if deep research is globally enabled in admin settings
    const showDeepResearch = useMemo(() => {
      const deepResearchGloballyEnabled =
        combinedSettingsData?.deep_research_enabled ?? true;

      // Resolved from the chat, not the URL. `projectId` is dropped once a chat
      // opens (`PARAMS_TO_SKIP` in `app/app/services/lib.tsx`), so a project
      // chat carries no project context in its URL — reading the search param
      // hid the toggle on the project page and left it showing in the one place
      // it actually breaks.
      // Loading counts as "unknown", and unknown withholds: an unloaded
      // projects list makes a project chat look like a normal one.
      const isProjectWorkflow = isLoadingProjects || activeProject !== null;

      // TODO(@yuhong): Re-enable Deep Research in Projects workflow once it is fully supported.
      // https://linear.app/onyx-app/issue/ENG-3818/re-enable-deep-research-in-projects
      return (
        !isProjectWorkflow &&
        deepResearchGloballyEnabled &&
        hasSearchToolsAvailable(activeAgent?.tools || [])
      );
    }, [
      activeAgent?.tools,
      combinedSettingsData?.deep_research_enabled,
      activeProject,
      isLoadingProjects,
    ]);

    const attachedFiles = !isSearchMode && currentMessageFiles.length > 0 && (
      <div className="flex flex-wrap gap-1 p-1">
        {currentMessageFiles.map((file) => (
          <FileCard
            key={file.id}
            file={file}
            removeFile={handleRemoveMessageFile}
            hideProcessingState={hideProcessingState}
            onFileClick={handleFileClick}
            compactImages={shouldCompactImages}
          />
        ))}
      </div>
    );

    // Toolbar slots keep the existing /app controls; search mode hides the
    // chat-only ones exactly like the old controls row did.
    const controlsHiddenClass = cn(
      "flex flex-row items-center",
      isSearchMode && "hidden",
      controlsLoading && "invisible",
    );

    const toolbarLeading = (
      <div className={controlsHiddenClass}>
        {activeAgent && (
          // Keyed, so switching agents starts clean rather than carrying
          // the previous agent's open panel and search term across.
          <ToolsPopover
            key={activeAgent.id}
            agent={activeAgent}
            toolConfiguration={toolConfiguration}
            disabled={disabled}
          />
        )}
        {onToggleTabReading ? (
          <SelectButton
            disabled={disabled}
            icon={SvgGlobe}
            onClick={onToggleTabReading}
            state={tabReadingEnabled ? "selected" : "empty"}
          >
            {tabReadingEnabled
              ? currentTabUrl
                ? (() => {
                    try {
                      return new URL(currentTabUrl).hostname;
                    } catch {
                      return currentTabUrl;
                    }
                  })()
                : t("appInputBar.tabReadingButton.readingLabel")
              : t("appInputBar.tabReadingButton.readLabel")}
          </SelectButton>
        ) : (
          showDeepResearch && (
            <SelectButton
              disabled={disabled || isMultiModelActive}
              variant="select-light"
              icon={SvgHourglass}
              onClick={toggleDeepResearch}
              state={deepResearchEnabled ? "selected" : "empty"}
              foldable={!deepResearchEnabled}
              tooltip={
                isMultiModelActive
                  ? t("appInputBar.deepResearchButton.disabledTooltip")
                  : undefined
              }
            >
              {t("appInputBar.deepResearchButton.label")}
            </SelectButton>
          )
        )}

        {(() => {
          if (!activeAgent || forcedToolId === null) return null;
          const tool = activeAgent.tools.find(
            (tool) => tool.id === forcedToolId,
          );
          if (!tool) return null;
          return (
            <Disabled disabled={disabled}>
              <SelectButton
                variant="select-light"
                icon={getIconForAction(tool)}
                onClick={clearForcedTool}
                state="selected"
              >
                {tool.display_name}
              </SelectButton>
            </Disabled>
          );
        })()}
      </div>
    );

    const toolbarTrailing = !isSearchMode && (
      <>
        <ContextUsageMeter
          usedTokens={contextTokensUsed}
          contextLimit={currentModel?.max_input_tokens ?? null}
        />
        <ThoughtLevelSelect
          value={llmManager.reasoningEffort}
          onChange={(effort) => llmManager.updateReasoningEffort(effort)}
          supportsReasoning={currentModel?.supports_reasoning ?? false}
          supportedEfforts={currentModel?.supported_reasoning_efforts}
          effortMax={currentModel?.reasoning_effort_max}
          fallback={DEFAULT_THOUGHT_LEVEL}
          disabled={disabled}
        />
        {showMicButton &&
          (sttEnabled ? (
            <MicrophoneButton
              onTranscription={(text) => {
                editorRef.current?.setText(text);
                setMessage(text);
              }}
              disabled={disabled || chatState === "streaming"}
              autoSend={user?.preferences?.voice_auto_send ?? false}
              autoListen={user?.preferences?.voice_auto_playback ?? false}
              isNewSession={isNewSession}
              chatState={chatState}
              onRecordingChange={handleRecordingChange}
              stopRecordingRef={stopRecordingRef}
              currentMessage={message}
              onRecordingStart={() => {}}
              onAutoSend={(text) => {
                handleSubmit(text);
                editorRef.current?.clear();
                setMessage("");
              }}
              onMuteChange={setIsMuted}
              setMutedRef={setMutedRef}
              onAudioLevel={setAudioLevel}
            />
          ) : (
            <Button
              disabled
              icon={SvgMicrophone}
              aria-label={t("appInputBar.voiceSetupButton.ariaLabel")}
              prominence="tertiary"
              tooltip={t("appInputBar.voiceSetupButton.tooltip")}
            />
          ))}
      </>
    );

    return (
      <>
        <Disabled disabled={disabled} allowClick>
          <div id="onyx-chat-input" className="relative w-full">
            {/* Voice waveform overlay (positioned outside normal flow to avoid resizing input) */}
            {isTTSActuallySpeaking ? (
              <div className="absolute bottom-full mb-1 start-1 z-10">
                <Waveform
                  variant="speaking"
                  isActive={isTTSActuallySpeaking}
                  isMuted={isTTSMuted}
                  onMuteToggle={toggleTTSMute}
                />
              </div>
            ) : isRecording &&
              !isVoicePlaybackActive &&
              !shouldShowRecordingWaveformBelow ? (
              <div className="absolute bottom-full mb-1 start-1 end-1 z-10">
                <Waveform
                  variant="recording"
                  isActive={isRecording}
                  isMuted={isMuted}
                  audioLevel={audioLevel}
                  onMuteToggle={() => {
                    setMutedRef.current?.(!isMuted);
                  }}
                />
              </div>
            ) : null}

            <ChatPromptEditor
              placeholder={activePlaceholder}
              disabled={disabled}
              submitBlocked={hasUploadingFiles || hasIndexingFiles}
              isRunning={canStopGeneration}
              isBusy={isClassifying}
              onInterrupt={handleStopGeneration}
              onSubmit={handleSubmit}
              onQueueMessage={handleQueueMessage}
              queuedMessages={queuedMessages}
              onRemoveQueuedMessage={removeCurrentQueuedMessage}
              historyStorageKey={`onyx-prompt-history:chat:${user?.id ?? "anonymous"}`}
              draft={{ surface: "chat", scope: draftScope }}
              slashTrigger={slashTrigger}
              pasteTilesEnabled={user?.preferences?.paste_as_tile ?? false}
              topContent={attachedFiles}
              toolbarLeading={toolbarLeading}
              toolbarTrailing={toolbarTrailing}
              submitButtonId="onyx-chat-input-send-button"
              inputTestId="onyx-chat-input-textbox"
              inputId="onyx-chat-input-textbox"
              editorRef={editorRef}
              initialValue={initialMessage}
              onPasteFiles={handleFileUpload}
              submitControl={
                isSearchMode ? (
                  <LayoutSection flexDirection="row" width="fit" gap={0}>
                    <Button
                      disabled={!message || isClassifying}
                      icon={SvgX}
                      onClick={() => {
                        editorRef.current?.clear();
                        setMessage("");
                      }}
                      prominence="tertiary"
                    />
                    <Button
                      disabled={!message || isClassifying || hasUploadingFiles}
                      id="onyx-chat-input-send-button"
                      icon={isClassifying ? SvgSimpleLoader : SvgSearch}
                      onClick={() => {
                        if (chatState == "streaming") {
                          stopGenerating();
                        } else if (message) {
                          handleSubmit(editorRef.current?.getText() ?? message);
                          editorRef.current?.clear();
                          setMessage("");
                        }
                      }}
                      prominence="tertiary"
                    />
                    <Spacer orientation="horizontal" rem={0.25} />
                  </LayoutSection>
                ) : undefined
              }
            />

            {/* First recording cycle waveform below input */}
            {shouldShowRecordingWaveformBelow && (
              <div className="absolute top-full mt-1 start-1 end-1 z-10">
                <Waveform
                  variant="recording"
                  isActive={isRecording}
                  isMuted={isMuted}
                  audioLevel={audioLevel}
                  onMuteToggle={() => {
                    setMutedRef.current?.(!isMuted);
                  }}
                />
              </div>
            )}
          </div>
        </Disabled>
        {/* Stays for the whole session: the warning is most relevant
            once the user is actually chatting. */}
        {incognitoEnabled && (
          <LayoutSection
            flexDirection="column"
            alignItems="center"
            height="fit"
            gap={0.125}
            className="mt-3 text-center"
          >
            <Text font="secondary-body" color="text-02">
              {t("appInputBar.incognitoNotice.text")}
            </Text>
            <Text font="secondary-body" color="text-02">
              {t("appInputBar.incognitoPolicyNotice.text")}
            </Text>
          </LayoutSection>
        )}
      </>
    );
  },
);
AppInputBar.displayName = "AppInputBar";

export default AppInputBar;
