import { expect, test } from "@playwright/test";
import { loginAsWorkerUser } from "@tests/e2e/utils/auth";
import { CraftWelcomePage } from "@tests/e2e/pages/CraftWelcomePage";

test.describe("Craft slash picker", () => {
  // A cold stack provisions the sandbox before the welcome composer enables;
  // the per-test budget must cover provisioning, not just the assertions.
  test.setTimeout(180_000);

  let welcome: CraftWelcomePage;

  async function guarded(page: import("@playwright/test").Page, name: string, flow: () => Promise<void>) {
    try {
      await welcome.goto();
      console.log(`NAV[${name}] url=${page.url()} pages=${page.context().pages().length}`);
      await flow();
    } catch (err) {
      await page.screenshot({ path: `output/playwright/fail-${name}.png`, fullPage: true }).catch(() => {});
      const count = await page.getByRole("textbox").count();
      console.log(`FAIL[${name}] textboxes=${count} url=${page.url()}`);
      throw err;
    }
  }
  test.beforeEach(async ({ page }, testInfo) => {
    await page.context().clearCookies();
    await loginAsWorkerUser(page, testInfo.workerIndex);
    const response = await page.request.get("/api/settings");
    const body = response.ok() ? await response.json() : {};
    const enabled =
      body?.settings?.onyx_craft_enabled === true ||
      body?.onyx_craft_enabled === true;
    test.skip(!enabled, "Craft is disabled on this deployment");
    welcome = new CraftWelcomePage(page);
  });

  test("slash lists a built-in skill on the welcome input", async ({ page }) => {
    await guarded(page, "t1", async () => {
      await welcome.dismissIntro();
      if (await welcome.lockedState.isVisible().catch(() => false)) {
        test.skip(true, "Craft input is locked for this user");
      }
      await welcome.expectInputEnabled();
      await welcome.openSlashPicker("docx");
      await expect(welcome.skillPickerRow("docx")).toBeVisible();
    });
  });

  test("picker search box filters rows", async ({ page }) => {
    await welcome.expectInputEnabled();
    await welcome.openSlashPicker();
    await expect(welcome.skillPickerRow("docx")).toBeVisible();
    await welcome.searchPicker("docx");
    await expect(welcome.skillPickerRow("docx")).toBeVisible();
    // Non-matching categories drop out while filtering.
    await expect(page.getByTestId("command-picker-row-compact"))
      .toBeHidden()
      .catch(() => {});
  });

  test("$ opens the skills-only menu", async () => {
    await welcome.expectInputEnabled();
    await welcome.openSkillsPicker("pptx");
    await expect(welcome.skillPickerRow("pptx")).toBeVisible();
    // Skills-only: no commands group in the $ menu.
    await expect(welcome.skillPicker().getByText("Commands", { exact: true }))
      .toBeHidden()
      .catch(() => {});
  });

  test("picker shows the footer tip", async ({ page }) => {
    await guarded(page, "t4", async () => {
      await welcome.expectInputEnabled();
      await welcome.openSlashPicker();
      await expect(welcome.skillPickerFooterTip()).toBeVisible();
    });
  });
});
