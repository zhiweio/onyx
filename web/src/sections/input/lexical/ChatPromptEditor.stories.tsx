import type { Meta, StoryObj } from "@storybook/react-vite";
import { ChatPromptEditor } from "@/sections/input/lexical";
import type { TriggerMenuConfig } from "@/sections/input/lexical";
import type { PickerSections } from "@/lib/skills/picker";

const sections: PickerSections = {
  commands: [
    {
      kind: "command",
      slug: "compact",
      name: "Compact",
      description: "Summarize the conversation to free up context",
    },
  ],
  skills: [
    {
      kind: "skill",
      slug: "pptx",
      name: "pptx",
      description: "Build slide decks",
    },
    {
      kind: "skill",
      slug: "long-doc",
      name: "long-doc",
      description: "Write long structured documents",
    },
  ],
  apps: [
    {
      kind: "app",
      externalAppId: 1,
      name: "Slack",
      appType: "SLACK",
      authenticated: true,
    },
  ],
  mcpServers: [
    {
      kind: "mcp",
      mcpServerId: 1,
      name: "Linear",
      serverUrl: "https://mcp.linear.app/sse",
      authenticated: false,
      description: "Issues and projects",
    },
  ],
  files: [
    {
      kind: "file",
      fileId: "1",
      name: "brand-guidelines.pdf",
      path: "user_library/brand-guidelines.pdf",
      source: "library",
    },
    {
      kind: "file",
      fileId: "2",
      name: "q2-financials.xlsx",
      path: "user_library/q2-financials.xlsx",
      source: "library",
    },
  ],
};

const slashTrigger: TriggerMenuConfig = {
  id: "slash",
  triggerChars: ["/"],
  sections,
  onPick: (entry) => entry.kind === "command",
};

const fileMentions: TriggerMenuConfig = {
  id: "mention-files",
  triggerChars: ["@"],
  sections: { ...sections, commands: [], skills: [], apps: [], mcpServers: [] },
};

const meta: Meta<typeof ChatPromptEditor> = {
  title: "Input/Lexical Prompt Editor",
  component: ChatPromptEditor,
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "Shared Lexical prompt-input kernel. Craft mounts the full form (slash + file mentions, history, drafts); the main chat mounts a light subset.",
      },
    },
  },
};

export default meta;
type Story = StoryObj<typeof ChatPromptEditor>;

export const Light: Story = {
  args: {
    placeholder: "Ask anything",
    historyStorageKey: "storybook-prompt-history-light",
    onSubmit: (text) => {
      // eslint-disable-next-line no-alert
      window.alert(`submit: ${text}`);
    },
  },
};

export const Full: Story = {
  args: {
    placeholder: "Build something — try / for skills, @ for files",
    slashTrigger,
    mentionTriggers: [fileMentions],
    draft: { surface: "storybook", scope: "full" },
    historyStorageKey: "storybook-prompt-history-full",
    dragOverlayHint: "Drop files to attach",
    onDropFiles: (files) => {
      // eslint-disable-next-line no-alert
      window.alert(`drop: ${files.map((file) => file.name).join(", ")}`);
    },
    onSubmit: (text) => {
      // eslint-disable-next-line no-alert
      window.alert(`submit: ${text}`);
    },
  },
};

export const RunningWithQueue: Story = {
  args: {
    placeholder: "Queue a follow-up while the turn runs",
    isRunning: true,
    isInterrupting: false,
    onInterrupt: () => undefined,
    onQueueMessage: (text) => {
      // eslint-disable-next-line no-alert
      window.alert(`queue: ${text}`);
    },
    queuedMessages: [{ id: 1, text: "Then add charts" }],
    onRemoveQueuedMessage: () => undefined,
    onSubmit: () => true,
  },
};
