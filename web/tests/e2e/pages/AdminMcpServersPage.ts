/**
 * Page Object Model for the admin "MCP Actions" page (/admin/mcp-actions).
 *
 * Drives the Add-Server modal and the auth-configuration modal (OAuth / API Key
 * shared / API Key per-user). Used by the UI "create-flow" tests we deliberately
 * keep — most other setup is done via the API client instead.
 */

import { type Page, type Locator, expect } from "@playwright/test";
import type { McpSurface } from "@/lib/tools/mcpSurface";
import { mcpActionsPath } from "@/lib/tools/mcpSurface";

export class AdminMcpServersPage {
  readonly page: Page;
  readonly surface: McpSurface;

  // Add-server modal
  readonly addServerButton: Locator;
  readonly nameInput: Locator;
  readonly descriptionInput: Locator;
  readonly serverUrlInput: Locator;
  readonly submitButton: Locator;
  readonly accessControlSelector: Locator;

  // Auth modal
  readonly authMethodSelect: Locator;
  readonly apiTokenInput: Locator;
  readonly oauthClientIdInput: Locator;
  readonly oauthClientSecretInput: Locator;
  readonly connectButton: Locator;

  // Server card + tools
  readonly refreshToolsButton: Locator;

  constructor(page: Page, surface: McpSurface = "admin") {
    this.page = page;
    this.surface = surface;
    this.addServerButton = page.getByRole("button", {
      name: /Add MCP Server/i,
    });
    this.nameInput = page.locator("input#name");
    this.descriptionInput = page.locator("textarea#description");
    this.serverUrlInput = page.locator("input#server_url");
    this.submitButton = page.getByRole("button", { name: "Add Server" });
    // BooleanFormField aria-label from "Make this MCP server Public?"
    this.accessControlSelector = page.getByRole("checkbox", {
      name: /make-this mcp server public/i,
    });

    this.authMethodSelect = page.getByTestId("mcp-auth-method-select");
    this.apiTokenInput = page.locator('input[name="api_token"]');
    this.oauthClientIdInput = page.locator('input[name="oauth_client_id"]');
    this.oauthClientSecretInput = page.locator(
      'input[name="oauth_client_secret"]'
    );
    this.connectButton = page.getByTestId("mcp-auth-connect-button");

    this.refreshToolsButton = page.getByRole("button", {
      name: /Refresh tools/i,
    });
  }

  // ---------------------------------------------------------------------------
  // Navigation
  // ---------------------------------------------------------------------------

  private apiRoot(): string {
    return this.surface === "personal" ? "/api/mcp/personal" : "/api/admin/mcp";
  }

  async goto(): Promise<void> {
    const path = mcpActionsPath(this.surface);
    await this.page.goto(path);
    await this.page.waitForURL(`**${path}**`);
  }

  // ---------------------------------------------------------------------------
  // Add-server modal
  // ---------------------------------------------------------------------------

  async openAddServerModal(): Promise<void> {
    await this.addServerButton.click();
    await expect(this.nameInput).toBeVisible();
  }

  async expectAccessControlVisible(): Promise<void> {
    await expect(this.accessControlSelector).toBeVisible();
  }

  async fillServerDetails(details: {
    name: string;
    description?: string;
    url: string;
    /** Restrict to this group. Required for a scoped manager: the backend
     *  refuses a public server outside the groups they manage. */
    group?: string;
  }): Promise<void> {
    await this.nameInput.fill(details.name);
    if (details.description) {
      await this.descriptionInput.fill(details.description);
    }
    await this.serverUrlInput.fill(details.url);
    if (details.group) {
      await this.restrictToGroup(details.group);
    }
  }

  /** A global holder gets a Public toggle defaulting to on, which disables the
   *  picker — untick it (the checkbox is 1x1, so click the label). A scoped
   *  manager never sees the toggle; is_public is forced off for them. */
  async restrictToGroup(group: string): Promise<void> {
    const publicLabel = this.page
      .getByText("Make this MCP Server Public?", { exact: false })
      .first();
    if (await publicLabel.isVisible().catch(() => false)) {
      await publicLabel.click();
    }
    const search = this.page.getByTestId("groups-search-input");
    await expect(search).toBeVisible({ timeout: 10_000 });
    await search.click();
    await this.page.getByText(group, { exact: true }).first().click();
  }

  /**
   * Submit the add-server modal, returning the created (bare) server id. The
   * auth-configuration modal opens automatically afterwards.
   */
  async submitAddServer(): Promise<number> {
    const responsePromise = this.page.waitForResponse(
      (resp) =>
        new URL(resp.url()).pathname === `${this.apiRoot()}/server` &&
        resp.request().method() === "POST" &&
        resp.ok()
    );
    await this.submitButton.click();
    const response = await responsePromise;
    const created = (await response.json()) as { id?: number };
    expect(created.id).toBeTruthy();
    await expect(this.authMethodSelect).toBeVisible();
    return Number(created.id);
  }

  // ---------------------------------------------------------------------------
  // Auth modal
  // ---------------------------------------------------------------------------

  async selectAuthMethod(method: "OAuth" | "API Key" | "None"): Promise<void> {
    await this.authMethodSelect.click();
    await this.page.getByRole("option", { name: method }).click();
  }

  async selectApiKeyTab(which: "admin" | "per-user"): Promise<void> {
    const pattern =
      which === "admin" ? /Shared Key.*Admin/i : /Individual Key.*Per User/i;
    const tab = this.page.getByRole("tab", { name: pattern });
    await expect(tab).toBeVisible();
    await tab.click();
  }

  async fillApiToken(token: string): Promise<void> {
    await expect(this.apiTokenInput).toBeVisible();
    await this.apiTokenInput.click();
    await this.apiTokenInput.fill(token);
  }

  async fillOAuthCredentials(
    clientId: string,
    clientSecret: string
  ): Promise<void> {
    await this.oauthClientIdInput.fill(clientId);
    await this.oauthClientSecretInput.fill(clientSecret);
  }

  async clickConnect(): Promise<void> {
    await expect(this.connectButton).toBeVisible();
    await expect(this.connectButton).toBeEnabled();
    await this.connectButton.click();
  }

  /**
   * Click Connect and wait for the `servers/create` upsert (used by API-key /
   * per-user flows that validate credentials against the live server in-place).
   */
  async connectAndWaitForUpsert(): Promise<void> {
    const responsePromise = this.page.waitForResponse(
      (resp) =>
        resp.url().endsWith(`${this.apiRoot()}/servers/create`) &&
        resp.request().method() === "POST"
    );
    await this.clickConnect();
    const response = await responsePromise;
    expect(response.ok()).toBeTruthy();
  }

  // ---------------------------------------------------------------------------
  // Per-user multi-field template header builder
  // ---------------------------------------------------------------------------

  /**
   * The InputKeyValue wrapper for header rows. Inputs are labelled "Key N" /
   * "Value N" (1-indexed) because PerUserAuthConfig passes no placeholders.
   */
  get headerGroup(): Locator {
    return this.page.getByRole("group", {
      name: /Header Name and Header Value pairs/i,
    });
  }

  async expectFirstHeaderPrefilled(): Promise<void> {
    await expect(this.headerGroup.getByLabel("Key 1")).toHaveValue(
      "Authorization"
    );
    await expect(this.headerGroup.getByLabel("Value 1")).toHaveValue(
      "Bearer {api_key}"
    );
  }

  async addHeaderRow(): Promise<void> {
    await this.headerGroup
      .getByRole("button", { name: /Add Header Name and Header Value pair/i })
      .click();
  }

  async fillHeaderRow(
    index: number,
    name: string,
    value: string
  ): Promise<void> {
    const nameInput = this.headerGroup.getByLabel(`Key ${index}`);
    const valueInput = this.headerGroup.getByLabel(`Value ${index}`);
    await expect(nameInput).toBeVisible();
    await nameInput.fill(name);
    await valueInput.fill(value);
  }

  async fillOwnCredentials(credentials: {
    apiKey: string;
    username?: string;
  }): Promise<void> {
    const apiKeyInput = this.page.locator(
      'input[name="user_credentials.api_key"]'
    );
    await expect(apiKeyInput).toBeVisible();
    await apiKeyInput.fill(credentials.apiKey);
    if (credentials.username !== undefined) {
      const usernameInput = this.page.locator(
        'input[name="user_credentials.username"]'
      );
      await expect(usernameInput).toBeVisible();
      await usernameInput.fill(credentials.username);
    }
  }

  // ---------------------------------------------------------------------------
  // Server card + tool toggles
  // ---------------------------------------------------------------------------

  async expectServerCard(serverName: string): Promise<void> {
    await expect(
      this.page.getByText(serverName, { exact: false }).first()
    ).toBeVisible();
  }

  async connectAndWaitForTools(): Promise<void> {
    const toolsPromise = this.page.waitForResponse(
      (resp) =>
        resp.url().includes(`${this.apiRoot()}/server/`) &&
        resp.url().includes("/tools/snapshots") &&
        resp.request().method() === "GET"
    );
    await this.connectAndWaitForUpsert();
    const response = await toolsPromise;
    expect(response.ok()).toBeTruthy();
  }

  async refreshTools(): Promise<void> {
    await expect(this.refreshToolsButton).toBeVisible();
    await this.refreshToolsButton.click();
    await expect(this.page.getByText("No tools available")).not.toBeVisible();
  }

  serverCard(serverName: string): Locator {
    return this.page.getByRole("article", {
      name: new RegExp(serverName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
    });
  }

  async searchServers(term: string): Promise<void> {
    const search = this.page
      .locator("div.flex-row")
      .filter({ has: this.addServerButton })
      .getByPlaceholder(/Search/i);
    await expect(search).toBeVisible();
    await search.fill(term);
    await expect(search).toHaveValue(term);
  }

  async expandServerCard(serverName: string): Promise<void> {
    const card = this.serverCard(serverName);
    await expect(card).toBeVisible();
    const fold = card.getByRole("button", { name: /^Fold$/i });
    if ((await fold.count()) === 0) {
      await card
        .getByRole("button", { name: /View .* tools?/i })
        .first()
        .click();
    }
    await expect(card.getByPlaceholder(/Search tools/i)).toBeVisible();
  }

  cardToolToggle(toolName: string): Locator {
    return this.page.getByLabel(`tool-toggle-${toolName}`);
  }

  /**
   * Set every visible instance of a card tool toggle to the desired state.
   * (The same tool can render more than once on the page.)
   */
  async setCardToolEnabled(toolName: string, enabled: boolean): Promise<void> {
    const toggles = this.cardToolToggle(toolName);
    await expect(toggles.first()).toBeVisible();
    const count = await toggles.count();
    const desired = enabled ? "true" : "false";
    for (let i = 0; i < count; i++) {
      const toggle = toggles.nth(i);
      if ((await toggle.getAttribute("aria-checked")) !== desired) {
        await toggle.click();
        await expect(toggle).toHaveAttribute("aria-checked", desired);
      }
    }
  }

  // ---------------------------------------------------------------------------
  // Pack install + gateway badge
  // ---------------------------------------------------------------------------

  customUrlModeButton(): Locator {
    return this.page.getByTestId("mcp-install-custom");
  }

  fromPackModeButton(): Locator {
    return this.page.getByTestId("mcp-install-pack");
  }

  async expectInstallModesVisible(): Promise<void> {
    await expect(this.customUrlModeButton()).toBeVisible();
    await expect(this.fromPackModeButton()).toBeVisible();
  }

  async expectInstallModesHidden(): Promise<void> {
    await expect(this.customUrlModeButton()).toHaveCount(0);
    await expect(this.fromPackModeButton()).toHaveCount(0);
  }

  async selectFromPack(): Promise<void> {
    await this.fromPackModeButton().click();
  }

  packButton(displayName: string): Locator {
    const escaped = displayName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    return this.page.getByRole("button", { name: new RegExp(`^${escaped}`) });
  }

  packBySlug(slug: string): Locator {
    return this.page.getByTestId(`mcp-pack-${slug}`);
  }

  async selectPack(displayName: string): Promise<void> {
    const pack = this.packButton(displayName);
    await expect(pack).toBeVisible();
    await pack.click();
  }

  async changePack(): Promise<void> {
    const change = this.page.getByTestId("mcp-pack-change");
    await expect(change).toBeVisible();
    await change.click();
  }

  async fillGatewaySlug(slug: string): Promise<void> {
    const slugInput = this.page.locator('input[name="gateway_slug"]');
    await expect(slugInput).toBeVisible();
    await slugInput.fill(slug);
  }

  /**
   * Submit a From Pack install and return the created server id.
   */
  async submitFromPack(): Promise<number> {
    const responsePromise = this.page.waitForResponse(
      (resp) =>
        new URL(resp.url()).pathname === "/api/admin/mcp/servers/from-pack" &&
        resp.request().method() === "POST" &&
        resp.ok()
    );
    await this.submitButton.click();
    const response = await responsePromise;
    const created = (await response.json()) as { id?: number };
    expect(created.id).toBeTruthy();
    return Number(created.id);
  }

  async expectGatewayBadge(serverName: string): Promise<void> {
    await this.searchServers(serverName);
    await expect(
      this.page.getByText(`${serverName} · Gateway`, { exact: false }).first()
    ).toBeVisible();
  }

  async expectDirectBadge(serverName: string): Promise<void> {
    await this.searchServers(serverName);
    await expect(
      this.page.getByText(`${serverName} · Direct`, { exact: false }).first()
    ).toBeVisible();
  }

  async openGatewayFromCard(serverName: string, slug?: string): Promise<void> {
    await this.expectGatewayBadge(serverName);
    const suffix = slug ? `?tab=cache&server=${slug}` : "";
    await this.page.goto(`/admin/mcp-gateway${suffix}`);
    await this.page.waitForURL("**/admin/mcp-gateway**");
  }

  async openManageModal(serverName: string): Promise<void> {
    await this.searchServers(serverName);
    const card = this.serverCard(serverName);
    await expect(card).toBeVisible();
    await card.scrollIntoViewIfNeeded();
    const manage = card.getByRole("button", {
      name: new RegExp(
        `Manage ${serverName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")} server`,
        "i"
      ),
    });
    await expect(manage).toBeVisible();
    // The actions column can sit over the manage control on a crowded page.
    await manage.evaluate((element) => element.click());
    await expect(this.page.getByRole("dialog")).toBeVisible();
    await expect(this.page.getByTestId("mcp-gateway-section")).toBeVisible();
  }

  gatewaySection(): Locator {
    return this.page.getByTestId("mcp-gateway-section");
  }

  async bindToGateway(slug?: string): Promise<void> {
    if (slug) {
      await this.fillGatewaySlug(slug);
    }
    const bind = this.page.getByTestId("mcp-gateway-bind");
    await expect(bind).toBeVisible();
    await bind.click();
    await expect(this.page.getByTestId("mcp-gateway-path")).toBeVisible();
  }

  async unbindFromGateway(): Promise<void> {
    const unbind = this.page.getByTestId("mcp-gateway-unbind");
    await expect(unbind).toBeVisible();
    await unbind.click();
    const confirm = this.page.getByTestId("mcp-gateway-unbind-confirm");
    await expect(confirm).toBeVisible();
    await confirm.click();
    await expect(this.page.getByTestId("mcp-gateway-bind")).toBeVisible();
  }

  async closeManageModal(): Promise<void> {
    await this.page.getByRole("button", { name: /^Cancel$/i }).click();
    await expect(this.page.getByTestId("mcp-gateway-section")).toHaveCount(0);
  }

  async expectCatalogAbsentFromSidebar(): Promise<void> {
    await expect(
      this.page.getByRole("link", { name: /System MCP/i })
    ).toHaveCount(0);
    await expect(this.page.locator('a[href="/admin/mcp-catalog"]')).toHaveCount(
      0
    );
  }
}
