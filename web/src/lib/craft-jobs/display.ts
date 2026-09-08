import type { TagColor } from "@opal/components";
import type { ToolCallState } from "@/app/craft/types/displayTypes";
import {
  isKnownSessionRole,
  type KnownSessionRole,
} from "@/lib/craft-projects/display";

const ROLE_ALIASES: Record<string, KnownSessionRole> = {
  literature: "literature",
  clinical: "clinical",
  patent: "patent",
  cmc: "cmc",
  fto: "fto",
};

export function compactJobError(
  text: string | null | undefined,
  max = 280
): string {
  if (!text?.trim()) {
    return "";
  }
  const lines = text
    .split(/\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
  const errorLine = lines.find(
    (line) =>
      /403|blocked|fail|error|timeout|无法|阻断|失败|denied/i.test(line) &&
      !line.startsWith("{") &&
      !line.startsWith("#") &&
      !line.startsWith("[")
  );
  const cleaned = (errorLine ?? text)
    .replace(/\s+/g, " ")
    .replace(/:+\s*$/, "")
    .trim();
  if (!cleaned) {
    return "";
  }
  if (cleaned.length <= max) {
    return cleaned;
  }
  return `${cleaned.slice(0, max - 3)}...`;
}

export function jobErrorDisplay(
  text: string | null | undefined,
  fallback: string,
  max = 280
): string {
  const compact = compactJobError(text, max);
  if (!compact) {
    return fallback;
  }
  if (/:\s*$/.test(compact)) {
    return `${compact} ${fallback}`;
  }
  return compact;
}

export function specialistRoleKey(role: string): KnownSessionRole | null {
  const tail = role.split(/[:/]/).pop()?.trim().toLowerCase() ?? "";
  const normalized = tail.replace(/[\s-]+/g, "_");
  if (isKnownSessionRole(normalized)) {
    return normalized;
  }
  return ROLE_ALIASES[normalized] ?? null;
}

export function phaseTagColor(status: string): TagColor {
  if (status === "succeeded") return "green";
  if (status === "running") return "blue";
  if (status === "failed") return "red";
  return "gray";
}

const DURABILITY_FILE_RE =
  /outputs\/(PLAN\.md|TODO\.md|MEMORY\.md|DONE\.json|plan\/PLAN\.json)\b/;
const MCP_CACHE_RE = /outputs\/mcp\//;
const CROSS_SESSION_RE =
  /\/workspace\/\.opencode-data|\/workspace\/sessions\/[0-9a-f-]{8,}/i;

export function isDurabilityFileTool(tool: ToolCallState): boolean {
  return isHiddenJobTool(tool);
}

export function isHiddenJobTool(tool: ToolCallState): boolean {
  if (tool.toolName === "todowrite" || tool.kind === "task") {
    return false;
  }
  const hay = `${tool.title} ${tool.description} ${tool.command}`;
  if (DURABILITY_FILE_RE.test(hay) || MCP_CACHE_RE.test(hay)) {
    return true;
  }
  if (tool.toolName === "bash" && CROSS_SESSION_RE.test(hay)) {
    return true;
  }
  return false;
}

export function isHostContinueMessage(metadata: unknown): boolean {
  if (!metadata || typeof metadata !== "object") {
    return false;
  }
  return (metadata as { craft_job_continue?: boolean }).craft_job_continue === true;
}

export function jobStatusTagColor(status: string): TagColor {
  if (status === "succeeded") return "green";
  if (status === "failed") return "red";
  if (status === "cancelled") return "gray";
  if (status === "interrupted") return "amber";
  return "blue";
}
