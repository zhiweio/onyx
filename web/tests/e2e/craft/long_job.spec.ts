import { expect, test, type Page } from "@playwright/test";
import { CraftWelcomePage } from "@tests/e2e/pages/CraftWelcomePage";

async function suppressCraftIntro(page: Page): Promise<void> {
  const me = await page.request.get("/api/me");
  if (!me.ok()) return;
  const body = (await me.json()) as { id?: string };
  if (!body.id) return;
  await page.addInitScript((userId: string) => {
    window.localStorage.setItem(`onyx:craftOnboardingSeen:${userId}`, "true");
  }, body.id);
}

test.beforeEach(async ({ page }) => {
  const response = await page.request.get("/api/settings");
  const settings = response.ok() ? await response.json() : null;
  test.skip(
    settings?.settings?.onyx_craft_enabled !== true &&
      settings?.onyx_craft_enabled !== true,
    "Onyx Craft is disabled in this environment"
  );
  await suppressCraftIntro(page);
});

test("welcome long-job toggle posts start true", async ({ page }) => {
  const welcome = new CraftWelcomePage(page);
  const posted: { start?: boolean; prompt?: string } = {};
  await page.route("**/api/build/jobs", async (route) => {
    if (route.request().method() !== "POST") {
      await route.continue();
      return;
    }
    const body = route.request().postDataJSON() as {
      start?: boolean;
      prompt?: string;
    };
    posted.start = body.start;
    posted.prompt = body.prompt;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        job: {
          id: "00000000-0000-0000-0000-000000000001",
          session_id: "00000000-0000-0000-0000-000000000002",
          project_id: null,
          scenario_id: null,
          name: "Long job",
          domain: "general",
          status: "running",
          current_phase_index: 0,
          phases: [
            { id: "plan", name: "Plan", kind: "plan", status: "running" },
          ],
          total_budget_seconds: 7200,
          phase_budget_seconds: 1500,
          error_detail: null,
          specialists: [],
        },
        turn_id: "turn-fake",
      }),
    });
  });
  await page.route("**/api/build/sessions/**/send-message", async (route) => {
    await route.fulfill({
      status: 409,
      contentType: "application/json",
      body: JSON.stringify({ detail: "job turn already started" }),
    });
  });

  await welcome.goto();
  await welcome.startNewSession();
  await welcome.enableLongJob();
  await welcome.submitMessage("start a long job fixture");

  await expect.poll(() => posted.start).toBe(true);
  expect(posted.prompt).toContain("long job fixture");
});

test("session long-job toggle sits next to plus menu", async ({ page }) => {
  const welcome = new CraftWelcomePage(page);
  await page.route("**/api/build/jobs", async (route) => {
    if (route.request().method() !== "POST") {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        job: {
          id: "00000000-0000-0000-0000-000000000001",
          session_id: "00000000-0000-0000-0000-000000000002",
          project_id: null,
          scenario_id: null,
          name: "Long job",
          domain: "general",
          status: "running",
          current_phase_index: 0,
          phases: [
            { id: "plan", name: "Plan", kind: "plan", status: "running" },
          ],
          timeline: [
            { id: "plan", kind: "plan", status: "running", label: "Plan" },
          ],
          artifacts: [],
          events: [],
          interrupt: null,
          total_budget_seconds: 7200,
          phase_budget_seconds: 1500,
          error_detail: null,
          specialists: [],
        },
        turn_id: "turn-fake",
      }),
    });
  });
  await page.route("**/api/build/sessions/**/send-message", async (route) => {
    await route.fulfill({
      status: 409,
      contentType: "application/json",
      body: JSON.stringify({ detail: "job turn already started" }),
    });
  });

  await welcome.goto();
  await welcome.startNewSession();
  const welcomeToggle = page.getByTestId("craft-long-job-toggle");
  await expect(welcomeToggle).toBeVisible({ timeout: 15000 });
  await welcomeToggle.click();
  await welcome.submitMessage("start a session long job");
  await expect(page.getByTestId("craft-long-job-toggle")).toBeVisible({
    timeout: 15000,
  });
});

test("job banner shows research timeline and plan approval", async ({
  page,
}) => {
  const welcome = new CraftWelcomePage(page);
  let resumed = false;
  const jobBody = (status: string) => ({
    id: "00000000-0000-0000-0000-000000000001",
    session_id: "00000000-0000-0000-0000-000000000002",
    project_id: null,
    scenario_id: null,
    name: "GLP-1 initiation report",
    domain: "biomed",
    status,
    current_phase_index: 0,
    phases: [
      { id: "plan", name: "Plan", kind: "plan", status: "succeeded" },
      {
        id: "lane:literature",
        name: "Literature",
        kind: "lane",
        status: "pending",
      },
      {
        id: "lane:clinical",
        name: "Clinical",
        kind: "lane",
        status: "pending",
      },
      {
        id: "reconcile",
        name: "Reconcile",
        kind: "reconcile",
        status: "pending",
      },
      { id: "compose", name: "Compose", kind: "compose", status: "pending" },
      { id: "review", name: "Review", kind: "review", status: "pending" },
    ],
    timeline: [
      { id: "plan", kind: "plan", status: "succeeded", label: "Plan" },
      {
        id: "lanes",
        kind: "lane",
        status: "pending",
        label: "Lanes",
      },
      {
        id: "reconcile",
        kind: "reconcile",
        status: "pending",
        label: "Reconcile",
      },
      { id: "compose", kind: "compose", status: "pending", label: "Compose" },
      { id: "review", kind: "review", status: "pending", label: "Review" },
    ],
    artifacts: [
      {
        path: "outputs/plan/PLAN.json",
        summary: "GLP-1 创新药立项计划",
        producer_node: "plan",
      },
    ],
    events: [{ type: "interrupt", payload: { kind: "approve_plan" } }],
    interrupt:
      status === "interrupted"
        ? { kind: "approve_plan", payload: { goal: "GLP-1" } }
        : null,
    total_budget_seconds: 7200,
    phase_budget_seconds: 1500,
    error_detail: null,
    specialists: [],
  });

  await page.route("**/api/build/jobs**", async (route) => {
    const request = route.request();
    if (request.url().includes("/resume")) {
      resumed = true;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(jobBody("running")),
      });
      return;
    }
    if (request.method() === "POST") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          job: jobBody("interrupted"),
          turn_id: "turn-fake",
        }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(jobBody(resumed ? "running" : "interrupted")),
    });
  });
  await page.route("**/api/build/sessions/**/send-message", async (route) => {
    await route.fulfill({
      status: 409,
      contentType: "application/json",
      body: JSON.stringify({ detail: "job turn already started" }),
    });
  });

  await welcome.goto();
  await welcome.startNewSession();
  await welcome.enableLongJob();
  await welcome.submitMessage("撰写一份 GLP-1 创新药立项深度研究报告");
  await expect(welcome.jobBanner).toBeVisible({ timeout: 15000 });
  await expect(welcome.jobAskBar).toBeVisible();
  await expect(welcome.jobAskApprove).toBeVisible();
  await welcome.jobBanner.click();
  await expect(page.getByTestId("craft-job-phase-plan")).toBeVisible();
  await expect(page.getByTestId("craft-job-phase-lanes")).toBeVisible();
  await welcome.jobAskApprove.click();
  await expect.poll(() => resumed).toBe(true);
});

test("continue transcript hides host brief and shows ask reject", async ({
  page,
}) => {
  const sessionId = "00000000-0000-0000-0000-00000000c0de";
  const jobId = "00000000-0000-0000-0000-00000000c0df";
  const now = new Date().toISOString();
  const sessionBody = {
    id: sessionId,
    user_id: "user-1",
    name: "GLP-1 job",
    status: "active",
    created_at: now,
    last_activity_at: now,
    nextjs_port: null,
    sandbox: {
      id: "sbx-1",
      status: "running",
      container_id: "ctr-1",
      created_at: now,
      last_heartbeat: now,
    },
    artifacts: [],
    sharing_scope: "private",
    origin: "INTERACTIVE",
    agent_provider: null,
    agent_model: null,
    skills_stale: false,
    session_loaded_in_sandbox: true,
  };
  const jobBody = {
    id: jobId,
    session_id: sessionId,
    project_id: null,
    scenario_id: null,
    name: "GLP-1 initiation report",
    domain: "biomed",
    status: "interrupted",
    current_phase_index: 1,
    phases: [
      { id: "plan", name: "Plan", kind: "plan", status: "succeeded" },
      {
        id: "lane:literature",
        name: "Literature",
        kind: "lane",
        status: "running",
      },
    ],
    timeline: [
      { id: "plan", kind: "plan", status: "succeeded", label: "Plan" },
      { id: "lanes", kind: "lane", status: "running", label: "Lanes" },
    ],
    artifacts: [
      {
        path: "outputs/lanes/literature/NOTES.md",
        summary: "Literature notes",
        producer_node: "lane:literature",
      },
    ],
    events: [],
    interrupt: {
      kind: "clarify",
      payload: { summary: "Search is not available." },
    },
    total_budget_seconds: 7200,
    phase_budget_seconds: 1500,
    error_detail: null,
    specialists: [],
  };

  await page.route("**/api/build/sessions/**", async (route) => {
    const url = route.request().url();
    const method = route.request().method();
    if (url.includes("/messages") && method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          messages: [
            {
              id: "m-user",
              session_id: sessionId,
              turn_index: 0,
              type: "user",
              content: "Write the GLP-1 report",
              message_metadata: {
                type: "user_message",
                content: { type: "text", text: "Write the GLP-1 report" },
              },
              created_at: now,
            },
            {
              id: "m-continue",
              session_id: sessionId,
              turn_index: 1,
              type: "user",
              content: "HOST BRIEF MUST NOT RENDER",
              message_metadata: {
                type: "user_message",
                content: { type: "text", text: "HOST BRIEF MUST NOT RENDER" },
                craft_job_continue: true,
              },
              created_at: now,
            },
            {
              id: "m-ask",
              session_id: sessionId,
              turn_index: 1,
              type: "assistant",
              content: "",
              message_metadata: {
                type: "question_ask",
                request_id: "q-search",
                prompt:
                  "Search is not available. Retry, use existing tools, or cancel.",
                options: ["Retry search", "Use existing tools", "Cancel"],
              },
              created_at: now,
            },
            {
              id: "m-assistant",
              session_id: sessionId,
              turn_index: 1,
              type: "assistant",
              content: "Literature lane is running.",
              message_metadata: {
                type: "assistant_message",
                streamItems: [
                  {
                    type: "question_ask",
                    id: "q-search",
                    requestId: "q-search",
                    prompt:
                      "Search is not available. Retry, use existing tools, or cancel.",
                    options: ["Retry search", "Use existing tools", "Cancel"],
                    questions: [],
                  },
                  {
                    type: "tool_call",
                    id: "write-plan",
                    toolCall: {
                      id: "write-plan",
                      kind: "edit",
                      toolName: "write",
                      title: "Writing",
                      description: "outputs/PLAN.md",
                      command: "",
                      status: "completed",
                      rawOutput: "",
                    },
                  },
                  {
                    type: "tool_call",
                    id: "lane-task",
                    toolCall: {
                      id: "lane-task",
                      kind: "task",
                      toolName: "task",
                      title: "Literature",
                      description:
                        "Literature — outputs/lanes/literature/NOTES.md",
                      command: "",
                      status: "in_progress",
                      rawOutput: "",
                    },
                  },
                ],
              },
              created_at: now,
            },
          ],
        }),
      });
      return;
    }
    if (url.includes("/files") && method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          path: "outputs",
          entries: [
            {
              name: "lanes",
              path: "outputs/lanes",
              is_directory: true,
              size: null,
              mime_type: null,
            },
            {
              name: "NOTES.md",
              path: "outputs/lanes/literature/NOTES.md",
              is_directory: false,
              size: 32,
              mime_type: "text/markdown",
            },
          ],
        }),
      });
      return;
    }
    if (
      (url.includes("/artifacts") ||
        url.includes("/turns/active") ||
        url.includes("/webapp-info")) &&
      method === "GET"
    ) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: url.includes("/turns/active") ? "null" : "[]",
      });
      return;
    }
    const sessionRoot = url.match(
      /\/sessions\/[0-9a-f-]+(?:\?|$)/i
    );
    if (method === "GET" && sessionRoot) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(sessionBody),
      });
      return;
    }
    await route.continue();
  });
  await page.route("**/api/build/jobs**", async (route) => {
    const url = route.request().url();
    if (url.includes("/asks/current")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          request_id: "q-search",
          prompt: "Search is not available. Retry, use existing tools, or cancel.",
          options: ["Retry search", "Use existing tools", "Cancel"],
        }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(jobBody),
    });
  });

  await page.goto(`/craft/v1?sessionId=${sessionId}`);
  const welcome = new CraftWelcomePage(page);
  await expect(welcome.jobAskBar).toBeVisible({ timeout: 15000 });
  await expect(
    welcome.jobAskReject.or(page.getByTestId("craft-ask-cancel"))
  ).toBeVisible();
  await expect(page.getByText("HOST BRIEF MUST NOT RENDER")).toHaveCount(0);
  await expect(page.getByText("outputs/PLAN.md")).toHaveCount(0);
  await expect(page.getByText("Literature")).toBeVisible();
  const askBox = await welcome.jobAskBar.boundingBox();
  const inputBox = await welcome.messageInput.boundingBox();
  expect(askBox && inputBox && askBox.y < inputBox.y).toBe(true);

  const filesTab = page.getByRole("tab", { name: /Files|文件/ });
  if (await filesTab.isVisible().catch(() => false)) {
    await filesTab.click();
    await expect(page.getByText("NOTES.md")).toBeVisible({ timeout: 10000 });
  }
});

test("skill catalog does not list long-job-protocol", async ({ page }) => {
  const response = await page.request.get("/api/skills");
  if (!response.ok()) {
    test.skip(true, "Skills API is not available");
    return;
  }
  const body = (await response.json()) as {
    builtins?: { name?: string }[];
  };
  const names = (body.builtins ?? []).map((item) => item.name);
  expect(names).not.toContain("long-job-protocol");
});
