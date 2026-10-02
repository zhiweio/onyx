/**
 * Retry and edit-and-resend on the finished timeline: retry button visibility
 * when idle and the edit-resend inline composer that POSTs the edited content
 * to the retry-turn endpoint.
 */

import { expect, test, type Page } from "@playwright/test";
import { CraftSessionPage } from "@tests/e2e/craft/helpers/CraftSessionPage";
import {
  SESSION_ID,
  assistantMessage,
  mockCraftBackend,
  suppressCraftIntro,
  savedText,
  userMessage,
} from "@tests/e2e/craft/helpers/craftSessionMock";

test.beforeEach(async ({ page }) => {
  await suppressCraftIntro(page);
});

async function mockHistory(
  page: Page,
  opts: { withAssistant?: boolean } = {}
): Promise<void> {
  const user = userMessage({
    id: "m1",
    content: "original user message",
    turnIndex: 0,
    createdAt: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
  });
  const messages: unknown[] = [user];
  if (opts.withAssistant !== false) {
    messages.push(
      assistantMessage({
        id: "m2",
        turnIndex: 0,
        content: "assistant replied",
        streamItems: [savedText("tx-1", "assistant replied")],
      })
    );
  }
  await mockCraftBackend(page, { messages });
}

function mockRetryTurn(
  page: Page,
  bodies: Record<string, unknown>[]
): void {
  void page.route("**/api/build/sessions/**/retry-turn", async (route) => {
    bodies.push(route.request().postDataJSON() as Record<string, unknown>);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ turn_id: "turn-retry", turn_index: 2 }),
    });
  });
  void page.route("**/api/build/sessions/**/turns/**/events", async (route) => {
    // Hold the turn open long enough that the running state survives
    // the spec's own poll-assert round trip.
    await new Promise((resolve) => setTimeout(resolve, 4000));
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: 'event: message\ndata: {"type":"prompt_response"}\n\n',
    });
  });
}

test("idle history shows the retry button; clicking posts an empty retry-turn", async ({
  page,
}) => {
  await mockHistory(page);
  const session = new CraftSessionPage(page);
  await session.goto(SESSION_ID);

  // Row actions are hover-revealed.
  await page.getByText("assistant replied").hover();
  await expect(session.retryButton).toBeVisible({ timeout: 15000 });

  const retryBodies: Record<string, unknown>[] = [];
  mockRetryTurn(page, retryBodies);

  await session.retryButton.click();
  await expect.poll(() => retryBodies.length, { timeout: 10000 }).toBe(1);
  expect(retryBodies[0]).toEqual({});
});

test("edit-and-resend opens the inline editor and posts edited content", async ({
  page,
}) => {
  // No assistant message: the resent turn keeps the user message last, so the
  // live tail (and its timer) render while the mock stream is held open.
  await mockHistory(page, { withAssistant: false });
  const session = new CraftSessionPage(page);
  await session.goto(SESSION_ID);

  // Row actions are hover-revealed; hover the bubble before clicking.
  await page.getByText("original user message").hover();
  await session.userEditButton.click({ timeout: 15000 });
  const editEditor = page.getByTestId("CraftUserMessage/edit-editor");
  await expect(editEditor).toBeVisible();
  const editInput = page.getByTestId("craft-message-edit-input");
  await expect(editInput).toContainText("original user message");

  const retryBodies: Record<string, unknown>[] = [];
  mockRetryTurn(page, retryBodies);

  await editInput.fill("");
  await editInput.pressSequentially("edited user message");
  await editEditor.getByRole("button", { name: /Resend|重发/ }).click();

  await expect.poll(() => retryBodies.length, { timeout: 10000 }).toBe(1);
  expect(String(retryBodies[0]?.content)).toBe("edited user message");

  // The resent turn anchors its timer to the resend, not the original
  // message's timestamp (the message row is rewritten in place).
  const turnStatus = page.getByTestId("craft-turn-status");
  await expect(turnStatus).toBeVisible({ timeout: 15000 });
  // Seconds-scale elapsed: the original message is 2h old, so only the
  // resend-anchored override can produce this.
  await expect(turnStatus).toHaveText(/(已工作|Working for) [0-9]{1,2}s/);
});
