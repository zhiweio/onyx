/**
 * Shared helpers for the Alibaba Bailian (DashScope) provider.
 *
 * Bailian serves each workspace from a region-specific domain:
 * `https://{WorkspaceId}.{region}.maas.aliyuncs.com`. Both the language-model
 * and image-generation admin forms compose that domain from a workspace ID
 * plus a region picker, and store the full OpenAI-compatible base
 * (`.../compatible-mode/v1`) in `api_base`. Backend consumers normalize the
 * suffix away when they need the bare domain.
 */

export interface DashscopeRegion {
  /** Region code used inside the workspace domain. */
  code: string;
  /**
   * Region display name, matching Alibaba's console naming. A proper noun,
   * so it is not translated (same convention as provider group names).
   */
  label: string;
}

export const DASHSCOPE_REGIONS: DashscopeRegion[] = [
  { code: "cn-beijing", label: "华北2（北京）" },
  { code: "cn-hongkong", label: "中国香港" },
  { code: "ap-southeast-1", label: "新加坡" },
  { code: "us-east-1", label: "美国（弗吉尼亚）" },
  { code: "eu-central-1", label: "德国（法兰克福）" },
  { code: "ap-northeast-1", label: "日本（东京）" },
];

/** Region selector value for a hand-entered endpoint (legacy domains etc.). */
export const DASHSCOPE_CUSTOM_REGION = "custom";

/**
 * Known qwen-image family members, kept in sync with the backend seed list
 * (`onyx.server.manage.image_generation.api`). Shown before the workspace's
 * model listing is fetched, and merged with whatever the fetch returns.
 */
export const DASHSCOPE_IMAGE_SEED_MODELS: { name: string; label: string }[] = [
  { name: "qwen-image-3.0-pro", label: "Qwen Image 3.0 Pro" },
  { name: "qwen-image-3.0", label: "Qwen Image 3.0" },
  { name: "qwen-image-2.0-pro", label: "Qwen Image 2.0 Pro" },
  { name: "qwen-image-2.0", label: "Qwen Image 2.0" },
  { name: "qwen-image-edit", label: "Qwen Image Edit" },
  { name: "qwen-image", label: "Qwen Image" },
];

const COMPATIBLE_MODE_SUFFIX = "/compatible-mode/v1";

const MAAS_DOMAIN_PATTERN =
  /^https:\/\/([^.]+)\.([a-z0-9-]+)\.maas\.aliyuncs\.com/i;

export interface ParsedDashscopeBase {
  workspaceId: string;
  /** A region code, or `DASHSCOPE_CUSTOM_REGION`. */
  region: string;
  /** Raw endpoint; only meaningful in custom mode. */
  customBase: string;
}

/** Builds the OpenAI-compatible base for the workspace domain. */
export function composeDashscopeBase(
  workspaceId: string,
  region: string,
  customBase: string
): string {
  if (region === DASHSCOPE_CUSTOM_REGION) {
    const cleaned = customBase.trim().replace(/\/+$/, "");
    return cleaned.endsWith(COMPATIBLE_MODE_SUFFIX)
      ? cleaned
      : `${cleaned}${COMPATIBLE_MODE_SUFFIX}`;
  }
  return `https://${workspaceId.trim()}.${region}.maas.aliyuncs.com${COMPATIBLE_MODE_SUFFIX}`;
}

/**
 * Splits a stored `api_base` back into form fields. Falls back to custom mode
 * when the value does not match the workspace domain pattern, so any endpoint
 * saved earlier can still be edited.
 */
export function parseDashscopeBase(
  apiBase: string | null | undefined
): ParsedDashscopeBase {
  const match = apiBase?.match(MAAS_DOMAIN_PATTERN);
  if (match) {
    const [, workspaceId, region] = match;
    if (DASHSCOPE_REGIONS.some((r) => r.code === region)) {
      return { workspaceId, region, customBase: "" };
    }
  }
  return {
    workspaceId: "",
    region: DASHSCOPE_CUSTOM_REGION,
    customBase: apiBase ?? "",
  };
}
