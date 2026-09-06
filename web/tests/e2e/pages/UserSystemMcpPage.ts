/**
 * Page Object Model for the "System MCP" section of user settings
 * (/app/settings/connectors).
 *
 * The section only renders when the gateway module is on and the user has been
 * granted at least one server, so absence is a meaningful assertion here.
 */

import { type Page, type Locator, expect } from "@playwright/test";

export class UserSystemMcpPage {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  async goto(): Promise<void> {
    await this.page.goto("/app/settings/connectors");
  }

  server(slug: string): Locator {
    return this.page.getByTestId(`system-mcp-${slug}`);
  }

  toggle(slug: string): Locator {
    return this.page.getByTestId(`system-mcp-toggle-${slug}`);
  }

  async expectServerVisible(slug: string): Promise<void> {
    await expect(this.server(slug)).toBeVisible();
  }

  async expectServerHidden(slug: string): Promise<void> {
    await expect(this.server(slug)).toBeHidden();
  }

  async expectEnabled(slug: string, enabled: boolean): Promise<void> {
    await expect(this.toggle(slug)).toHaveAttribute(
      "aria-checked",
      String(enabled)
    );
  }

  async enable(slug: string): Promise<void> {
    await this.expectEnabled(slug, false);
    await this.toggle(slug).click();
    await this.expectEnabled(slug, true);
  }
}
