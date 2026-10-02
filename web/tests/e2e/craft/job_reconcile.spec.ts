/**
 * F1 regression: when a job settles (cancelled variant — the same effect
 * branch as failed) while the composer shows Stop and no SSE settle path
 * ran, the store must reconcile from the job poller's terminal status
 * WITHOUT a reload.
 *
 * Drive path: the cancel click calls mutateCraftJob (immediate SWR
 * refetch — SWR interval polling does not fire in headless runs), the mock
 * flips to cancelled, and the F1 effect must recover the composer.
 */

import { expect, test } from "@playwright/test";
import { CraftSessionPage } from "@tests/e2e/craft/helpers/CraftSessionPage";
import {
  SESSION_ID,
  holdTurnOpen,
  mockCraftBackend,
  suppressCraftIntro,
} from "@tests/e2e/craft/helpers/craftSessionMock";

test.beforeEach(async ({ page }) => {
  await suppressCraftIntro(page);
  await mockCraftBackend(page);
});

test("job settle auto-recovers the composer to Send without a reload", async ({
  page,
}) => {
  const session = new CraftSessionPage(page);
  await session.goto(SESSION_ID);
  const held = await holdTurnOpen(page);

  await session.typeMessage("trigger the job");
  await session.pressEnter();
  await session.expectPrimaryAction(/Stop generating|停止生成/);

  // Cancel the job (mutateCraftJob → immediate refetch → cancelled status).
  await page.getByTestId("craft-job-cancel").click();


  // F1's reconcile effect must run from the terminal job status — composer
  // back to Send, no page.reload() anywhere in this test.
  await session.expectPrimaryAction(/Send|发送/);

  // The store is no longer stuck: the composer accepts a new message.
  await session.typeMessage("after recovery");
  await expect(session.messageInput).toContainText("after recovery");

  await held.fail("cleanup");
});
