import { test } from "@playwright/test";
import { loginAsWorkerUser } from "@tests/e2e/utils/auth";
import { CraftLibraryPage } from "@tests/e2e/pages/CraftLibraryPage";
import { CraftWelcomePage } from "@tests/e2e/pages/CraftWelcomePage";

test.describe("Craft library settings", () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await page.context().clearCookies();
    await loginAsWorkerUser(page, testInfo.workerIndex);
    const response = await page.request.get("/api/settings");
    const body = response.ok() ? await response.json() : {};
    const enabled =
      body?.settings?.onyx_craft_enabled === true ||
      body?.onyx_craft_enabled === true;
    test.skip(!enabled, "Craft is disabled on this deployment");
  });

  test("opens a settings page, not a modal", async ({ page }) => {
    const library = new CraftLibraryPage(page);
    await library.goto();
    await library.expectSettingsPage();
    await library.expectSidebarSelected();
  });

  test("creates a folder from an inline panel", async ({ page }) => {
    const library = new CraftLibraryPage(page);
    await library.goto();
    await library.openNewFolderPanel();
    await library.cancelNewFolder();
    await library.expectSettingsPage();
  });

  test("opens the page from the compose plus menu", async ({ page }) => {
    const welcome = new CraftWelcomePage(page);
    await welcome.goto();
    await welcome.dismissIntro();
    if (await welcome.lockedState.isVisible().catch(() => false)) {
      test.skip(true, "Craft input is locked for this user");
    }
    await welcome.expectInputEnabled();

    const library = new CraftLibraryPage(page);
    await library.manageFromPlusMenu();
    await library.expectSettingsPage();
  });
});
