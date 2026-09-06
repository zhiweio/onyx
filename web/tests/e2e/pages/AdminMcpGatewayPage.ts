/**
 * Page Object Model for the admin MCP Gateway ops page (/admin/mcp-gateway).
 */

import { type Page, type Locator, expect } from "@playwright/test";
import { ADMIN_ROUTES } from "@/lib/admin-routes";

export class AdminMcpGatewayPage {
  readonly page: Page;
  readonly root: Locator;
  readonly enableSwitch: Locator;
  readonly dateRange: Locator;
  readonly filters: Locator;
  readonly serverFilter: Locator;
  readonly toolFilter: Locator;
  readonly overviewTab: Locator;
  readonly cacheTab: Locator;
  readonly callsTab: Locator;
  readonly cacheTable: Locator;
  readonly callsTable: Locator;
  readonly cacheSearch: Locator;
  readonly callsSearch: Locator;
  readonly confirmToggle: Locator;
  readonly tableFooter: Locator;

  constructor(page: Page) {
    this.page = page;
    this.root = page.getByTestId("mcp-gateway-page");
    this.enableSwitch = page.getByTestId("mcp-gateway-enable-switch");
    this.dateRange = page.getByTestId("admin-date-range-selector");
    this.filters = page.getByTestId("mcp-gateway-filters");
    this.serverFilter = page.getByTestId("mcp-gateway-server-filter");
    this.toolFilter = page.getByTestId("mcp-gateway-tool-filter");
    this.overviewTab = page.getByTestId("mcp-gateway-tab-overview");
    this.cacheTab = page.getByTestId("mcp-gateway-tab-cache");
    this.callsTab = page.getByTestId("mcp-gateway-tab-calls");
    this.cacheTable = page.getByTestId("mcp-gateway-cache-table");
    this.callsTable = page.getByTestId("mcp-gateway-calls-table");
    this.cacheSearch = page.getByTestId("mcp-gateway-cache-search");
    this.callsSearch = page.getByTestId("mcp-gateway-calls-search");
    this.confirmToggle = page.getByTestId("mcp-gateway-confirm-toggle");
    this.tableFooter = page.locator(".table-footer");
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
    await expect(this.root).toBeVisible();
    await expect(this.overviewTab).toBeVisible();
    await expect(this.cacheTab).toBeVisible();
    await expect(this.callsTab).toBeVisible();
  }

  async expectDateRangeVisible(): Promise<void> {
    await expect(this.dateRange).toBeVisible();
    await expect(this.dateRange.locator("button").nth(1)).toHaveAttribute(
      "aria-pressed",
      "true"
    );
  }

  async selectSevenDayWindow(): Promise<void> {
    await this.dateRange.locator("button").nth(0).click();
    await expect(this.dateRange.locator("button").nth(0)).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    await this.dateRange.locator("button").nth(1).click();
    await expect(this.dateRange.locator("button").nth(1)).toHaveAttribute(
      "aria-pressed",
      "true"
    );
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
    await expect(this.cacheTable).toBeVisible();
    await expect(this.cacheSearch).toBeVisible();
    await expect(this.cacheTable.locator(".table-footer")).toBeVisible();
  }

  async searchCache(term: string): Promise<void> {
    await this.cacheSearch.fill(term);
    await expect(this.cacheSearch).toHaveValue(term);
  }

  async expectCallsPreviewOnly(): Promise<void> {
    await expect(this.callsTable).toBeVisible();
    await expect(this.callsSearch).toBeVisible();
    await expect(this.callsTable.locator(".table-footer")).toBeVisible();
    await expect(this.callsTable).not.toContainText(/"arguments"\s*:/);
    await expect(this.callsTable).not.toContainText(/\{\s*"\w+"\s*:/);
  }

  async expectConfirmOnToggle(): Promise<void> {
    await expect(this.enableSwitch).toBeVisible();
    await this.enableSwitch.click();
    await expect(this.page.getByRole("dialog")).toBeVisible();
    await expect(this.confirmToggle).toBeVisible();
    await this.page.getByTestId("mcp-gateway-confirm-cancel").click();
    await expect(this.page.getByRole("dialog")).toHaveCount(0);
    await expect(this.enableSwitch).toHaveAttribute("aria-checked", "true");
  }

  async expectServerFilter(serverName: string): Promise<void> {
    await expect(
      this.serverFilter.getByText(serverName, { exact: false }).first()
    ).toBeVisible();
  }
}
