import { test, expect } from "@playwright/test";
import { loginAsWorkerUser } from "@tests/e2e/utils/auth";
import { LoopsPage } from "@tests/e2e/pages/LoopsPage";

test.describe("Craft Loops", () => {
  test("loop renders in list and detail drives controls", async ({
    page,
  }, testInfo) => {
    await loginAsWorkerUser(page, testInfo.workerIndex);

    const loops = new LoopsPage(page);
    await loops.gotoList();
    test.skip(
      !loops.isCraftEnabled(),
      "Onyx Craft is disabled in this environment"
    );

    const uniqueName = `E2E loop ${Date.now()}`;
    const loop = await loops.createLoopViaApi(uniqueName);
    try {
      // List: the loop row appears with its state badge.
      await page.reload();
      await page.waitForLoadState("networkidle");
      await loops.expectLoopRow(uniqueName);

      // Detail: badges, autopilot switch, ledger intake.
      await loops.openLoop(uniqueName);
      await loops.expectStateBadge("enabled");
      await expect(loops.autopilotSwitch).toBeVisible();
      await expect(loops.autopilotSwitch).toHaveAttribute(
        "aria-checked",
        "false"
      );

      // Autopilot flip → every gate turns auto → switch reflects on.
      await loops.autopilotSwitch.click();
      await expect(loops.autopilotSwitch).toHaveAttribute(
        "aria-checked",
        "true"
      );

      // Ledger intake through the API shows in the items table.
      await loops.seedItemViaApi(loop.id, "e2e-key-1");
      await page.reload();
      await page.waitForLoadState("networkidle");
      await loops.expectLedgerRow("e2e-key-1");

      // Pause flips the state badge.
      await loops.toggleStateButton.click();
      await loops.expectStateBadge("paused");
    } finally {
      await loops.deleteLoopViaApi(loop.id);
    }
  });
});
