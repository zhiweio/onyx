import { test, expect } from "@playwright/test";
import { loginAs, loginAsRandomUser } from "@tests/e2e/utils/auth";
import { AdminMcpCatalogPage } from "@tests/e2e/pages/AdminMcpCatalogPage";
import { UserSystemMcpPage } from "@tests/e2e/pages/UserSystemMcpPage";

/**
 * The system MCP round trip: an admin installs a server and opens it up, and a
 * regular user then sees it in settings and can switch it on.
 *
 * RBAC edges and the module toggle are covered by the backend integration
 * suite; this spec proves the two UI surfaces are actually wired to it.
 */
test.describe("System MCP catalog", () => {
  test.describe.configure({ mode: "serial" });

  const slug = `e2e-${Date.now().toString(36)}`;
  let entryId: number | null = null;
  let gatewayDeployed = true;

  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage();
    await loginAs(page, "admin");

    // The module only turns on where the operator deployed the gateway
    // process, so skip rather than fail on a stack without it.
    const settings = await page.request.get("/api/admin/settings");
    const current = await settings.json();
    const enable = await page.request.patch("/api/admin/settings", {
      data: { ...current, mcp_gateway_enabled: true },
    });
    if (!enable.ok()) {
      gatewayDeployed = false;
      await page.close();
      return;
    }

    const created = await page.request.post("/api/admin/mcp-catalog/entries", {
      data: {
        slug,
        pack_slug: "generic_http",
        upstream_url: "http://127.0.0.1:9/mcp",
        credentials: { api_key: "e2e-key" },
        enabled: true,
        is_public: false,
        group_ids: [],
      },
    });
    expect(created.ok()).toBeTruthy();
    entryId = (await created.json()).id;
    await page.close();
  });

  test("admin sees the installed server and can open it to everyone", async ({
    page,
  }) => {
    test.skip(!gatewayDeployed, "MCP_GATEWAY_ENABLED is not set on this stack");
    await loginAs(page, "admin");

    const catalogPage = new AdminMcpCatalogPage(page);
    await catalogPage.goto();
    await catalogPage.expectModuleEnabled(true);
    await catalogPage.expectEntryVisible(slug);
    await catalogPage.makePublic(slug);
  });

  test("a regular user sees the granted server and turns it on", async ({
    page,
  }) => {
    test.skip(!gatewayDeployed, "MCP_GATEWAY_ENABLED is not set on this stack");
    await loginAsRandomUser(page);

    const settingsPage = new UserSystemMcpPage(page);
    await settingsPage.goto();
    await settingsPage.expectServerVisible(slug);
    // A grant makes the server available; the user still has to switch it on.
    await settingsPage.enable(slug);
  });

  test.afterAll(async ({ browser }) => {
    if (!gatewayDeployed) return;
    const page = await browser.newPage();
    await loginAs(page, "admin");
    if (entryId !== null) {
      await page.request.delete(`/api/admin/mcp-catalog/entries/${entryId}`);
    }
    const settings = await page.request.get("/api/admin/settings");
    await page.request.patch("/api/admin/settings", {
      data: { ...(await settings.json()), mcp_gateway_enabled: false },
    });
    await page.close();
  });
});
