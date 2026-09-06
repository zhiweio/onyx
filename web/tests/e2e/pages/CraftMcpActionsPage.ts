/**
 * Page Object Model for the personal MCP Actions page (/craft/v1/mcp-actions).
 *
 * Reuses the admin add-server / auth / tools locators with the personal API
 * root. Pack and gateway controls must stay hidden on this surface.
 */

import { expect, type Page } from "@playwright/test";
import { AdminMcpServersPage } from "@tests/e2e/pages/AdminMcpServersPage";

async function suppressCraftIntro(page: Page): Promise<void> {
  const me = await page.request.get("/api/me");
  if (!me.ok()) return;
  const body = (await me.json()) as { id?: string };
  if (!body.id) return;
  await page.addInitScript((userId: string) => {
    window.localStorage.setItem(`onyx:craftOnboardingSeen:${userId}`, "true");
  }, body.id);
}

export class CraftMcpActionsPage extends AdminMcpServersPage {
  constructor(page: Page) {
    super(page, "personal");
  }

  override async goto(): Promise<void> {
    await suppressCraftIntro(this.page);
    await super.goto();
  }

  async expectHeadingVisible(): Promise<void> {
    await expect(
      this.page.getByText(
        /Add MCP servers that only you can use in Chat and Craft/i
      )
    ).toBeVisible();
  }

  async expectPersonalSurface(): Promise<void> {
    await this.expectHeadingVisible();
    await this.openAddServerModal();
    await this.expectInstallModesHidden();
    await expect(this.accessControlSelector).toHaveCount(0);
    await this.page.keyboard.press("Escape");
  }
}
