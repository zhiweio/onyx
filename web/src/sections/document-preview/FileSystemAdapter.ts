import type { FileSystemEntry } from "@/app/craft/types/streamingTypes";
import type { LibraryEntry } from "@/app/craft/types/user-library";
import type { CraftProjectFile } from "@/lib/craft-projects/types";
import type {
  FileSystemFileItem,
  FileSystemItem,
} from "@/sections/extend/file-system";

function cleanPath(path: string): string {
  return path.replace(/\\/g, "/").replace(/^\/+/, "");
}

function folderPath(path: string): string {
  const normalized = cleanPath(path);
  return normalized.endsWith("/") ? normalized : `${normalized}/`;
}

export function sandboxEntriesToItems(
  entries: FileSystemEntry[],
  getUrl?: (entry: FileSystemEntry) => string
): FileSystemItem[] {
  return entries.map((entry) => {
    if (entry.is_directory) {
      return {
        kind: "folder",
        path: folderPath(entry.path || entry.name),
        name: entry.name,
        hasChildren: true,
      };
    }
    return {
      kind: "file",
      path: cleanPath(entry.path || entry.name),
      name: entry.name,
      contentType: entry.mime_type ?? undefined,
      size: entry.size ?? undefined,
      url: getUrl?.(entry),
    };
  });
}

export function flattenSandboxCache(
  directoryCache: Map<string, FileSystemEntry[]>,
  getUrl?: (entry: FileSystemEntry) => string
): FileSystemItem[] {
  const items: FileSystemItem[] = [];
  const seen = new Set<string>();
  for (const entries of directoryCache.values()) {
    for (const item of sandboxEntriesToItems(entries, getUrl)) {
      if (seen.has(item.path)) continue;
      seen.add(item.path);
      items.push(item);
    }
  }
  return items;
}

export function craftFilesToItems(
  files: CraftProjectFile[],
  getUrl: (file: CraftProjectFile) => string
): FileSystemItem[] {
  return files.map((file) => ({
    kind: "file" as const,
    path: cleanPath(file.path || file.name),
    name: file.name,
    contentType: file.mime_type ?? undefined,
    size: file.size_bytes ?? undefined,
    url: getUrl(file),
    metadata: { id: file.id },
  }));
}

export function libraryEntriesToItems(
  entries: LibraryEntry[]
): FileSystemItem[] {
  return entries.map((entry) => {
    if (entry.is_directory) {
      return {
        kind: "folder",
        path: folderPath(entry.path || entry.name),
        name: entry.name,
        hasChildren: Boolean(entry.children && entry.children.length > 0),
      };
    }
    return {
      kind: "file",
      path: cleanPath(entry.path || entry.name),
      name: entry.name,
      contentType: entry.mime_type ?? undefined,
      size: entry.file_size ?? undefined,
      metadata: { id: entry.id },
    };
  });
}

export function flattenLibraryTree(entries: LibraryEntry[]): FileSystemItem[] {
  const items: FileSystemItem[] = [];
  const walk = (nodes: LibraryEntry[]) => {
    items.push(...libraryEntriesToItems(nodes));
    for (const node of nodes) {
      if (node.children?.length) {
        walk(node.children);
      }
    }
  };
  walk(entries);
  return items;
}

export function fileSystemFileId(file: FileSystemFileItem): string | undefined {
  return file.metadata?.id;
}
