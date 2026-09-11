import { expect, test } from "@playwright/test";
import { loginAsWorkerUser } from "@tests/e2e/utils/auth";
import { CraftWelcomePage } from "@tests/e2e/pages/CraftWelcomePage";

test.describe("Craft slash picker", () => {
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

  test("slash lists a built-in skill on the welcome input", async ({
    page,
  }) => {
    const welcome = new CraftWelcomePage(page);
    await welcome.goto();
    await welcome.dismissIntro();
    if (await welcome.lockedState.isVisible().catch(() => false)) {
      test.skip(true, "Craft input is locked for this user");
    }
    await welcome.expectInputEnabled();
    await welcome.openSlashPicker("docx");
    await expect(welcome.skillPickerRow("docx")).toBeVisible();
  });
});
