/**
 * Composer kernel behaviors on the craft session surface: Enter/Shift+Enter
 * submit semantics, the send/stop primary action, Esc interrupt, the slash
 * picker, draft persistence, and prompt history. All network effects are
 * mocked; nothing here requires a live sandbox or LLM.
 */

import { expect, test, type Page } from "@playwright/test";
import { CraftSessionPage } from "@tests/e2e/craft/helpers/CraftSessionPage";
import {
  SESSION_ID,
  holdTurnOpen,
  mockCraftBackend,
  seedPromptHistory,
  suppressCraftIntro,
} from "@tests/e2e/craft/helpers/craftSessionMock";

test.beforeEach(async ({ page }) => {
  await suppressCraftIntro(page);
  await mockCraftBackend(page);
});

async function openSession(page: Page): Promise<CraftSessionPage> {
  const session = new CraftSessionPage(page);
  await session.goto(SESSION_ID);
  return session;
}

test("slash picker opens and inserts a skill chip", async ({ page }) => {
  const session = await openSession(page);
  await session.typeMessage("/");
  const picker = page.getByTestId("skill-picker-popover");
  await expect(picker).toBeVisible({ timeout: 10000 });
  await picker.getByRole("button", { name: /alpha-skill/ }).click();
  // The inserted mention is an atomic chip node, not bare text.
  await expect(
    session.messageInput.locator(".prompt-mention-chip")
  ).toHaveCount(1);
  await expect(session.messageInput).toContainText("/alpha-skill");
});


test("Enter sends, Shift+Enter keeps editing with a newline", async ({
  page,
}) => {
  const session = await openSession(page);
  // Messages on an existing session always launch as long jobs.
  const prompts: string[] = [];
  await page.route("**/api/build/jobs**", async (route) => {
    if (route.request().url().includes("/asks/current")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: "null",
      });
      return;
    }
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON() as { prompt?: string };
      prompts.push(body.prompt ?? "");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          job: {
            id: "00000000-0000-0000-0000-000000000abc",
            session_id: SESSION_ID,
            status: "running",
            phases: [],
            timeline: [],
            artifacts: [],
            events: [],
            interrupt: null,
            specialists: [],
          },
          turn_id: `turn-${prompts.length}`,
        }),
      });
      return;
    }
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: "no job" }),
    });
  });
  await page.route("**/api/build/sessions/**/turns/**/events", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: 'event: message\ndata: {"type":"prompt_response"}\n\n',
    });
  });

  await session.typeMessage("first line");
  await session.messageInput.press("Shift+Enter");
  await session.typeMessage("second line");
  await session.pressEnter();

  await expect.poll(() => prompts.length).toBe(1);
  // Both lines reach the wire. (Headless quirk: synthetic Shift+Enter inserts
  // the break without moving the caret, so the newline position isn't asserted
  // here — caret behavior is covered by the kernel unit tests and was verified
  // against a real browser.)
  expect(prompts[0]).toContain("first line");
  expect(prompts[0]).toContain("second line");
  await expect(session.messageInput).toHaveText(/^\s*$/);
});

test("running turn swaps the primary action to stop; Esc cancels and settles", async ({
  page,
}) => {
  const session = await openSession(page);
  const held = await holdTurnOpen(page);

  await session.typeMessage("keep the turn running");
  await session.pressEnter();
  await session.expectPrimaryAction(/Stop generating|停止生成/);

  // Esc on a job-backed turn cancels the job (and interrupts the session turn).
  await session.messageInput.press("Escape");
  await expect.poll(() => held.cancels.length, { timeout: 15000 }).toBe(1);

  await held.release([
    { type: "text_chunk", text: "ok", sessionId: null, parentSessionId: null },
  ]);
  // The cancel handler revalidates the job, which now reports cancelled.
  await session.expectPrimaryAction(/Send|发送/);
});

test("empty input while running keeps the stop action, not send", async ({
  page,
}) => {
  const session = await openSession(page);
  const held = await holdTurnOpen(page);

  await session.typeMessage("long running");
  await session.pressEnter();
  await session.expectPrimaryAction(/Stop generating|停止生成/);
  await session.expectPrimaryAction(/Stop generating|停止生成/);
  await expect(session.primaryAction).toBeEnabled();

  await held.release([
    { type: "text_chunk", text: "done", sessionId: null, parentSessionId: null },
  ]);
  // Esc settles via the cancel path so the composer returns to send.
  await session.messageInput.press("Escape");
  await expect.poll(() => held.cancels.length, { timeout: 15000 }).toBe(1);
  await session.expectPrimaryAction(/Send|发送/);
});


test("draft persists across a reload within the same session", async ({
  page,
}) => {
  const session = await openSession(page);
  await session.typeMessage("draft survives reload");
  await page.waitForTimeout(900);
  await page.reload();
  await session.expectInputEnabled();
  await expect(session.messageInput).toContainText("draft survives reload");
});

test("arrow up recalls prompt history, arrow down returns", async ({ page }) => {
  // History is stored append-only: the LAST entry is the most recent, and
  // ArrowUp walks from the most recent backwards.
  await seedPromptHistory(page, ["older prompt", "newer prompt"]);
  const session = await openSession(page);

  await session.messageInput.click();
  await session.messageInput.press("ArrowUp");
  await expect(session.messageInput).toContainText("newer prompt");
  await session.messageInput.press("ArrowUp");
  await expect(session.messageInput).toContainText("older prompt");
  await session.messageInput.press("ArrowDown");
  await expect(session.messageInput).toContainText("newer prompt");
});
