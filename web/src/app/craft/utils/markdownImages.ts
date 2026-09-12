import { transformLinkUri } from "@/lib/utils";
import { buildArtifactUrl } from "@/app/craft/services/apiServices";

const WORKSPACE_ROOTS = [
  "outputs/",
  "attachments/",
  "project/",
  "uploads/",
  "user_library/",
] as const;

/**
 * Map a Markdown image/link URL to a workspace-relative sandbox path.
 *
 * Handles sibling paths (`figures/plot.png`), workspace-rooted paths
 * (`outputs/markdown/figures/plot.png`), and `sandbox://...` URIs.
 * Remote schemes and paths that leave the workspace return null.
 */
export function resolveWorkspaceMarkdownPath(
  src: string,
  markdownFilePath: string
): string | null {
  const decoded = decodeSrc(src);
  if (!decoded) return null;

  let raw = decoded;
  const schemeEnd = schemePrefixEnd(raw);
  if (schemeEnd !== null) {
    const scheme = raw.slice(0, schemeEnd).toLowerCase();
    if (scheme !== "sandbox:") return null;
    raw = raw.slice(schemeEnd).replace(/^\/+/, "");
  }

  raw = raw.split("#", 1)[0].split("?", 1)[0].replaceAll("\\", "/").trim();
  if (!raw) return null;
  if (raw.startsWith("/")) raw = raw.replace(/^\/+/, "");

  if (isWorkspaceRootPath(raw)) {
    return normalizeWorkspaceParts(raw.split("/"), []);
  }

  return normalizeWorkspaceParts(raw.split("/"), markdownDir(markdownFilePath));
}

export function makeMarkdownPreviewUrlTransform(
  sessionId: string | undefined,
  markdownFilePath: string
): (href: string) => string | null {
  return (href: string) => {
    const trimmed = href.trim();
    if (trimmed.toLowerCase().startsWith("data:image/")) {
      return trimmed;
    }
    if (sessionId) {
      const path = resolveWorkspaceMarkdownPath(trimmed, markdownFilePath);
      if (path) {
        return buildArtifactUrl(sessionId, path);
      }
    }
    return transformLinkUri(href);
  };
}

function decodeSrc(src: string): string {
  const text = src.trim();
  if (!text) return "";
  try {
    return decodeURI(text);
  } catch {
    return text;
  }
}

function schemePrefixEnd(src: string): number | null {
  for (let index = 0; index < src.length; index += 1) {
    const char = src[index];
    if (char === ":") {
      return index > 0 ? index + 1 : null;
    }
    if (!/[a-zA-Z0-9+.-]/.test(char)) {
      return null;
    }
  }
  return null;
}

function isWorkspaceRootPath(path: string): boolean {
  const lowered = path.toLowerCase();
  return WORKSPACE_ROOTS.some((root) => lowered.startsWith(root));
}

function markdownDir(markdownFilePath: string): string[] {
  const cleaned = markdownFilePath
    .replaceAll("\\", "/")
    .replace(/^\/+|\/+$/g, "");
  const idx = cleaned.lastIndexOf("/");
  if (idx <= 0) return [];
  return cleaned
    .slice(0, idx)
    .split("/")
    .filter((part) => part && part !== ".");
}

function normalizeWorkspaceParts(
  parts: string[],
  baseParts: string[]
): string | null {
  const stack = baseParts.filter((part) => part && part !== ".");
  for (const part of parts) {
    if (!part || part === ".") continue;
    if (part === "..") {
      if (stack.length === 0) return null;
      stack.pop();
      continue;
    }
    if (part.includes("/") || part.includes("\\") || part.includes("\0")) {
      return null;
    }
    stack.push(part);
  }
  return stack.length > 0 ? stack.join("/") : null;
}
