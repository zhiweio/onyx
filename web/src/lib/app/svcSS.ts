import type { Metadata } from "next";

async function fetchAppName(): Promise<string> {
  return "Onyx";
}

export async function generateFaviconMetadata(): Promise<Metadata["icons"]> {
  return { icon: "/onyx.ico" };
}

export async function generateAdminTitleMetadata(): Promise<Metadata["title"]> {
  return `Admin — ${await fetchAppName()}`;
}
