import {
  craftFilesToItems,
  fileSystemFileId,
  flattenSandboxCache,
  sandboxEntriesToItems,
} from "@/sections/document-preview/FileSystemAdapter";
import type { CraftProjectFile } from "@/lib/craft-projects/types";

describe("FileSystemAdapter", () => {
  it("maps sandbox directories and files", () => {
    const items = sandboxEntriesToItems(
      [
        {
          name: "outputs",
          path: "outputs",
          is_directory: true,
          size: null,
          mime_type: null,
        },
        {
          name: "report.docx",
          path: "outputs/report.docx",
          is_directory: false,
          size: 12,
          mime_type:
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        },
      ],
      (entry) => `/files/${entry.path}`
    );
    expect(items[0]).toMatchObject({
      kind: "folder",
      path: "outputs/",
      hasChildren: true,
    });
    expect(items[1]).toMatchObject({
      kind: "file",
      path: "outputs/report.docx",
      url: "/files/outputs/report.docx",
    });
  });

  it("flattens cached sandbox listings without duplicates", () => {
    const cache = new Map([
      [
        "",
        [
          {
            name: "outputs",
            path: "outputs",
            is_directory: true,
            size: null,
            mime_type: null,
          },
        ],
      ],
      [
        "outputs",
        [
          {
            name: "old.txt",
            path: "outputs/old.txt",
            is_directory: false,
            size: 10,
            mime_type: "text/plain",
          },
        ],
      ],
    ]);
    const items = flattenSandboxCache(cache);
    expect(items.map((item) => item.path)).toEqual([
      "outputs/",
      "outputs/old.txt",
    ]);
  });

  it("strips a leading slash so project files sit at the root", () => {
    const file = {
      id: "file-2",
      name: "report.docx",
      path: "/report.docx",
      mime_type: null,
      size_bytes: 44,
    } as CraftProjectFile;
    const [item] = craftFilesToItems([file], () => "/x");
    expect(item).toMatchObject({
      kind: "file",
      path: "report.docx",
      name: "report.docx",
    });
  });

  it("keeps craft file ids on File System metadata", () => {
    const file = {
      id: "file-1",
      name: "notes.pdf",
      path: "docs/notes.pdf",
      mime_type: "application/pdf",
      size_bytes: 20,
    } as CraftProjectFile;
    const [item] = craftFilesToItems(file ? [file] : [], () => "/x");
    expect(item?.kind).toBe("file");
    if (item?.kind === "file") {
      expect(fileSystemFileId(item)).toBe("file-1");
    }
  });
});
