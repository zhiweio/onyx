import type { Meta, StoryObj } from "@storybook/react-vite";
import {
  SvgFileText,
  SvgFolder,
  SvgMcp,
  SvgPaperclip,
  SvgSparkle,
} from "@opal/icons";
import {
  PlusMenuButton,
  type PlusMenuItem,
} from "@/sections/input/PlusMenuButton";

const filesItem: PlusMenuItem = {
  key: "files",
  icon: SvgPaperclip,
  label: "Add files or photos",
  onSelect: () => console.log("attach files"),
};

const skillsItem: PlusMenuItem = {
  key: "skills",
  icon: SvgSparkle,
  label: "Skills",
  panel: {
    searchPlaceholder: "Search skills...",
    manageLabel: "Manage",
    manageHref: "/craft/v1/skills",
    manageTarget: "_blank",
    emptyLabel: "No skills yet.",
    rows: [
      {
        key: "pptx",
        icon: SvgSparkle,
        label: "PPTX",
        description: "Build PowerPoint decks.",
        checked: true,
        onCheckedChange: (checked) => console.log("pptx", checked),
      },
      {
        key: "pdf",
        icon: SvgSparkle,
        label: "PDF",
        description: "Fill and read PDFs.",
        checked: false,
        onCheckedChange: (checked) => console.log("pdf", checked),
      },
    ],
  },
};

const mcpItem: PlusMenuItem = {
  key: "mcp",
  icon: SvgMcp,
  label: "MCP",
  panel: {
    searchPlaceholder: "Search MCPs...",
    manageLabel: "Manage",
    manageHref: "/craft/v1/mcp-actions",
    manageTarget: "_blank",
    emptyLabel: "No MCP servers yet.",
    rows: [
      {
        key: "context7",
        icon: SvgMcp,
        label: "Context7",
        checked: true,
        onCheckedChange: (checked) => console.log("context7", checked),
      },
      {
        key: "deepwiki",
        icon: SvgMcp,
        label: "DeepWiki",
        checked: false,
        onCheckedChange: (checked) => console.log("deepwiki", checked),
      },
    ],
  },
};

const libraryItem: PlusMenuItem = {
  key: "library",
  icon: SvgFolder,
  label: "Library",
  panel: {
    searchPlaceholder: "Search library...",
    manageLabel: "Manage",
    onManage: () => console.log("manage library"),
    emptyLabel: "No files yet.",
    rows: [
      {
        key: "notes",
        icon: SvgFileText,
        label: "notes.pdf",
        checked: false,
        onCheckedChange: () => console.log("manage library"),
      },
    ],
  },
};

const meta: Meta<typeof PlusMenuButton> = {
  title: "Apps/Craft/Input Bar/Plus Menu Button",
  component: PlusMenuButton,
  tags: ["autodocs"],
  decorators: [
    (Story) => (
      <div className="w-[400px] p-8 flex justify-start">
        <Story />
      </div>
    ),
  ],
};

export default meta;
type Story = StoryObj<typeof PlusMenuButton>;

export const Default: Story = {
  args: { items: [filesItem, skillsItem, mcpItem, libraryItem] },
};

export const SkillsOnly: Story = {
  args: { items: [filesItem, skillsItem] },
};

export const ActionsOnly: Story = {
  args: { items: [filesItem] },
};

export const Disabled: Story = {
  args: {
    items: [filesItem, skillsItem, mcpItem, libraryItem],
    disabled: true,
  },
};
