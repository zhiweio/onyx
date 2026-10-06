/**
 * Craft tapes browser (dsh-style master-detail): personal list rows with
 * status dots, ?sessionId= deep-link sync and reload survival, the
 * trajectory ledger with delta-run collapsing, replay loading only when its
 * tab opens, debounced search, and the admin stats strip + chart + browser.
 * Mocking style mirrors craftSessionMock: black-box UI assertions over
 * intercepted tape APIs.
 */

import { expect, test, type Page, type Route } from "@playwright/test";
import { suppressCraftIntro } from "@tests/e2e/craft/helpers/craftSessionMock";

const RUNNING_ID = "00000000-0000-0000-0000-00000000a001";
const DONE_ID = "00000000-0000-0000-0000-00000000a002";
const ERROR_ID = "00000000-0000-0000-0000-00000000a003";

function hoursAgo(hours: number): string {
  return new Date(Date.now() - hours * 3_600_000).toISOString();
}

function session(id: string, name: string, lastReason: string | null) {
  return {
    session_id: id,
    name,
    user_id: "user-1",
    user_email: "user@example.com",
    origin: "interactive",
    created_at: hoursAgo(2),
    turns: 1,
    events: 7,
    hot_events: lastReason === null ? 3 : 0,
    archived: false,
    input_tokens: 100,
    output_tokens: 120,
    cost: 0.01,
    last_activity: hoursAgo(1),
    last_reason: lastReason,
    runtimes: ["opencode"],
  };
}

const SESSIONS = [
  session(RUNNING_ID, "Running import task", null),
  session(DONE_ID, "Done import task", "completed"),
  session(ERROR_ID, "Broken export task", "error"),
];

const TURNS = {
  items: [
    {
      turn_index: 0,
      runtime: "opencode",
      started_at: hoursAgo(1),
      ended_at: hoursAgo(0.9),
      event_count: 7,
      input_tokens: 100,
      output_tokens: 120,
      cost: 0.01,
      turn_end_reason: "completed",
      error_detail: null,
      model: "gpt-4.1",
      tier: "hot",
    },
  ],
  total: 1,
};

function deltaEvent(sourceId: number, text: string) {
  return {
    source_id: sourceId,
    turn_index: 0,
    kind: "harness_message",
    subtype: "message.part.delta",
    runtime: "opencode",
    payload: {
      id: `evt-${sourceId}`,
      type: "message.part.delta",
      properties: { delta: text, field: "text", partID: "prt-1" },
    },
    created_at: hoursAgo(0.98),
    annotations: [],
  };
}

const EVENTS = {
  items: [
    {
      source_id: 1,
      turn_index: 0,
      kind: "context_event",
      subtype: "turn/start",
      runtime: "opencode",
      payload: { runtime: "opencode", turn_index: 0 },
      created_at: hoursAgo(1),
      annotations: [],
    },
    {
      source_id: 2,
      turn_index: 0,
      kind: "harness_message",
      subtype: "message.part.updated",
      runtime: "opencode",
      payload: {
        id: "evt-2",
        type: "message.part.updated",
        properties: {
          part: { id: "prt-2", type: "text", text: "Starting the import." },
        },
      },
      created_at: hoursAgo(0.99),
      annotations: [],
    },
    deltaEvent(3, "delta "),
    deltaEvent(4, "chunk "),
    deltaEvent(5, "run"),
    {
      source_id: 6,
      turn_index: 0,
      kind: "harness_message",
      subtype: "message.part.updated",
      runtime: "opencode",
      payload: {
        id: "evt-6",
        type: "message.part.updated",
        properties: {
          part: {
            id: "prt-6",
            type: "tool",
            tool: "bash",
            state: { input: { command: "python import.py" } },
          },
        },
      },
      created_at: hoursAgo(0.95),
      annotations: [],
    },
    {
      source_id: 7,
      turn_index: 0,
      kind: "context_event",
      subtype: "turn/end",
      runtime: "opencode",
      payload: { reason: "completed", runtime: "opencode", turn_index: 0 },
      created_at: hoursAgo(0.9),
      annotations: [],
    },
  ],
  next_source_id: null,
};

const REPLAY = { items: [], next_source_id: null, skipped: 0 };

const STATS = {
  sessions: 3,
  turns: 3,
  events: 21,
  input_tokens: 300,
  output_tokens: 360,
  cost: 0.03,
  by_reason: { completed: 2, error: 1 },
  by_runtime: { opencode: 3 },
  archiving_enabled: true,
  hot_retention_days: 7,
  lake_retention_days: 365,
};

const SERIES = {
  series: [
    { day: "2026-01-01", sessions: 1, turns: 1, events: 7 },
    { day: "2026-01-02", sessions: 2, turns: 2, events: 14 },
  ],
};

async function fulfillJson(route: Route, body: unknown): Promise<void> {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

/** One handler for a tape API base; records list queries and replay calls. */
function tapeApiHandler(
  page: Page,
  base: RegExp,
  counters: { listQueries: string[]; replayCalls: number }
): void {
  void page.route(base, async (route: Route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path.endsWith("/tape/sessions")) {
      counters.listQueries.push(url.searchParams.get("q") ?? "");
      await fulfillJson(route, { items: SESSIONS, total: SESSIONS.length });
      return;
    }
    if (path.endsWith("/turns")) {
      await fulfillJson(route, TURNS);
      return;
    }
    if (path.endsWith("/events")) {
      await fulfillJson(route, EVENTS);
      return;
    }
    if (path.endsWith("/replay")) {
      counters.replayCalls += 1;
      await fulfillJson(route, REPLAY);
      return;
    }
    if (path.endsWith("/stats")) {
      await fulfillJson(route, STATS);
      return;
    }
    if (path.endsWith("/stats/series")) {
      await fulfillJson(route, SERIES);
      return;
    }
    await fulfillJson(route, {});
  });
}

test.beforeEach(async ({ page }) => {
  await suppressCraftIntro(page);
});

test.describe("craft tapes browser", () => {
  test("personal: status rows, deep link, trajectory, lazy replay", async ({
    page,
  }) => {
    const counters = { listQueries: [] as string[], replayCalls: 0 };
    tapeApiHandler(page, /\/api\/build\/tape\//, counters);

    await page.goto("/craft/v1/tapes");
    await expect(page.getByTestId("my-craft-tapes-page")).toBeVisible();

    // Rows render with dsh-style status dots: spinner for the running
    // session, green for the completed one.
    const runningRow = page.getByTestId(`tape-row-${RUNNING_ID}`);
    await expect(runningRow).toBeVisible();
    await expect(
      runningRow.locator('[data-testid="tape-status-running"]')
    ).toHaveCount(1);
    const doneRow = page.getByTestId(`tape-row-${DONE_ID}`);
    await expect(
      doneRow.locator('[data-testid="tape-status-done"]')
    ).toHaveCount(1);

    // Nothing selected yet: the empty detail placeholder shows.
    await expect(page.getByTestId("tape-no-selection")).toBeVisible();
    expect(counters.replayCalls).toBe(0);

    // Selecting a session syncs ?sessionId= and opens the detail with the
    // trajectory view as default.
    await doneRow.click();
    await expect(page).toHaveURL(new RegExp(`sessionId=${DONE_ID}`));
    await expect(page.getByTestId("craft-tape-detail")).toBeVisible();
    await expect(page.getByTestId("tape-trajectory-turn-0")).toBeVisible();
    await expect(page.getByTestId("craft-tape-event-2")).toBeVisible();
    // Consecutive delta chunks collapse into one run row.
    await expect(page.getByTestId("craft-tape-delta-run-3")).toContainText(
      /3 (delta chunks|个增量块)/
    );
    // The turn rail lists the recorded turn.
    await expect(page.getByTestId("tape-rail-turn-0")).toBeVisible();

    // Replay drains only when its tab opens (StrictMode dev runs mount the
    // player twice, hence >= 1 rather than exactly 1).
    expect(counters.replayCalls).toBe(0);
    await page.getByTestId("tape-tab-replay").click();
    await expect.poll(() => counters.replayCalls).toBeGreaterThanOrEqual(1);

    // Reload keeps the selection through the URL param.
    await page.reload();
    await expect(page.getByTestId("craft-tape-detail")).toBeVisible();

    // The view-options popover opens and lists the grouping controls
    // (regression: a trigger that dropped Radix's Slot props stayed dead).
    await page.getByTestId("tape-view-options").click();
    const menu = page.getByTestId("tape-view-options-menu");
    await expect(menu).toBeVisible();
    await expect(menu).toContainText(/Group by|分组方式/);
    await page.keyboard.press("Escape");
  });

  test("personal: debounced search reaches the sessions endpoint", async ({
    page,
  }) => {
    const counters = { listQueries: [] as string[], replayCalls: 0 };
    tapeApiHandler(page, /\/api\/build\/tape\//, counters);

    await page.goto("/craft/v1/tapes");
    await expect(page.getByTestId("tape-list")).toBeVisible();

    await page.getByTestId("tape-search-toggle").click();
    await page.getByTestId("tape-search-input").fill("import");
    await expect
      .poll(() => counters.listQueries.some((q) => q.includes("import")))
      .toBe(true);
  });

  test("admin: stats strip, daily chart, browser with user subline", async ({
    page,
  }) => {
    const counters = { listQueries: [] as string[], replayCalls: 0 };
    tapeApiHandler(page, /\/api\/build\/admin\/tape\//, counters);

    await page.goto("/admin/craft/tapes");
    await expect(page.getByTestId("craft-tape-page")).toBeVisible();

    // Stats overview: window selector, tiles, and the daily series chart.
    await expect(page.getByTestId("craft-tape-window-7")).toBeVisible();
    await expect(page.getByTestId("craft-tape-series-chart")).toBeVisible();

    // The admin browser shows the user subline on rows.
    const errorRow = page.getByTestId(`tape-row-${ERROR_ID}`);
    await expect(errorRow).toBeVisible();
    await expect(errorRow).toContainText("user@example.com");

    await errorRow.click();
    await expect(page).toHaveURL(new RegExp(`sessionId=${ERROR_ID}`));
    await expect(page.getByTestId("craft-tape-detail")).toBeVisible();
    await expect(page.getByTestId("tape-trajectory-turn-0")).toBeVisible();
  });
});
