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
  let posted: { start?: boolean; prompt?: string } | null = null;
  await page.route("**/api/build/jobs", async (route) => {
    if (route.request().method() !== "POST") {
      await route.continue();
      return;
    }
    posted = route.request().postDataJSON() as {
      start?: boolean;
      prompt?: string;
    };
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

  await expect.poll(() => posted?.start).toBe(true);
  expect(posted?.prompt).toContain("long job fixture");
});
