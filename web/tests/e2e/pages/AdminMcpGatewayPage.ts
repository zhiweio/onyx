/**
 * Page Object Model for the admin MCP Gateway ops page (/admin/mcp-gateway).
 */

import { type Page, type Locator, expect } from "@playwright/test";
import { ADMIN_ROUTES } from "@/lib/admin-routes";

export class AdminMcpGatewayPage {
  readonly page: Page;
  readonly overviewTab: Locator;
  readonly cacheTab: Locator;
  readonly callsTab: Locator;
  readonly toolFilter: Locator;
  readonly loadMoreButton: Locator;
  readonly cacheTable: Locator;
  readonly callsTable: Locator;

  constructor(page: Page) {
    this.page = page;
    this.overviewTab = page.getByRole("tab", { name: /Overview/i });
    this.cacheTab = page.getByRole("tab", { name: /^Cache$/i });
    this.callsTab = page.getByRole("tab", { name: /^Calls$/i });
    this.toolFilter = page.getByLabel(/Tool name/i);
    this.loadMoreButton = page.getByRole("button", { name: /Load more/i });
    this.cacheTable = page.getByRole("table").filter({
      has: page.getByText(/Cached calls/i),
    });
    this.callsTable = page.getByRole("table").filter({
      has: page.getByText(/Time window/i),
    });
  }

  async goto(query?: { tab?: string; server?: string }): Promise<void> {
    const params = new URLSearchParams();
    if (query?.tab) params.set("tab", query.tab);
    if (query?.server) params.set("server", query.server);
    const suffix = params.size ? `?${params.toString()}` : "";
    await this.page.goto(`${ADMIN_ROUTES.MCP_GATEWAY.path}${suffix}`);
    await this.page.waitForURL(`**${ADMIN_ROUTES.MCP_GATEWAY.path}**`);
  }

  async expectLoaded(): Promise<void> {
    await expect(
      this.page.getByText(
        /Operations for organization MCP servers that route through the gateway/i
      )
    ).toBeVisible();
    await expect(this.overviewTab).toBeVisible();
    await expect(this.cacheTab).toBeVisible();
    await expect(this.callsTab).toBeVisible();
  }

  async expectTimeWindowVisible(): Promise<void> {
    await expect(this.page.getByText(/24 hours/i).first()).toBeVisible();
  }

  async selectSevenDayWindow(): Promise<void> {
    await this.page.getByText(/24 hours/i).first().click();
    await this.page.getByRole("option", { name: /7 days/i }).click();
    await expect(this.page.getByText(/7 days/i).first()).toBeVisible();
  }

  async openTab(tab: "overview" | "cache" | "calls"): Promise<void> {
    const target =
      tab === "overview"
        ? this.overviewTab
        : tab === "cache"
          ? this.cacheTab
          : this.callsTab;
    await target.click();
    await expect(target).toHaveAttribute("data-state", "active");
  }

  async expectCacheTable(): Promise<void> {
    await expect(this.page.getByText(/Cached calls/i).first()).toBeVisible();
    await expect(this.page.getByText(/hits/i).first()).toBeVisible();
  }

  async expectCallsPreviewOnly(): Promise<void> {
    await expect(this.page.getByText(/Time window/i).first()).toBeVisible();
    const body = await this.page.locator("table tbody").innerText();
    expect(body).not.toMatch(/"arguments"\s*:/);
    expect(body).not.toMatch(/\{\s*"\w+"\s*:/);
  }

  async expectServerFilter(serverName: string): Promise<void> {
    await expect(this.page.getByText(serverName, { exact: false }).first()).toBeVisible();
  }
}
