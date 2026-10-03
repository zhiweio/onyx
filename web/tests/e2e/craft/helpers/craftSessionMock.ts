/**
 * Deterministic backend mocks for craft session specs: the session/message
 * CRUD surface, a scripted interactive turn driven over the SSE event stream,
 * and a held-open variant that keeps a turn "running" until the spec releases
 * it. Specs stay black-box: they only touch the UI and assert on network
 * effects, mirroring the mocking style of craft/long_job.spec.ts.
 */

import { type Page, type Route } from "@playwright/test";

export const SESSION_ID = "00000000-0000-0000-0000-00000000beef";

const NOW = "2026-01-01T00:00:00.000Z";

export interface CraftUserMessage {
  id: string;
  content: string;
  turnIndex: number;
  createdAt?: string;
}

export interface CraftAssistantMessage {
  id: string;
  turnIndex: number;
  content?: string;
  streamItems: unknown[];
  createdAt?: string;
}

export function sessionBody(overrides: Record<string, unknown> = {}) {
  return {
    id: SESSION_ID,
    user_id: "user-1",
    name: "Craft UI spec session",
    status: "active",
    created_at: NOW,
    last_activity_at: NOW,
    nextjs_port: null,
    sandbox: {
      id: "sbx-1",
      status: "running",
      container_id: "ctr-1",
      created_at: NOW,
      last_heartbeat: NOW,
    },
    artifacts: [],
    sharing_scope: "private",
    origin: "INTERACTIVE",
    agent_provider: null,
    agent_model: null,
    skills_stale: false,
    session_loaded_in_sandbox: true,
    ...overrides,
  };
}

export function userMessage(msg: CraftUserMessage) {
  return {
    id: msg.id,
    session_id: SESSION_ID,
    turn_index: msg.turnIndex,
    type: "user",
    content: msg.content,
    message_metadata: {
      type: "user_message",
      content: { type: "text", text: msg.content },
    },
    created_at: msg.createdAt ?? NOW,
  };
}

export function assistantMessage(msg: CraftAssistantMessage) {
  return {
    id: msg.id,
    session_id: SESSION_ID,
    turn_index: msg.turnIndex,
    type: "assistant",
    content: msg.content ?? "",
    message_metadata: {
      type: "assistant_message",
      streamItems: msg.streamItems,
    },
    created_at: msg.createdAt ?? NOW,
  };
}

export interface ToolCallProgressOverrides {
  status?: string;
  rawOutput?: string;
  description?: string;
  command?: string;
  newContent?: string;
  oldContent?: string;
}

export function toolCallProgress(
  toolCallId: string,
  overrides: ToolCallProgressOverrides = {}
) {
  return {
    type: "tool_call_progress",
    toolCallId,
    toolName: "bash",
    kind: "execute",
    status: overrides.status ?? "running",
    isTodo: false,
    title: "Terminal",
    description: overrides.description ?? "",
    command: overrides.command ?? "mkdir -p outputs/hello",
    rawOutput: overrides.rawOutput ?? "",
    filePath: "",
    subagentType: null,
    skillName: null,
    isNewFile: false,
    oldContent: overrides.oldContent ?? "",
    newContent: overrides.newContent ?? "",
    todos: [],
    taskOutput: null,
    sessionId: null,
    parentSessionId: null,
    subagentSessionId: null,
  };
}

export function toolCallStart(
  toolCallId: string,
  command = "mkdir -p outputs"
) {
  return {
    type: "tool_call_start",
    toolCallId,
    toolName: "bash",
    kind: "execute",
    isTodo: false,
    title: "Terminal",
    description: "",
    command,
    skillName: null,
    subagentType: null,
    sessionId: null,
    parentSessionId: null,
    subagentSessionId: null,
  };
}

export function thinkingChunk(text: string) {
  return {
    type: "thinking_chunk",
    text,
    sessionId: null,
    parentSessionId: null,
  };
}

export function textChunk(text: string) {
  return { type: "text_chunk", text, sessionId: null, parentSessionId: null };
}

// ── Saved stream-item constructors (message_metadata.streamItems shape) ──

export interface SavedToolCallOverrides {
  kind?: string;
  toolName?: string;
  title?: string;
  description?: string;
  command?: string;
  status?: string;
  rawOutput?: string;
  filePath?: string;
  isNewFile?: boolean;
  oldContent?: string;
  newContent?: string;
}

export function savedToolCall(
  id: string,
  overrides: SavedToolCallOverrides = {}
) {
  return {
    type: "tool_call",
    id,
    toolCall: {
      id,
      kind: overrides.kind ?? "execute",
      toolName: overrides.toolName ?? "bash",
      title: overrides.title ?? "Terminal",
      description: overrides.description ?? "",
      command: overrides.command ?? "mkdir -p outputs/hello",
      status: overrides.status ?? "completed",
      rawOutput: overrides.rawOutput ?? "",
      filePath: overrides.filePath ?? "",
      isNewFile: overrides.isNewFile ?? false,
      oldContent: overrides.oldContent ?? "",
      newContent: overrides.newContent ?? "",
    },
  };
}

export function savedThinking(
  id: string,
  content: string,
  durationMs?: number
) {
  return {
    type: "thinking",
    id,
    content,
    isStreaming: false,
    ...(durationMs != null ? { durationMs } : {}),
  };
}

export function savedText(id: string, content: string) {
  return { type: "text", id, content, isStreaming: false };
}

/** Serializes packets into the SSE wire format the craft parser expects. */
export function sseBody(packets: unknown[]): string {
  return packets
    .map((packet) => `event: message\ndata: ${JSON.stringify(packet)}\n\n`)
    .join("");
}

export interface HeldTurn {
  /** Resolves the hung event stream with the given packets and settles. */
  release(packets: unknown[]): Promise<void>;
  /** Job launch prompts observed (one per createCraftJob call). */
  prompts: string[];
  /** POST /interrupt bodies observed so far. */
  interrupts: number[];
  /** POST /jobs/{id}/cancel observed so far. */
  cancels: number[];
  /** How many turns the mock has started. */
  turnsStarted(): number;
  /** Flip the job to failed and release the held stream (terminal packet). */
  fail(errorDetail?: string): Promise<void>;
}

function jobBody(
  sessionId: string,
  status: string,
  errorDetail: string | null = null
) {
  return {
    id: "00000000-0000-0000-0000-000000000abc",
    session_id: sessionId,
    project_id: null,
    scenario_id: null,
    name: "Spec job",
    domain: "general",
    status,
    error_detail: errorDetail,
    current_phase_index: 0,
    phases: [{ id: "execute", name: "Execute", kind: "work", status: status }],
    timeline: [
      { id: "execute", kind: "work", status: status, label: "Execute" },
    ],
    artifacts: [],
    events: [],
    interrupt: null,
    total_budget_seconds: 7200,
    phase_budget_seconds: 1500,
    specialists: [],
  };
}

/**
 * Holds a running turn open so the session stays busy. Both send paths are
 * mocked (plain POST send-message is the default; POST /jobs fires for the
 * deep-task switch), the jobs SWR poll mirrors the job status, and the
 * turn's SSE event stream is held open until `release()` fulfills it with
 * the scripted packets plus a final prompt_response.
 */
export async function holdTurnOpen(page: Page): Promise<HeldTurn> {
  const held: HeldTurn = {
    release: async () => {},
    fail: async () => {},
    prompts: [],
    interrupts: [],
    cancels: [],
    turnsStarted: () => held.prompts.length,
  };
  let released = false;
  let cancelled = false;
  let failedDetail: string | null = null;
  let releaseEvents: ((packets: unknown[]) => void) | null = null;
  const releasedPromise = new Promise<unknown[]>((resolve) => {
    releaseEvents = resolve;
  });

  await page.route("**/api/build/jobs**", async (route) => {
    const url = route.request().url();
    if (url.includes("/asks/current")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: "null",
      });
      return;
    }
    if (url.includes("/cancel")) {
      cancelled = true;
      held.cancels.push(1);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(jobBody(SESSION_ID, "cancelled")),
      });
      return;
    }
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON() as { prompt?: string };
      held.prompts.push(body.prompt ?? "");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          job: jobBody(SESSION_ID, "running"),
          turn_id: `turn-${held.prompts.length}`,
        }),
      });
      return;
    }
    await route.fulfill({
      // After release the SWR job poll must observe a settled job: SWR keeps
      // the last successful body on errors, so a 404 here would leave the UI
      // believing the job is still in flight. SWR interval polling does not
      // fire in headless runs, so specs drive revalidation through user
      // actions that call mutateCraftJob (interrupt/cancel/send).
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(
        jobBody(
          SESSION_ID,
          failedDetail !== null
            ? "failed"
            : cancelled
              ? "cancelled"
              : released
                ? "succeeded"
                : "running",
          failedDetail
        )
      ),
    });
  });
  await page.route("**/api/build/sessions/*/send-message", async (route) => {
    if (route.request().method() !== "POST") {
      await route.continue();
      return;
    }
    // Plain turns are the default send path; the deep-task switch (or a
    // start_long_job escalation) is what POSTs /jobs instead.
    const body = route.request().postDataJSON() as { content?: string };
    held.prompts.push(body.content ?? "");
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        turn_id: `turn-${held.prompts.length}`,
        session_id: SESSION_ID,
        status: "QUEUED",
        turn_index: held.prompts.length - 1,
      }),
    });
  });
  await page.route("**/api/build/sessions/**/interrupt", async (route) => {
    held.interrupts.push(1);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: "{}",
    });
  });
  await page.route(
    "**/api/build/sessions/**/turns/**/events",
    async (route) => {
      const packets = await releasedPromise;
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: sseBody([...packets, { type: "prompt_response" }]),
      });
    }
  );

  held.release = async (packets: unknown[]) => {
    released = true;
    releaseEvents?.(packets);
  };
  held.fail = async (errorDetail = "upstream LLM request failed") => {
    failedDetail = errorDetail;
    releaseEvents?.([{ type: "error", message: errorDetail }]);
  };
  return held;
}

export interface MockBackendOptions {
  messages?: unknown[];
  /** Fulfills the turn event stream immediately with these packets. */
  turnPackets?: unknown[];
  activeTurn?: string | null;
}

/**
 * Mocks the read surface of a craft session (session body, messages, sandbox
 * status, files, artifacts, active turn) plus a no-job jobs endpoint. Call
 * before navigating to /craft/v1?sessionId=...
 */
export async function mockCraftBackend(
  page: Page,
  options: MockBackendOptions = {}
): Promise<void> {
  const messages = options.messages ?? [];
  const { turnPackets, activeTurn = null } = options;

  await page.route("**/api/build/sessions/**", async (route: Route) => {
    const url = route.request().url();
    const method = route.request().method();
    if (url.includes("/messages") && method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ messages }),
      });
      return;
    }
    if (url.includes("/files") && method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ path: "outputs", entries: [] }),
      });
      return;
    }
    if (
      (url.includes("/artifacts") ||
        url.includes("/turns/active") ||
        url.includes("/webapp-info") ||
        url.includes("/approvals")) &&
      method === "GET"
    ) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: url.includes("/turns/active") ? "null" : "[]",
      });
      return;
    }
    if (url.includes("/sandbox-status") && method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "running",
          session_loaded_in_sandbox: true,
        }),
      });
      return;
    }
    if (url.includes("/jobs/asks/current") || url.includes("/asks/current")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: "null",
      });
      return;
    }
    const sessionRoot = url.match(/\/sessions\/[0-9a-f-]+(?:\?|$)/i);
    if (method === "GET" && sessionRoot) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(sessionBody()),
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
        body: "null",
      });
      return;
    }
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: "no job" }),
    });
  });
  // Real notifications from the shared dev backend steal focus with a toast
  // right as specs start typing; serve an empty feed instead.
  await page.route("**/api/notifications**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        notifications: [],
        total_pages: 0,
        total_notifications: 0,
      }),
    });
  });
  // The slash picker reads the skills catalog; serve a tiny fixture so the
  // popover is deterministic and fast regardless of backend load.
  await page.route(/\/api\/skills\/?(\?.*)?$/, async (route) => {
    const fixtureSkill = (name: string, description: string) => ({
      source: "builtin",
      id: name,
      name,
      description,
      is_available: true,
      unavailable_reason: null,
      is_valid: true,
      is_personal: false,
      enabled: true,
      can_toggle: false,
      author_user_id: null,
      author_email: null,
      owner: null,
    });
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        builtins: [
          fixtureSkill("alpha-skill", "Alpha fixture skill for e2e specs."),
          fixtureSkill("beta-skill", "Beta fixture skill for e2e specs."),
        ],
        customs: [],
      }),
    });
  });
  // CraftComposer gates the picker on these companion catalogs too; stub both
  // empty so popover readiness never depends on live backend latency.
  await page.route("**/api/mcp/servers/craft", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ mcp_servers: [] }),
    });
  });
  await page.route("**/api/build/user-library/tree", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });

  if (turnPackets) {
    const body = sseBody([...turnPackets, { type: "prompt_response" }]);
    await page.route(
      "**/api/build/sessions/**/turns/**/events",
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "text/event-stream",
          body,
        });
      }
    );
  }
  if (activeTurn) {
    void activeTurn;
  }
}

/** Seeds prompt history for the craft surface before page scripts run. */
export async function seedPromptHistory(
  page: Page,
  entries: string[]
): Promise<void> {
  const me = await page.request.get("/api/me");
  if (!me.ok()) return;
  const body = (await me.json()) as { id?: string };
  if (!body.id) return;
  await page.addInitScript(
    ({ userId, items }: { userId: string; items: string[] }) => {
      window.localStorage.setItem(
        `onyx-prompt-history:craft:${userId}`,
        JSON.stringify(items)
      );
    },
    { userId: body.id, items: entries }
  );
}

/** Suppresses the first-visit craft intro tour. */
export async function suppressCraftIntro(page: Page): Promise<void> {
  const me = await page.request.get("/api/me");
  if (!me.ok()) return;
  const body = (await me.json()) as { id?: string };
  if (!body.id) return;
  await page.addInitScript((userId: string) => {
    window.localStorage.setItem(`onyx:craftOnboardingSeen:${userId}`, "true");
  }, body.id);
}
