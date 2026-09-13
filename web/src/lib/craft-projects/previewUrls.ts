import { transformLinkUri } from "@/lib/utils";
import { resolveWorkspaceMarkdownPath } from "@/app/craft/utils/markdownImages";
import { craftProjectFileUrl } from "@/lib/craft-projects/api";
import type { CraftProjectFile } from "@/lib/craft-projects/types";

const WORKSPACE_PREFIXES = ["outputs/", "attachments/", "project/"] as const;
const RELATIVE_ASSET_SOURCE =
  String.raw`\s(?:src|href)=["'](?!https?:|data:|blob:|#|mailto:|javascript:)[^"']+["']`;
const ASSET_ATTR_SOURCE =
  String.raw`(\s(?:src|href)=["'])(?!https?:|data:|blob:|#|mailto:|javascript:)([^"']+)(["'])`;

function relativeAssetRe(): RegExp {
  return new RegExp(RELATIVE_ASSET_SOURCE, "i");
}

function assetAttrRe(): RegExp {
  return new RegExp(ASSET_ATTR_SOURCE, "gi");
}

export function normalizeProjectCatalogPath(path: string): string {
  return path.replaceAll("\\", "/").replace(/^\/+/, "");
}

export function catalogPathCandidates(workspacePath: string): string[] {
  const cleaned = normalizeProjectCatalogPath(workspacePath);
  const candidates = [cleaned];
  const lowered = cleaned.toLowerCase();
  for (const prefix of WORKSPACE_PREFIXES) {
    if (lowered.startsWith(prefix)) {
      candidates.push(cleaned.slice(prefix.length));
    }
  }
  return candidates;
}

export function findProjectFileForWorkspacePath(
  files: CraftProjectFile[],
  workspacePath: string
): CraftProjectFile | undefined {
  const wanted = new Set(
    catalogPathCandidates(workspacePath).map((path) => path.toLowerCase())
  );
  return files.find((file) =>
    wanted.has(normalizeProjectCatalogPath(file.path).toLowerCase())
  );
}

export function makeProjectMarkdownPreviewUrlTransform(
  projectId: string,
  markdownFilePath: string,
  files: CraftProjectFile[]
): (href: string) => string | null {
  return (href: string) => {
    const trimmed = href.trim();
    if (trimmed.toLowerCase().startsWith("data:image/")) {
      return trimmed;
    }
    const workspacePath = resolveWorkspaceMarkdownPath(
      trimmed,
      markdownFilePath
    );
    if (workspacePath) {
      const match = findProjectFileForWorkspacePath(files, workspacePath);
      if (match) {
        return craftProjectFileUrl(projectId, match.id);
      }
    }
    return transformLinkUri(href);
  };
}

export async function rewriteProjectHtmlForPreview(
  html: string,
  htmlFilePath: string,
  projectId: string,
  files: CraftProjectFile[],
  fetchBlob: (url: string) => Promise<Blob> = defaultFetchBlob
): Promise<{ html: string; revoke: () => void }> {
  if (!relativeAssetRe().test(html)) {
    return { html, revoke: () => undefined };
  }

  const objectUrls = new Map<string, string>();
  const created: string[] = [];
  const replacements = new Map<string, string>();

  for (const match of html.matchAll(assetAttrRe())) {
    const href = match[2];
    if (!href || replacements.has(href)) {
      continue;
    }
    const workspacePath = resolveWorkspaceMarkdownPath(href, htmlFilePath);
    if (!workspacePath) {
      continue;
    }
    const file = findProjectFileForWorkspacePath(files, workspacePath);
    if (!file) {
      continue;
    }
    const apiUrl = craftProjectFileUrl(projectId, file.id);
    const cached = objectUrls.get(apiUrl);
    if (cached) {
      replacements.set(href, cached);
      continue;
    }
    try {
      const blob = await fetchBlob(apiUrl);
      const objectUrl = URL.createObjectURL(blob);
      objectUrls.set(apiUrl, objectUrl);
      created.push(objectUrl);
      replacements.set(href, objectUrl);
    } catch {
      continue;
    }
  }

  if (replacements.size === 0) {
    return { html, revoke: () => undefined };
  }

  const rewritten = html.replace(assetAttrRe(), (full, prefix, href, suffix) => {
    const next = replacements.get(href);
    return next ? `${prefix}${next}${suffix}` : full;
  });

  return {
    html: rewritten,
    revoke: () => {
      for (const url of created) {
        URL.revokeObjectURL(url);
      }
    },
  };
}

async function defaultFetchBlob(url: string): Promise<Blob> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.blob();
}
