import { test, expect } from "@playwright/test";
import { loginAs } from "@tests/e2e/utils/auth";
import { OnyxApiClient } from "@tests/e2e/utils/onyxApiClient";
import { AdminMcpServersPage } from "@tests/e2e/pages/AdminMcpServersPage";
import { AdminMcpGatewayPage } from "@tests/e2e/pages/AdminMcpGatewayPage";

test.describe("Organization MCP and Gateway", () => {
  test.describe.configure({ mode: "serial" });

  let packServerId: number | null = null;
  let packServerName = "";
  let packSlug = "";
  let uiPackServerId: number | null = null;

  test.beforeAll(async ({ browser }) => {
    const adminContext = await browser.newContext({
      storageState: "admin_auth.json",
    });
    const response = await adminContext.request.patch("/api/admin/settings", {
      data: { mcp_gateway_enabled: true },
    });
    expect(response.ok()).toBeTruthy();
    await adminContext.close();
  });

  test.afterAll(async ({ browser }) => {
    const adminContext = await browser.newContext({
      storageState: "admin_auth.json",
    });
    const adminClient = new OnyxApiClient(adminContext.request);
    for (const id of [packServerId, uiPackServerId]) {
      if (id !== null) {
        await adminClient.deleteMcpServer(id);
      }
    }
    await adminContext.close();
  });

  test.beforeEach(async ({ page }) => {
    await page.context().clearCookies();
    await loginAs(page, "admin2");
  });

  test("catalog route is gone from admin nav", async ({ page }) => {
    const adminMcp = new AdminMcpServersPage(page);
    await adminMcp.goto();
    await adminMcp.expectCatalogAbsentFromSidebar();

    await page.goto("/admin/mcp-catalog");
    await expect(
      page.getByRole("heading", { name: /System MCP/i })
    ).toHaveCount(0);
  });

  test("admin can add from a pack and open gateway cache", async ({ page }) => {
    const adminMcp = new AdminMcpServersPage(page);
    await adminMcp.goto();

    await adminMcp.openAddServerModal();
    await adminMcp.expectInstallModesVisible();
    await adminMcp.selectFromPack();
    await adminMcp.selectPack("DeepWiki");
    await expect(adminMcp.nameInput).toHaveValue("DeepWiki");
    await adminMcp.changePack();
    await adminMcp.selectPack("Parallel Search");
    await expect(adminMcp.nameInput).toHaveValue("Parallel Search");
    await adminMcp.changePack();
    await adminMcp.selectPack("Generic HTTP MCP");
    await expect(adminMcp.serverUrlInput).toBeVisible();
    await page.keyboard.press("Escape");

    packSlug = `pw-pack-${Date.now()}`;
    packServerName = `PW Pack ${Date.now()}`;
    const client = new OnyxApiClient(page.request);
    const created = await client.createMcpServerFromPack({
      pack_slug: "generic_http",
      name: packServerName,
      slug: packSlug,
      upstream_url: "http://127.0.0.1:9/mcp",
      credentials: { api_key: "e2e-unused" },
      is_public: true,
    });
    packServerId = created.id;
    expect(created.gateway_bound).toBeTruthy();

    await adminMcp.goto();
    await adminMcp.expectGatewayBadge(packServerName);
    await adminMcp.openGatewayFromCard(packServerName, packSlug);

    const gateway = new AdminMcpGatewayPage(page);
    await gateway.expectLoaded();
    await gateway.openTab("cache");
    await gateway.expectCacheTable();
  });

  test("gateway ops page has a time window and call previews", async ({
    page,
  }) => {
    const gateway = new AdminMcpGatewayPage(page);
    await gateway.goto();
    await gateway.expectLoaded();
    await gateway.expectTimeWindowVisible();
    await gateway.selectSevenDayWindow();

    await gateway.openTab("cache");
    await gateway.expectCacheTable();

    await gateway.openTab("calls");
    await gateway.expectCallsPreviewOnly();
  });

  test("from-pack API server shows a Gateway badge", async ({ page }) => {
    const client = new OnyxApiClient(page.request);
    const slug = `pw-api-${Date.now()}`;
    const created = await client.createMcpServerFromPack({
      pack_slug: "generic_http",
      name: `PW API Pack ${Date.now()}`,
      slug,
      upstream_url: "http://127.0.0.1:9/mcp",
      credentials: { api_key: "e2e-unused" },
      is_public: true,
    });
    uiPackServerId = created.id;
    expect(created.gateway_bound).toBeTruthy();

    const adminMcp = new AdminMcpServersPage(page);
    await adminMcp.goto();
    await adminMcp.expectGatewayBadge(created.name);
  });
});
