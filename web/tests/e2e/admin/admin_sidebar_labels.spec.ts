import { test, expect, type Locator } from "@playwright/test";
import { ADMIN_ROUTES } from "@/lib/admin-routes";

test.use({ storageState: "admin_auth.json" });

/**
 * Every admin sidebar entry must carry a visible label — as link text when
 * the sidebar is expanded, or as the overlay link's accessible name when it
 * is collapsed to icons (the sidebarIsToggled cookie persists that state).
 * A regression once left four admin entries icon-only with no name at all
 * because their i18n keys lived in an unconsumed namespace; this spec pins
 * the label wiring end-to-end.
 */
async function entryLabel(link: Locator): Promise<string> {
  const text = (await link.textContent())?.trim() ?? "";
  if (text) return text;
  return (await link.getAttribute("aria-label"))?.trim() ?? "";
}

test("admin sidebar entries all carry labels", async ({ page }) => {
  await page.goto(ADMIN_ROUTES.LLM_MODELS.path);
  await page.waitForLoadState("networkidle");

  const links = page.locator(".opal-sidebar-root__column a[href^='/admin/']");
  const count = await links.count();
  expect(count).toBeGreaterThan(0);

  // A cold dev server hydrates the sidebar after networkidle.
  await expect.poll(async () => await entryLabel(links.first())).not.toBe("");

  for (let i = 0; i < count; i++) {
    const label = await entryLabel(links.nth(i));
    expect(label, `sidebar link #${i} has no label`).not.toBe("");
  }
});

test("the fork-added admin pages show their labels", async ({ page }) => {
  await page.goto(ADMIN_ROUTES.LLM_MODELS.path);
  await page.waitForLoadState("networkidle");

  const sidebar = page.locator(".opal-sidebar-root__column");

  // Language-agnostic on purpose: the admin's interface language decides the
  // exact label (the i18n parity tests pin those per locale); here only the
  // entry and its non-empty label matter.
  const paths = [
    ADMIN_ROUTES.AUDIT.path,
    ADMIN_ROUTES.TOKEN_RATE_LIMITS.path,
    ADMIN_ROUTES.STANDARD_ANSWERS.path,
    ADMIN_ROUTES.IM_BOTS.path,
  ];

  for (const path of paths) {
    const entry = sidebar.locator(`a[href='${path}']`);
    await expect.poll(async () => await entryLabel(entry)).not.toBe("");
  }
});

test("agent-models merged into the language models page", async ({ page }) => {
  await page.goto("/admin/agent-models");
  await page.waitForLoadState("networkidle");

  // Redirected onto the merged page with the overlay tab selected.
  await expect(page).toHaveURL(/\/admin\/language-models\?tab=agent-models/);
  await expect(page.getByTestId("agent-models-page")).toBeVisible();
});
