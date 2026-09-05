/**
 * Page Object Model for the admin "System MCP" page (/admin/mcp-catalog).
 *
 * Covers the module toggle and the installed-server list. Installing a server
 * goes through the API client instead — the form is not what these specs are
 * about.
 */

import { type Page, type Locator, expect } from "@playwright/test";
import { ADMIN_ROUTES } from "@/lib/admin-routes";

export class AdminMcpCatalogPage {
  readonly page: Page;
  readonly moduleToggle: Locator;

  constructor(page: Page) {
    this.page = page;
    this.moduleToggle = page.getByTestId("mcp-module-toggle");
  }

  async goto(): Promise<void> {
    await this.page.goto(ADMIN_ROUTES.MCP_CATALOG.path);
  }

  entry(slug: string): Locator {
    return this.page.getByTestId(`mcp-catalog-entry-${slug}`);
  }

  publicToggle(slug: string): Locator {
    return this.page.getByTestId(`mcp-catalog-public-${slug}`);
  }

  async expectEntryVisible(slug: string): Promise<void> {
    await expect(this.entry(slug)).toBeVisible();
  }

  async expectModuleEnabled(enabled: boolean): Promise<void> {
    await expect(this.moduleToggle).toHaveAttribute(
      "aria-checked",
      String(enabled)
    );
  }

  async setModuleEnabled(enabled: boolean): Promise<void> {
    await this.expectModuleEnabled(!enabled);
    await this.moduleToggle.click();
    await this.expectModuleEnabled(enabled);
  }

  async makePublic(slug: string): Promise<void> {
    await this.publicToggle(slug).click();
    await expect(this.publicToggle(slug)).toHaveAttribute(
      "aria-checked",
      "true"
    );
  }
}
