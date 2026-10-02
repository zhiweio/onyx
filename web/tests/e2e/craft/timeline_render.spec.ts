/**
 * Timeline rendering over a scripted SSE turn: thinking card, tool summary
 * rows with diff counts, live-tail turn status header, final answer, copy
 * action, and history re-render from persisted streamItems after a reload.
 */

import { expect, test } from "@playwright/test";
import { CraftSessionPage } from "@tests/e2e/craft/helpers/CraftSessionPage";
import {
  SESSION_ID,
  assistantMessage,
  mockCraftBackend,
  savedText,
  savedThinking,
  savedToolCall,
  suppressCraftIntro,
  thinkingChunk,
  textChunk,
  toolCallProgress,
  toolCallStart,
  userMessage,
} from "@tests/e2e/craft/helpers/craftSessionMock";

test.beforeEach(async ({ page }) => {
  await suppressCraftIntro(page);
});

const SCRIPTED_TURN = [
  thinkingChunk("Analyzing the request step by step"),
  toolCallStart("tc-1", "mkdir -p outputs/hello"),
  toolCallProgress("tc-1", { status: "completed", rawOutput: "" }),
  textChunk("All done — created the folder."),
];

/** POST /jobs accept + scripted SSE for the launched turn. */
async function mockScriptedTurn(page: import("@playwright/test").Page): Promise<void> {
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
          turn_id: "turn-1",
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
      body: `${SCRIPTED_TURN.map(
        (packet) => `event: message\ndata: ${JSON.stringify(packet)}\n\n`
      ).join("")}event: message\ndata: {"type":"prompt_response"}\n\n`,
    });
  });
}

test("scripted turn renders thinking, tool row, and final answer", async ({
  page,
}) => {
  // Seed the transcript the turn settles into: after prompt_response the
  // client refetches /messages and reconciles, replacing local state.
  await mockCraftBackend(page, {
    messages: [
      userMessage({ id: "m1", content: "run the scripted turn", turnIndex: 0 }),
      assistantMessage({
        id: "m2",
        turnIndex: 0,
        content: "All done — created the folder.",
        streamItems: [
          savedThinking("th-1", "Analyzing the request step by step"),
          savedToolCall("tc-1", { command: "mkdir -p outputs/hello" }),
          savedText("tx-1", "All done — created the folder."),
        ],
      }),
    ],
  });
  const session = new CraftSessionPage(page);
  await session.goto(SESSION_ID);
  await mockScriptedTurn(page);

  await session.typeMessage("run the scripted turn");
  await session.pressEnter();

  // The scripted stream completes instantly; assert the settled transcript.
  // The prompt_response triggers a /messages reconcile that re-mounts rows,
  // so wait for the settled answer before interacting with rows.
  await expect(page.getByText("All done — created the folder.")).toBeVisible({
    timeout: 15000,
  });
  // Thinking card trigger (duration label appears with real timings).
  await expect(page.getByText(/Thought|思考/).first()).toBeVisible();
  // Tool summary row: expand the phase group to see the command body.
  await page.getByRole("button", { name: /Show details|显示详情/ })
    .first()
    .click();
  await expect(
    page.getByText("mkdir -p outputs/hello").first()
  ).toBeVisible();
  // The agent row exposes the merged-turn copy action on hover.
  await page.getByText("All done — created the folder.").hover();
  await expect(session.agentCopyButton).toBeVisible();
});

test("history re-renders from persisted streamItems after reload", async ({
  page,
}) => {
  await mockCraftBackend(page, {
    messages: [
      userMessage({ id: "m1", content: "create the folder", turnIndex: 0 }),
      assistantMessage({
        id: "m2",
        turnIndex: 0,
        streamItems: [
          savedThinking("th-1", "Persisted thinking"),
          savedToolCall("tc-9", { command: "mkdir -p persisted/path" }),
          savedText("tx-1", "Persisted answer"),
        ],
      }),
    ],
  });
  const session = new CraftSessionPage(page);
  await session.goto(SESSION_ID);

  await expect(page.getByText("create the folder")).toBeVisible();
  await expect(page.getByText("Persisted answer")).toBeVisible();
  // Collapsed phase groups summarize as a phase label; expand to see the
  // command body.
  await page.getByRole("button", { name: /Show details|显示详情/ }).click();
  await expect(
    page.getByText("mkdir -p persisted/path").first()
  ).toBeVisible();
  // Idle session: no live tail, no stop action.
  await expect(page.locator("[data-craft-live-tail]")).toHaveCount(0);
});

test("edit tool call shows diff counts on the summary row", async ({
  page,
}) => {
  await mockCraftBackend(page, {
    messages: [
      userMessage({ id: "m1", content: "write hello.py", turnIndex: 0 }),
      assistantMessage({
        id: "m2",
        turnIndex: 0,
        streamItems: [
          savedToolCall("tc-edit", {
            kind: "edit",
            toolName: "write",
            title: "Write",
            description: "outputs/hello/hello.py",
            command: "",
            status: "completed",
            isNewFile: true,
            oldContent: "",
            newContent: 'print("Hello Craft")',
          }),
        ],
      }),
    ],
  });
  const session = new CraftSessionPage(page);
  await session.goto(SESSION_ID);

  await expect(page.getByText("outputs/hello/hello.py").first()).toBeVisible();
  // The phase-group row summarizes the write; expand it to see the block's
  // per-call diff counts.
  await page.getByRole("button", { name: /Show details|显示详情/ }).click();
  await expect(page.getByText("+1")).toBeVisible();
  await expect(page.getByText("−1")).toBeVisible();
  await expect(page.getByText(/Done|完成/).first()).toBeVisible();
});

test("clicking a write file chip opens the diff tab in the output panel", async ({
  page,
}) => {
  const editTool = {
    type: "tool_call",
    id: "tc-w1",
    toolCall: {
      id: "tc-w1",
      kind: "edit",
      toolName: "write",
      title: "Write",
      description: "outputs/hello.md",
      command: "",
      status: "completed",
      rawOutput: "",
      filePath: "outputs/hello.md",
      oldContent: "old line",
      newContent: "old line\nnew line",
    },
  };
  await mockCraftBackend(page, {
    messages: [
      userMessage({ id: "m1", content: "write hello.md", turnIndex: 0 }),
      assistantMessage({
        id: "m2",
        turnIndex: 0,
        content: "wrote it",
        streamItems: [editTool, savedText("tx-1", "wrote it")],
      }),
    ],
  });
  const session = new CraftSessionPage(page);
  await session.goto(SESSION_ID);

  // Expand the phase-group row first; the chip lives on the inner block.
  await page
    .getByRole("button", { name: /Show details|显示详情/ })
    .first()
    .click();
  const chip = page.getByTestId("tool-file-chip").first();
  await expect(chip).toBeVisible({ timeout: 15000 });
  await expect(chip).toContainText("hello.md");
  await chip.click();

  // Panel opens with the diff tab active, Diff badge, and diff content.
  await expect(page.getByTestId("diff-tab-badge").first()).toBeVisible({
    timeout: 10000,
  });
  await expect(page.getByTestId("diff-tab-breadcrumb")).toContainText(
    "hello.md"
  );
  await page.waitForTimeout(400);
  const body = await page.evaluate(() => document.body.innerText);
  expect(body).toContain("new line");

  // The turn-end summary card lists the change (expand to see the file row).
  const summary = page.getByTestId("file-changes-summary");
  await expect(summary).toBeVisible();
  await expect(summary).toContainText("1");
  await summary.getByRole("button").click();
  await expect(
    page.getByTestId("file-changes-row-hello.md")
  ).toBeVisible();
});
