import { test, expect } from "@playwright/test";
import { ADMIN_ROUTES } from "@/lib/admin-routes";

test.use({ storageState: "admin_auth.json" });

test("craft apps MCP tab carries the unified search header", async ({
  page,
}) => {
  await page.goto(`${ADMIN_ROUTES.CRAFT_APPS.path}?tab=mcp`);
  await page.waitForLoadState("networkidle");

  // The MCP tab shares the admin/mcp-actions list chrome: a search input
  // above the cards whenever servers exist.
  const search = page.getByRole("textbox").first();
  await expect.poll(async () => search.isVisible()).toBe(true);
});

test("craft apps MCP card expands into inline tools", async ({ page }) => {
  await page.goto(`${ADMIN_ROUTES.CRAFT_APPS.path}?tab=mcp`);
  await page.waitForLoadState("networkidle");

  // The shared expandable tools card (chat-preferences design). Skips when
  // this deployment has no MCP servers configured.
  const expand = page
    .getByText("展开", { exact: true })
    .or(page.getByText("Expand", { exact: true }));
  const count = await expand.count();
  test.skip(count === 0, "No MCP servers configured");

  await expand.first().click();
  const fold = page
    .getByText("收起", { exact: true })
    .or(page.getByText("Fold", { exact: true }));
  await expect(fold.first()).toBeVisible({ timeout: 15000 });
});

test("im bots page renders platforms and visibility switches", async ({
  page,
}) => {
  await page.goto(ADMIN_ROUTES.IM_BOTS.path);
  await page.waitForLoadState("networkidle");

  await expect(page.getByTestId("im-bots-page")).toBeVisible();
  // One card per China platform, each with a copyable callback URL.
  await expect(page.getByText(/\/onyxbot\/wecom\/callback/)).toBeVisible();
  await expect(page.getByText(/\/onyxbot\/dingtalk\/callback/)).toBeVisible();
  await expect(page.getByText(/\/onyxbot\/feishu\/callback/)).toBeVisible();
  // The Slack/Discord sidebar visibility switches live on this page.
  await expect(page.getByRole("switch")).toHaveCount(2, { timeout: 15000 });
});
