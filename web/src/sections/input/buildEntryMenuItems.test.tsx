import {
  buildEntryMenuItems,
  type EntryMenuTranslate,
} from "@/sections/input/buildEntryMenuItems";
import { CRAFT_LIBRARY_PATH } from "@/app/craft/v1/constants";

// Identity translator keeps assertions on stable key names.
const tStub = ((key: string) => key) as unknown as EntryMenuTranslate;

function handlers(
  over: Partial<Parameters<typeof buildEntryMenuItems>[0]> = {}
) {
  return {
    onAttachFiles: jest.fn(),
    ...over,
  };
}

function panel(items: ReturnType<typeof buildEntryMenuItems>, key: string) {
  return items.find((item) => item?.key === key)?.panel;
}

describe("buildEntryMenuItems", () => {
  it("exposes attach-files and the library; no skills/mcp panels", () => {
    const items = buildEntryMenuItems(handlers(), tStub);

    expect(items.find((item) => item?.key === "files")).toBeDefined();
    expect(items.find((item) => item?.key === "library")).toBeDefined();
    // Skills and MCP selection moved to the composer menus (/ and $) and the
    // mcp-actions page respectively.
    expect(items.find((item) => item?.key === "skills")).toBeUndefined();
    expect(items.find((item) => item?.key === "mcp")).toBeUndefined();
  });

  it("lists library files with a manage link to the library page", () => {
    const items = buildEntryMenuItems(
      handlers({
        libraryFiles: [
          {
            id: "file-1",
            name: "notes.pdf",
            checked: false,
            onToggle: jest.fn(),
          },
        ],
      }),
      tStub
    );
    const library = panel(items, "library");

    expect(library?.rows.map((row) => row.label)).toEqual(["notes.pdf"]);
    expect(library?.manageHref).toBe(CRAFT_LIBRARY_PATH);
    expect(library?.onManage).toBeUndefined();
  });

  it("wires each library row's switch to the file's checked/onToggle state", () => {
    const onToggle = jest.fn();
    const items = buildEntryMenuItems(
      handlers({
        libraryFiles: [
          {
            id: "file-1",
            name: "notes.pdf",
            checked: true,
            onToggle,
          },
        ],
      }),
      tStub
    );
    const row = panel(items, "library")?.rows[0];

    expect(row?.checked).toBe(true);
    row?.onCheckedChange(false);
    expect(onToggle).toHaveBeenCalledWith(false);
  });
});
