/**
 * Scroll behavior on a history tall enough to overflow: the floating
 * back-to-bottom button appears on user scroll and returns the view, and the
 * per-session scroll position is remembered across a reload. The virtualized
 * timeline mounts at the top, so specs scroll through the history explicitly.
 */

import { expect, test, type Page } from "@playwright/test";
import { CraftSessionPage } from "@tests/e2e/craft/helpers/CraftSessionPage";
import {
  SESSION_ID,
  assistantMessage,
  mockCraftBackend,
  savedText,
  suppressCraftIntro,
  userMessage,
} from "@tests/e2e/craft/helpers/craftSessionMock";

test.beforeEach(async ({ page }) => {
  await suppressCraftIntro(page);
});

async function mockTallHistory(page: Page): Promise<void> {
  const messages: unknown[] = [];
  for (let i = 0; i < 14; i += 1) {
    messages.push(
      userMessage({
        id: `u${i}`,
        content: `question number ${i} — please answer at length`,
        turnIndex: i,
      })
    );
    messages.push(
      assistantMessage({
        id: `a${i}`,
        turnIndex: i,
        content: `Answer ${i}`,
        streamItems: [
          savedText(
            `tx-${i}`,
            `Answer ${i}: a deliberately long paragraph so the conversation timeline overflows the viewport and needs scrolling for the e2e assertions to be meaningful.`
          ),
        ],
      })
    );
  }
  await mockCraftBackend(page, { messages });
}

function backToBottom(page: Page) {
  return page.getByRole("button", {
    name: /Scroll to bottom|滚动到底部|底部/,
  });
}

test("scrolling up reveals the back-to-bottom button; clicking returns to the bottom", async ({
  page,
}) => {
  await mockTallHistory(page);
  const session = new CraftSessionPage(page);
  await session.goto(SESSION_ID);

  await expect(page.getByText(/question number 0/).first()).toBeVisible({
    timeout: 15000,
  });
  // Wheel to the bottom of the history.
  await page.mouse.move(548, 400);
  await page.mouse.wheel(0, 20000);
  await expect(page.getByText(/Answer 13/).first()).toBeVisible({
    timeout: 15000,
  });

  // Wheel up: the floating back-to-bottom button appears.
  await page.mouse.wheel(0, -900);
  await expect(backToBottom(page)).toBeVisible({ timeout: 10000 });

  await backToBottom(page).click();
  await expect(backToBottom(page)).toBeHidden({ timeout: 10000 });
  await expect(page.getByText(/Answer 13/).first()).toBeVisible();
});

test("scroll position is remembered for the session across a reload", async ({
  page,
}) => {
  await mockTallHistory(page);
  const session = new CraftSessionPage(page);
  await session.goto(SESSION_ID);

  await expect(page.getByText(/question number 0/).first()).toBeVisible({
    timeout: 15000,
  });
  await page.mouse.move(548, 400);
  await page.mouse.wheel(0, 20000);
  await expect(page.getByText(/Answer 13/).first()).toBeVisible({
    timeout: 15000,
  });
  // Scroll up so the position (not the bottom) is the state to remember.
  await page.mouse.wheel(0, -1200);
  await page.waitForTimeout(600);

  await page.reload();
  await expect(
    page.getByText(/question number 0|Answer 0/).first()
  ).toBeVisible({ timeout: 15000 });

  // The memory key stores the scroll ratio for this session.
  const memory = await page.evaluate((sessionId) => {
    return window.localStorage.getItem(`craft-scroll-memory:v1:${sessionId}`);
  }, SESSION_ID);
  expect(memory).not.toBeNull();
});
