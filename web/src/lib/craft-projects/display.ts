import type {
  CraftProjectFile,
  CraftProjectSession,
  CraftProjectSessionStatus,
} from "@/lib/craft-projects/types";

export type CraftProjectFileKind = "markdown" | "table" | "json" | "other";

export type CraftProjectFileTitleSource =
  | "original"
  | "folder"
  | "mcp"
  | "generated";

export type CraftProjectSessionStatusKey =
  | "initializing"
  | "active"
  | "idle"
  | "failed";

export const KNOWN_SESSION_ROLES = [
  "literature",
  "clinical",
  "patent",
  "cmc",
  "fto",
] as const;

export type KnownSessionRole = (typeof KNOWN_SESSION_ROLES)[number];

const GENERIC_FOLDERS = new Set([
  "artifacts",
  "data",
  "files",
  "generated",
  "mcp",
  "output",
  "outputs",
  "temp",
  "tmp",
  "work",
  "workspace",
]);

const KIND_RANK: Record<CraftProjectFileKind, number> = {
  markdown: 0,
  table: 1,
  json: 2,
  other: 3,
};

const STATUS_RANK: Record<CraftProjectSessionStatusKey, number> = {
  active: 0,
  initializing: 1,
  idle: 2,
  failed: 3,
};

export function fileExtension(name: string): string {
  const index = name.lastIndexOf(".");
  if (index <= 0 || index === name.length - 1) {
    return "";
  }
  return name.slice(index + 1).toLowerCase();
}

export function fileKind(
  file: Pick<CraftProjectFile, "name" | "mime_type">
): CraftProjectFileKind {
  const ext = fileExtension(file.name);
  if (ext === "md" || ext === "markdown" || ext === "txt") {
    return "markdown";
  }
  if (ext === "csv" || ext === "tsv" || ext === "xlsx" || ext === "xls") {
    return "table";
  }
  if (ext === "json" || ext === "jsonl") {
    return "json";
  }
  const mime = file.mime_type?.toLowerCase() ?? "";
  if (mime.includes("spreadsheet") || mime.includes("csv")) {
    return "table";
  }
  if (mime.includes("json")) {
    return "json";
  }
  if (mime.startsWith("text/")) {
    return "markdown";
  }
  return "other";
}

export function isGeneratedDumpName(name: string): boolean {
  return /^\d{10,}(\.[a-z0-9]+)?$/i.test(name);
}

export function generatedDumpSuffix(name: string): string {
  const stem = name.replace(/\.[^.]+$/, "");
  const digits = stem.match(/\d{4,}$/)?.[0];
  if (!digits) {
    return stem.slice(-4);
  }
  return digits.slice(-4);
}

export function usefulFolder(path: string): string | null {
  const parts = path.replace(/\\/g, "/").split("/").filter(Boolean);
  if (parts.length < 2) {
    return null;
  }
  parts.pop();
  while (parts.length > 0) {
    const folder = parts.pop();
    if (folder && !GENERIC_FOLDERS.has(folder.toLowerCase())) {
      return folder;
    }
  }
  return null;
}

export function pathLooksLikeMcp(path: string): boolean {
  return /(^|\/)mcp(\/|$)/i.test(path.replace(/\\/g, "/"));
}

export function fileTitleSource(
  file: Pick<CraftProjectFile, "name" | "path">
): { source: CraftProjectFileTitleSource; folder: string | null } {
  const folder = usefulFolder(file.path);
  if (!isGeneratedDumpName(file.name)) {
    return { source: "original", folder };
  }
  if (folder) {
    return { source: "folder", folder };
  }
  if (pathLooksLikeMcp(file.path)) {
    return { source: "mcp", folder: null };
  }
  return { source: "generated", folder: null };
}

const BLACKBOARD_SUFFIX = /\s+blackboard$/i;
const HEADLINE_MAX = 28;

export function stripInternalProjectSuffix(name: string): string {
  const trimmed = name.trim();
  return trimmed.replace(BLACKBOARD_SUFFIX, "").trim() || trimmed;
}

export function sidebarListTitle(name: string | null): {
  text: string;
  tooltip: string;
} {
  const text = stripInternalProjectSuffix(name ?? "");
  return { text, tooltip: text };
}

export function projectHeadline(name: string): {
  title: string;
  full: string;
} {
  const full = stripInternalProjectSuffix(name);
  if (full.length <= HEADLINE_MAX) {
    return { title: full, full };
  }
  const clause = full.split(/[，。；;]/)[0]?.trim() ?? full;
  if (clause && clause.length < full.length && clause.length <= 36) {
    return { title: clause, full };
  }
  const source = clause && clause.length < full.length ? clause : full;
  return { title: `${source.slice(0, HEADLINE_MAX)}...`, full };
}

export function parseSessionLane(name: string | null): {
  role: string | null;
  goal: string;
} {
  if (!name?.trim()) {
    return { role: null, goal: "" };
  }
  const trimmed = name.trim();
  const match = trimmed.match(
    /^(.*?)(?:\s*\/\s*)([A-Za-z][A-Za-z0-9_-]{1,32})$/
  );
  if (!match || !match[1].trim()) {
    return { role: null, goal: trimmed };
  }
  return { role: match[2].toLowerCase(), goal: match[1].trim() };
}

export function isKnownSessionRole(role: string): role is KnownSessionRole {
  return (KNOWN_SESSION_ROLES as readonly string[]).includes(role);
}

export function sessionListLabel(name: string | null): {
  role: KnownSessionRole | null;
  text: string;
  full: string;
} {
  const parsed = parseSessionLane(name);
  const full = name?.trim() ?? "";
  if (parsed.role && isKnownSessionRole(parsed.role)) {
    return { role: parsed.role, text: parsed.role, full };
  }
  const tokens = full
    .toLowerCase()
    .split(/[\s/_-]+/)
    .filter(Boolean);
  for (let i = tokens.length - 1; i >= 0; i--) {
    const token = tokens[i];
    if (token && isKnownSessionRole(token)) {
      return { role: token, text: token, full };
    }
  }
  return { role: null, text: full, full };
}

export function normalizeSessionStatus(
  status: CraftProjectSessionStatus | string
): CraftProjectSessionStatusKey {
  const value = status.trim().toLowerCase();
  if (value === "initializing") {
    return "initializing";
  }
  if (value === "active") {
    return "active";
  }
  if (value === "failed") {
    return "failed";
  }
  return "idle";
}

export type ProjectFilePreviewKind =
  | "markdown"
  | "text"
  | "json"
  | "image"
  | "unsupported";

export const PROJECT_FILE_TEXT_PREVIEW_MAX_BYTES = 1_572_864;

const IMAGE_EXTENSIONS = new Set([
  "bmp",
  "gif",
  "jpeg",
  "jpg",
  "png",
  "svg",
  "webp",
]);

const TEXT_EXTENSIONS = new Set([
  "css",
  "csv",
  "html",
  "js",
  "jsonl",
  "log",
  "py",
  "sh",
  "ts",
  "tsv",
  "tsx",
  "txt",
  "xml",
  "yaml",
  "yml",
]);

export function projectFilePreviewKind(
  file: Pick<CraftProjectFile, "name" | "mime_type">
): ProjectFilePreviewKind {
  const ext = fileExtension(file.name);
  const mime = file.mime_type?.toLowerCase() ?? "";
  if (mime.startsWith("image/") || IMAGE_EXTENSIONS.has(ext)) {
    return "image";
  }
  if (ext === "md" || ext === "markdown") {
    return "markdown";
  }
  if (ext === "json" || (mime.includes("json") && ext !== "jsonl")) {
    return "json";
  }
  if (mime.startsWith("text/") || TEXT_EXTENSIONS.has(ext)) {
    return "text";
  }
  return "unsupported";
}

export function formatProjectFileText(
  text: string,
  kind: ProjectFilePreviewKind
): string {
  if (kind !== "json") {
    return text;
  }
  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    return text;
  }
}

export function fileFolderPath(path: string): string {
  const parts = path.replace(/\\/g, "/").replace(/^\//, "").split("/").filter(Boolean);
  if (parts.length < 2) {
    return "";
  }
  parts.pop();
  return parts.join("/");
}

export interface ProjectFileFolderGroup {
  folder: string;
  files: CraftProjectFile[];
}

export function groupProjectFilesByFolder(
  files: readonly CraftProjectFile[]
): ProjectFileFolderGroup[] {
  const sorted = [...files].sort((left, right) => {
    const byFolder = fileFolderPath(left.path).localeCompare(
      fileFolderPath(right.path)
    );
    if (byFolder !== 0) {
      return byFolder;
    }
    return left.name.localeCompare(right.name);
  });
  const groups: ProjectFileFolderGroup[] = [];
  for (const item of sorted) {
    const folder = fileFolderPath(item.path);
    const last = groups[groups.length - 1];
    if (last && last.folder === folder) {
      last.files.push(item);
    } else {
      groups.push({ folder, files: [item] });
    }
  }
  return groups;
}

export function compareProjectFiles(
  left: CraftProjectFile,
  right: CraftProjectFile
): number {
  const dumpLeft = isGeneratedDumpName(left.name) ? 1 : 0;
  const dumpRight = isGeneratedDumpName(right.name) ? 1 : 0;
  if (dumpLeft !== dumpRight) {
    return dumpLeft - dumpRight;
  }
  const byKind = KIND_RANK[fileKind(left)] - KIND_RANK[fileKind(right)];
  if (byKind !== 0) {
    return byKind;
  }
  return left.name.localeCompare(right.name);
}

export function compareProjectSessions(
  left: CraftProjectSession,
  right: CraftProjectSession
): number {
  const byStatus =
    STATUS_RANK[normalizeSessionStatus(left.status)] -
    STATUS_RANK[normalizeSessionStatus(right.status)];
  if (byStatus !== 0) {
    return byStatus;
  }
  return (
    Date.parse(right.last_activity_at) - Date.parse(left.last_activity_at)
  );
}
