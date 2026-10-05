/**
 * Approval cards in the craft dock: the tool-approval card (approve once /
 * approve for session / reject) and the content-quarantine card (scope
 * selector + approve/deny). The /live endpoint is mocked with pending items
 * — E3 coverage the real-agent rounds could not deterministically trigger.
 */

import { expect, test, type Page } from "@playwright/test";
import { CraftSessionPage } from "@tests/e2e/craft/helpers/CraftSessionPage";
import {
  SESSION_ID,
  mockCraftBackend,
  suppressCraftIntro,
} from "@tests/e2e/craft/helpers/craftSessionMock";

test.beforeEach(async ({ page }) => {
  await suppressCraftIntro(page);
  await mockCraftBackend(page);
});

interface PendingApprovals {
  withApproval?: boolean;
  withQuarantine?: boolean;
}

/** Overrides the empty /approvals live response with pending items. */
async function mockPendingApprovals(
  page: Page,
  opts: PendingApprovals
): Promise<void> {
  const now = new Date().toISOString();
  await page.route("**/api/build/approvals/sessions/*/live", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: opts.withApproval
          ? [
              {
                approval_id: "appr-1",
                session_id: SESSION_ID,
                actions: [
                  {
                    action_type: "web_search",
                    display_name: "Web Search",
                    description: "Search the web",
                    policy: "ASK",
                  },
                ],
                app_name: "Parallel Search",
                payload: { query: "雪龙集团 年报" },
                display_payload: { query: "雪龙集团 年报" },
                created_at: now,
                decision: null,
                decided_at: null,
                is_live: true,
              },
            ]
          : [],
        content_quarantines: opts.withQuarantine
          ? [
              {
                quarantine_id: "qtn-1",
                session_id: SESSION_ID,
                url_host: "static.example.com",
                url_path: "/files/report.xlsx",
                patterns_matched: ["*.xlsx"],
                evidence_excerpt: "binary spreadsheet upload",
                created_at: now,
              },
            ]
          : [],
      }),
    });
  });
}

test("pending tool approval renders; approve once posts the decision", async ({
  page,
}) => {
  await mockPendingApprovals(page, { withApproval: true });
  const session = new CraftSessionPage(page);
  await session.goto(SESSION_ID);

  const region = page.getByTestId("live-approvals-region");
  await expect(region).toBeVisible({ timeout: 15000 });
  await expect(region).toContainText("Parallel Search");

  const decisions: Record<string, unknown>[] = [];
  await page.route("**/api/build/approvals/appr-1/decision", async (route) => {
    decisions.push(route.request().postDataJSON() as Record<string, unknown>);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ approval_id: "appr-1", decision: "APPROVED" }),
    });
  });

  await region
    .getByRole("button", {
      name: /仅批准此操作一次|Approve this action once|批准一次|Approve once/,
    })
    .click();
  await expect.poll(() => decisions.length).toBe(1);
  expect(decisions[0]).toEqual({ decision: "APPROVED" });
});

test("approve for session posts the session grant", async ({ page }) => {
  await mockPendingApprovals(page, { withApproval: true });
  const session = new CraftSessionPage(page);
  await session.goto(SESSION_ID);

  const region = page.getByTestId("live-approvals-region");
  await expect(region).toBeVisible({ timeout: 15000 });

  const grants: number[] = [];
  await page.route(
    "**/api/build/approvals/appr-1/session-grant",
    async (route) => {
      grants.push(1);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ approval_id: "appr-1", decision: "APPROVED" }),
      });
    }
  );

  await region
    .getByRole("button", {
      name: /批准此会话中的匹配操作|Approve matching actions for this session|批准整个会话|Approve for session/,
    })
    .click();
  await expect.poll(() => grants.length).toBe(1);
});

test("quarantine card: host scope + approve posts scoped release", async ({
  page,
}) => {
  await mockPendingApprovals(page, { withQuarantine: true });
  const session = new CraftSessionPage(page);
  await session.goto(SESSION_ID);

  const region = page.getByTestId("live-approvals-region");
  await expect(region).toBeVisible({ timeout: 15000 });
  await expect(region).toContainText("static.example.com");

  // Switch the release scope to HOST (the third scope pill).
  await region
    .getByRole("button", { name: /全部会话（30 天）|30 days/i })
    .click();

  const releases: Record<string, unknown>[] = [];
  await page.route(
    "**/api/build/approvals/content-quarantines/qtn-1/decision",
    async (route) => {
      releases.push(route.request().postDataJSON() as Record<string, unknown>);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ quarantine_id: "qtn-1" }),
      });
    }
  );

  // The approve action button is labeled "Allow/放行（<scope>）".
  await region.getByRole("button", { name: /放行|Allow/ }).click();
  await expect.poll(() => releases.length).toBe(1);
  expect(releases[0]).toEqual({ decision: "APPROVED", scope: "HOST" });
});
