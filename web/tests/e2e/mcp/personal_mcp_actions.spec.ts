import { test, expect } from "@playwright/test";
import { loginAsWorkerUser } from "@tests/e2e/utils/auth";
import { ensureOnboardingComplete } from "@tests/e2e/utils/chatActions";
import {
  WORKER_USER_POOL_SIZE,
  workerUserCredentials,
} from "@tests/e2e/constants";
import { OnyxApiClient } from "@tests/e2e/utils/onyxApiClient";
import {
  dockerReachableMcpUrl,
  startMcpNoAuthServer,
  type McpServerProcess,
} from "@tests/e2e/utils/mcpServer";
import {
  grantAddAgents,
  deleteGrantGroups,
} from "@tests/e2e/utils/grantPermissions";
import { CraftMcpActionsPage } from "@tests/e2e/pages/CraftMcpActionsPage";
import { CraftAppsPage } from "@tests/e2e/pages/CraftAppsPage";
import { ToolsPopover } from "@tests/e2e/pages/ToolsPopover";
import { AgentEditorPage } from "@tests/e2e/pages/AgentEditorPage";

const PERSONAL_MCP_PORT = Number(process.env.MCP_PERSONAL_TEST_PORT || "8011");

test.describe("Personal MCP Actions", () => {
  test.describe.configure({ mode: "serial" });

  let serverProcess: McpServerProcess | null = null;
  let serverUrl: string;
  let uiServerId: number | null = null;
  let agentId: number | null = null;
  let workerIndex = 0;
  const grantGroupIds: number[] = [];
  const serverName = `PW Personal MCP ${Date.now()}`;

  test.beforeAll(async () => {
    serverProcess = await startMcpNoAuthServer({
      port: PERSONAL_MCP_PORT,
      bindHost: "0.0.0.0",
    });
    serverUrl = dockerReachableMcpUrl(serverProcess.address.port);
  });

  test.afterAll(async ({ browser }) => {
    const workerContext = await browser.newContext();
    const page = await workerContext.newPage();
    await loginAsWorkerUser(page, workerIndex);
    const client = new OnyxApiClient(page.request);
    if (agentId !== null) {
      await client.deleteAgent(agentId);
    }
    if (uiServerId !== null) {
      await client.deletePersonalMcpServer(uiServerId);
    }
    await workerContext.close();

    await deleteGrantGroups(browser, grantGroupIds);
    grantGroupIds.length = 0;

    if (serverProcess) {
      await serverProcess.stop();
    }
  });

  test.beforeEach(async ({ page }, testInfo) => {
    workerIndex = testInfo.workerIndex;
    await page.context().clearCookies();
    await loginAsWorkerUser(page, testInfo.workerIndex);
    await page.goto("/app");
    await ensureOnboardingComplete(page);
  });

  test("craft apps links to personal MCP actions", async ({ page }) => {
    const apps = new CraftAppsPage(page);
    await apps.goto();
    await apps.expectManageMyMcpVisible();
    await apps.openManageMyMcp();

    const personal = new CraftMcpActionsPage(page);
    await personal.expectHeadingVisible();
  });

  test("owner can add, authenticate, and pull tools", async ({ page }) => {
    const personal = new CraftMcpActionsPage(page);
    await personal.goto();
    await personal.expectPersonalSurface();

    await personal.openAddServerModal();
    await personal.fillServerDetails({
      name: serverName,
      description: "Personal MCP created via UI",
      url: serverUrl,
    });
    uiServerId = await personal.submitAddServer();

    await personal.selectAuthMethod("None");
    await personal.connectAndWaitForTools();
    await personal.expectServerCard(serverName);
    await personal.expandServerCard(serverName);
    await expect(personal.cardToolToggle("hello").first()).toBeVisible({
      timeout: 30_000,
    });
  });

  test("chat tools popover shows the personal server", async ({
    page,
    browser,
  }) => {
    expect(uiServerId).toBeTruthy();

    const { email } = workerUserCredentials(
      workerIndex % WORKER_USER_POOL_SIZE
    );
    grantGroupIds.push(await grantAddAgents(browser, email));

    await page.goto("/app");
    await ensureOnboardingComplete(page);

    const editor = new AgentEditorPage(page);
    await editor.openFromSidebar();
    await editor.fill({
      name: `Personal MCP Agent ${Date.now()}`,
      description: "Agent that uses a personal MCP server.",
      instructions: "Call hello when asked to greet.",
    });
    await editor.enableMcpServer(uiServerId!);
    await editor.enableFirstMcpTool(uiServerId!);
    agentId = await editor.create();

    const actions = new ToolsPopover(page);
    await actions.expectServerVisible(serverName);
    await expect(actions.serverRow(serverName)).toContainText(/Personal/i);
  });
});
