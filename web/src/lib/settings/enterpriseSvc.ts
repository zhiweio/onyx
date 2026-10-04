import { EnterpriseSettings } from "@/lib/settings/types";

async function parseErrorDetail(
  res: Response,
  fallback: string
): Promise<string> {
  try {
    const body = await res.json();
    return body?.detail ?? fallback;
  } catch {
    return fallback;
  }
}

// The endpoint merges only the fields sent, so a partial patch leaves the
// rest of the stored branding untouched.
export async function updateEnterpriseSettings(
  updates: Partial<EnterpriseSettings>
): Promise<EnterpriseSettings> {
  const res = await fetch("/api/admin/enterprise-settings", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  if (!res.ok) {
    throw new Error(
      await parseErrorDetail(res, "Failed to update branding settings")
    );
  }
  return res.json();
}

export type BrandAssetSlot =
  | "logo"
  | "logo-dark"
  | "logotype"
  | "logotype-dark"
  | "favicon";

export async function uploadBrandAsset(
  slot: BrandAssetSlot,
  file: File
): Promise<EnterpriseSettings> {
  const body = new FormData();
  body.append("file", file);
  const res = await fetch(`/api/admin/enterprise-settings/${slot}`, {
    method: "PUT",
    body,
  });
  if (!res.ok) {
    throw new Error(await parseErrorDetail(res, "Failed to upload image"));
  }
  return res.json();
}

export async function deleteBrandAsset(
  slot: BrandAssetSlot
): Promise<EnterpriseSettings> {
  const res = await fetch(`/api/admin/enterprise-settings/${slot}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    throw new Error(await parseErrorDetail(res, "Failed to remove image"));
  }
  return res.json();
}

/**
 * URL a browser can load the current custom asset from. The `v` cache-buster
 * forces a refetch after uploads; `Date.now()` is cheap and correct here.
 */
export function brandAssetUrl(slot: BrandAssetSlot): string {
  return `/api/enterprise-settings/${slot}?v=${Date.now()}`;
}
