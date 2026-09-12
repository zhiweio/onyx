import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

/**
 * The gallery is admin-curated content that users browse read-only and fork.
 * These cover the user-facing half: the tab split, that published catalog
 * content is listed, and that forking lands an editable copy under "Mine".
 *
 * Elements are addressed by test id rather than label, so the suite does not
 * depend on the deployment's UI locale.
 */

const MINE_TAB = "GalleryTabs/mine";
const GALLERY_TAB = "GalleryTabs/gallery";
const GRID = "GalleryGrid/container";

async function suppressCraftIntro(page: Page): Promise<void> {
  const me = await page.request.get("/api/me");
  if (!me.ok()) return;
  const body = (await me.json()) as { id?: string };
  if (!body.id) return;
  // Set before navigation so the intro never opens and intercepts clicks.
  await page.addInitScript((userId: string) => {
    window.localStorage.setItem(`onyx:craftOnboardingSeen:${userId}`, "true");
  }, body.id);
}

async function dismissAnyModal(page: Page): Promise<void> {
  const dialog = page.getByRole("dialog");
  const appeared = await dialog
    .first()
    .isVisible({ timeout: 2000 })
    .catch(() => false);
  if (!appeared) return;
  for (let attempt = 0; attempt < 5; attempt += 1) {
    const visible = await dialog
      .first()
      .isVisible()
      .catch(() => false);
    if (!visible) return;
    const close = dialog.first().getByRole("button", { name: /close/i });
    if (await close.isVisible().catch(() => false)) {
      await close.click({ force: true });
    } else {
      await page.keyboard.press("Escape");
    }
    await page.waitForTimeout(300);
  }
}

async function openGallery(page: Page, path: string): Promise<void> {
  await page.goto(path);
  await dismissAnyModal(page);

  // Opens on the user's own library, so the page starts where they work.
  await expect(page.getByTestId(MINE_TAB)).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await page.getByTestId(GALLERY_TAB).click();
  await expect(page.getByTestId(GRID)).toBeVisible();
}

test.beforeEach(async ({ page }) => {
  const response = await page.request.get("/api/settings");
  const settings = response.ok() ? await response.json() : null;
  test.skip(
    settings?.onyx_craft_enabled !== true,
    "Onyx Craft is disabled in this environment",
  );
  await suppressCraftIntro(page);
});

test("the skills gallery shows what the API publishes", async ({ page }) => {
  await openGallery(page, "/craft/v1/skills");

  const response = await page.request.get("/api/craft/gallery/skills");
  const items = (await response.json()).items as { name: string }[];
  expect(items.length).toBeGreaterThan(0);

  await expect(
    page.getByTestId(GRID).getByText(items[0].name, { exact: false }).first(),
  ).toBeVisible();
  await expect(
    page.getByTestId(GRID).getByTestId("GalleryCard/fork").first(),
  ).toBeVisible();
});

test("the scenario and report-template galleries also list content", async ({
  page,
}) => {
  for (const [path, endpoint] of [
    ["/craft/v1/scenarios", "/api/craft/gallery/scenarios"],
    ["/craft/v1/report-templates", "/api/craft/gallery/report-templates"],
  ]) {
    await openGallery(page, path);
    const response = await page.request.get(endpoint);
    expect((await response.json()).items.length).toBeGreaterThan(0);
    await expect(
      page.getByTestId(GRID).getByTestId("GalleryCard/fork").first(),
    ).toBeVisible();
  }
});

test("forking a report template creates an editable copy", async ({ page }) => {
  await openGallery(page, "/craft/v1/report-templates");

  const before = await page.request.get("/api/report-templates");
  const beforeCount = (await before.json()).templates.length;

  await page.getByTestId(GRID).getByTestId("GalleryCard/fork").first().click();

  // A fresh copy belongs to the user, so the page returns to their library.
  await expect(page.getByTestId(MINE_TAB)).toHaveAttribute(
    "aria-selected",
    "true",
    { timeout: 20000 },
  );

  await expect
    .poll(
      async () => {
        const after = await page.request.get("/api/report-templates");
        return (await after.json()).templates.length;
      },
      { timeout: 20000 },
    )
    .toBeGreaterThan(beforeCount);

  // Clean up so the suite stays re-runnable against a shared deployment.
  const after = await page.request.get("/api/report-templates");
  const forked = (await after.json()).templates.find(
    (template: { slug: string; author_user_id: string | null }) =>
      template.slug.endsWith("_copy") && template.author_user_id !== null,
  );
  if (forked) {
    await page.request.delete(`/api/report-templates/${forked.id}`);
  }
});

test("uploading a Word template attaches the file for the agent", async ({
  page,
}) => {
  const created = await page.request.post("/api/report-templates", {
    data: {
      name: "E2E Word template",
      slug: `e2e_word_${Date.now()}`,
      description: "Playwright upload",
      body: "# Outline\n",
    },
  });
  expect(created.ok()).toBeTruthy();
  const template = (await created.json()) as { id: string; slug: string };

  try {
    const fixture = path.join(
      process.cwd(),
      "tests/e2e/craft/fixtures/placeholder.docx",
    );
    await page.goto(`/craft/v1/report-templates/edit/${template.id}`);
    await dismissAnyModal(page);

    await page.getByTestId("DocxTemplateSection/input").setInputFiles(fixture);
    // Poll the API so the assertion does not depend on the UI locale.
    await expect
      .poll(
        async () => {
          const after = await page.request.get(
            `/api/report-templates/${template.id}`,
          );
          const body = (await after.json()) as { kind?: string };
          return body.kind;
        },
        { timeout: 20000 },
      )
      .toBe("DOCX");

    const download = await page.request.get(
      `/api/report-templates/${template.id}/docx`,
    );
    expect(download.ok()).toBeTruthy();
    expect(download.headers()["content-type"]).toContain(
      "wordprocessingml.document",
    );
    const bytes = await download.body();
    expect(bytes.byteLength).toBeGreaterThan(100);
  } finally {
    await page.request.delete(`/api/report-templates/${template.id}`);
  }
});
