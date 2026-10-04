import type { Metadata } from "next";
import { fetchEnterpriseSettingsSS } from "@/lib/settings/svcSS";

async function fetchAppName(): Promise<string> {
  const enterpriseSettings = await fetchEnterpriseSettingsSS();
  return enterpriseSettings?.application_name?.trim() || "Onyx";
}

export async function generateFaviconMetadata(): Promise<Metadata["icons"]> {
  const enterpriseSettings = await fetchEnterpriseSettingsSS();
  if (enterpriseSettings?.use_custom_favicon) {
    // Cache-buster so a newly uploaded favicon replaces the old one without
    // a manual cache clear.
    return { icon: `/api/enterprise-settings/favicon?v=${Date.now()}` };
  }
  return { icon: "/onyx.ico" };
}

export async function generateAdminTitleMetadata(): Promise<Metadata["title"]> {
  return `Admin — ${await fetchAppName()}`;
}
