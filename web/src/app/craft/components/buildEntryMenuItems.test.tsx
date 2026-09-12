import {
  buildEntryMenuItems,
  type EntryMenuTranslate,
} from "@/app/craft/components/buildEntryMenuItems";
import type { PickerSections } from "@/lib/skills/picker";
import {
  CRAFT_MCP_ACTIONS_PATH,
  CRAFT_SKILLS_PATH,
} from "@/app/craft/v1/constants";

function sections(over: Partial<PickerSections> = {}): PickerSections {
  return { commands: [], skills: [], apps: [], mcpServers: [], ...over };
}

const ACME_APP = {
  kind: "app" as const,
  externalAppId: 3,
  name: "Acme CRM",
  appType: "CUSTOM" as const,
  authenticated: true,
};

const ASANA_MCP = {
  kind: "mcp" as const,
  mcpServerId: 8,
  name: "Asana MCP",
  serverUrl: "https://mcp.asana.com/mcp",
  authenticated: true,
};

const PPTX_SKILL = {
  kind: "skill" as const,
  slug: "pptx",
  name: "PPTX",
  description: "Build PowerPoint decks.",
};

// Identity translator keeps assertions on stable key names.
const tStub = ((key: string) => key) as unknown as EntryMenuTranslate;

function handlers(
  over: Partial<Parameters<typeof buildEntryMenuItems>[1]> = {}
) {
  return {
    onAttachFiles: jest.fn(),
    onSelectEntry: jest.fn(),
    onRemoveEntry: jest.fn(),
    ...over,
  };
}

function panel(items: ReturnType<typeof buildEntryMenuItems>, key: string) {
  return items.find((item) => item?.key === key)?.panel;
}

describe("buildEntryMenuItems", () => {
  it("exposes MCP instead of Apps, with apps and MCP servers in one list", () => {
    const items = buildEntryMenuItems(
      sections({ apps: [ACME_APP], mcpServers: [ASANA_MCP] }),
      handlers(),
      tStub
    );

    expect(items.find((item) => item?.key === "apps")).toBeUndefined();
    expect(panel(items, "mcp")?.rows.map((row) => row.label)).toEqual([
      "Acme CRM",
      "Asana MCP",
    ]);
    expect(panel(items, "mcp")?.manageHref).toBe(CRAFT_MCP_ACTIONS_PATH);
  });

  it("toggles an MCP row on and off without treating it as a one-shot click", () => {
    const onSelectEntry = jest.fn();
    const onRemoveEntry = jest.fn();
    const items = buildEntryMenuItems(
      sections({ mcpServers: [ASANA_MCP] }),
      handlers({
        onSelectEntry,
        onRemoveEntry,
        activeEntries: [ASANA_MCP],
      }),
      tStub
    );
    const row = panel(items, "mcp")?.rows[0];

    expect(row?.checked).toBe(true);
    row?.onCheckedChange(false);
    expect(onRemoveEntry).toHaveBeenCalledWith("mcp:8");
    expect(onSelectEntry).not.toHaveBeenCalled();
  });

  it("selects an unauthenticated connection when its switch is turned on", () => {
    const onSelectEntry = jest.fn();
    const items = buildEntryMenuItems(
      sections({
        apps: [{ ...ACME_APP, authenticated: false }],
      }),
      handlers({ onSelectEntry }),
      tStub
    );
    const row = panel(items, "mcp")?.rows[0];

    expect(row?.checked).toBe(false);
    expect(row?.description).toBe("connect.hint");
    row?.onCheckedChange(true);
    expect(onSelectEntry).toHaveBeenCalledWith({
      ...ACME_APP,
      authenticated: false,
    });
  });

  it("lists skills with a manage link to the skills page", () => {
    const items = buildEntryMenuItems(
      sections({ skills: [PPTX_SKILL] }),
      handlers(),
      tStub
    );
    const skills = panel(items, "skills");

    expect(skills?.rows.map((row) => row.label)).toEqual(["PPTX"]);
    expect(skills?.manageHref).toBe(CRAFT_SKILLS_PATH);
  });

  it("keeps library files behind a manage action that opens the existing modal", () => {
    const onManageLibrary = jest.fn();
    const items = buildEntryMenuItems(
      sections(),
      handlers({
        onManageLibrary,
        libraryFiles: [{ id: "file-1", name: "notes.pdf" }],
      }),
      tStub
    );
    const library = panel(items, "library");

    expect(library?.rows.map((row) => row.label)).toEqual(["notes.pdf"]);
    expect(library?.manageHref).toBeUndefined();
    library?.onManage?.();
    expect(onManageLibrary).toHaveBeenCalledTimes(1);
  });
});
