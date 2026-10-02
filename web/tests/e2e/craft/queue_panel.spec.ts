/**
 * Follow-up queue panel: enqueue while a turn is running, drag to reorder,
 * edit back into the composer, remove, and send-now. The running turn comes
 * from a held-open event stream so the queue state is fully deterministic.
 */

import { expect, test } from "@playwright/test";
import { dragElementAbove } from "@tests/e2e/utils/dragUtils";
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

async function enqueue(page: CraftSessionPage, text: string): Promise<void> {
  await page.typeMessage(text);
  await page.pressEnter();
  await expect(page.queueRow(text)).toBeVisible({ timeout: 10000 });
}

test("enqueue while running, drag reorder, edit backfill, remove", async ({
  page,
}) => {
  const session = new CraftSessionPage(page);
  await session.goto(SESSION_ID);
  const held = await holdTurnOpen(page);

  await session.typeMessage("start the long turn");
  await session.pressEnter();
  await session.expectPrimaryAction(/Stop generating|停止生成/);  await enqueue(session, "first queued message");
  await enqueue(session, "second queued message");
  await expect(session.queuePanel).toContainText("2");

  // Drag the second row's handle above the first row to flip the order.
  // dnd-kit only listens for pointerdown on the drag handle.
  await dragElementAbove(
    session
      .queueRow("second queued message")
      .getByRole("button", { name: /Drag to reorder|拖/ }),
    session
      .queueRow("first queued message")
      .getByRole("button", { name: /Drag to reorder|拖/ }),
    page
  );
  await expect
    .poll(() => session.queueRows.allTextContents(), { timeout: 10000 })
    .toEqual(["second queued message", "first queued message"]);

  // Edit moves the text back into the composer and drops the row.
  await session
    .queueRow("second queued message")
    .getByRole("button", { name: /Edit in composer|编辑/ })
    .click();
  await expect(session.queueRow("second queued message")).toHaveCount(0);
  await expect(session.messageInput).toContainText("second queued message");

  // Remove the remaining queued row.
  await session
    .queueRow("first queued message")
    .getByRole("button", { name: /Remove|移除|删除/ })
    .click();
  await expect(session.queueRow("first queued message")).toHaveCount(0);
  await expect(session.queuePanel).toHaveCount(0);

  await held.release([]);
});

test("send now while running is refused and keeps the queued row", async ({
  page,
}) => {
  const session = new CraftSessionPage(page);
  await session.goto(SESSION_ID);
  const held = await holdTurnOpen(page);

  await session.typeMessage("the running turn");
  await session.pressEnter();
  await session.expectPrimaryAction(/Stop generating|停止生成/);
  const turnsAfterStart = held.turnsStarted();

  await enqueue(session, "jump the line");
  await session
    .queueRow("jump the line")
    .getByRole("button", { name: /Send now|立即发送/ })
    .click();

  // The guard refuses before dequeuing: the row survives, the toast explains,
  // and no second turn is started (FIFO sends it after the run finishes).
  await expect(page.getByText(/wait|等待/).first()).toBeVisible({
    timeout: 10000,
  });
  await expect(session.queueRow("jump the line")).toBeVisible();
  await expect
    .poll(() => held.turnsStarted(), { timeout: 5000 })
    .toBe(turnsAfterStart);

  await held.release([]);
});
