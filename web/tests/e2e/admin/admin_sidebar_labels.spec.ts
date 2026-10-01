import { test, expect } from "@playwright/test";
import { ADMIN_ROUTES } from "@/lib/admin-routes";

test.use({ storageState: "admin_auth.json" });

/**
 * Every admin sidebar link must carry a visible text label. A regression
 * once left four admin entries icon-only because their i18n keys lived in
 * an unconsumed namespace — this spec pins the label wiring end-to-end.
 */
test("admin sidebar entries all carry text labels", async ({ page }) => {
  await page.goto(ADMIN_ROUTES.LLM_MODELS.path);
  await page.waitForLoadState("networkidle");

  const links = page.locator(".opal-sidebar-root__column a[href^='/admin/']");
  const count = await links.count();
  expect(count).toBeGreaterThan(0);

  for (let i = 0; i < count; i++) {
    const label = (await links.nth(i).textContent())?.trim() ?? "";
    expect(label, `sidebar link #${i} has no text label`).not.toBe("");
  }
});

test("the four fork-added admin pages show their labels", async ({ page }) => {
  await page.goto(ADMIN_ROUTES.LLM_MODELS.path);
  await page.waitForLoadState("networkidle");

  const sidebar = page.locator(".opal-sidebar-root__column");

  const expected: [string, string][] = [
    [ADMIN_ROUTES.AGENT_MODELS.path, "Agent Models"],
    [ADMIN_ROUTES.AUDIT.path, "Audit Report"],
    [ADMIN_ROUTES.TOKEN_RATE_LIMITS.path, "Token Rate Limits"],
    [ADMIN_ROUTES.STANDARD_ANSWERS.path, "Standard Answers"],
  ];

  for (const [path, label] of expected) {
    await expect(
      sidebar.locator(`a[href='${path}']`),
      `${path} sidebar entry`
    ).toContainText(label);
  }
});
