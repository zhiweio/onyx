/**
 * Page Object Model for Craft Apps (/craft/v1/apps).
 */

import { type Page, type Locator, expect } from "@playwright/test";

async function suppressCraftIntro(page: Page): Promise<void> {
  const me = await page.request.get("/api/me");
  if (!me.ok()) return;
  const body = (await me.json()) as { id?: string };
  if (!body.id) return;
  await page.addInitScript((userId: string) => {
    window.localStorage.setItem(`onyx:craftOnboardingSeen:${userId}`, "true");
  }, body.id);
}

export class CraftAppsPage {
  readonly page: Page;
  readonly manageMyMcpButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.manageMyMcpButton = page
      .getByRole("link", { name: /Manage my MCP/i })
      .or(page.getByRole("button", { name: /Manage my MCP/i }));
  }

  async goto(): Promise<void> {
    await suppressCraftIntro(this.page);
    await this.page.goto("/craft/v1/apps");
    await this.page.waitForURL("**/craft/v1/apps**");
  }

  async expectManageMyMcpVisible(): Promise<void> {
    await expect(this.manageMyMcpButton).toBeVisible();
  }

  async openManageMyMcp(): Promise<void> {
    await this.manageMyMcpButton.click();
    await this.page.waitForURL("**/craft/v1/mcp-actions**");
  }
}
