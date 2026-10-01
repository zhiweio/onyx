/**
 * Page Object Model for the Onyx Craft Loops surface
 * (/craft/v1/loops, /craft/v1/loops/[id]).
 */

import { type Page, type Locator, expect } from "@playwright/test";

const LOOPS_LIST_PATH = "/craft/v1/loops";
const API_BASE = "/api/build/loops";

export interface LoopApiShape {
  id: string;
  name: string;
  state: string;
  health: string;
  ship_actions: { action: string; gate: string }[];
  counts: Record<string, number>;
}

export class LoopsPage {
  readonly page: Page;

  readonly autopilotSwitch: Locator;
  readonly toggleStateButton: Locator;
  readonly deleteButton: Locator;
  readonly openGrantModalButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.autopilotSwitch = page.getByTestId("loop-autopilot-switch");
    this.toggleStateButton = page.getByTestId("loop-toggle-state");
    this.deleteButton = page.getByTestId("loop-delete");
    this.openGrantModalButton = page.getByTestId("open-grant-modal");
  }

  async gotoList(): Promise<void> {
    await this.page.goto(LOOPS_LIST_PATH);
    await this.page.waitForLoadState("networkidle");
    await this.dismissCraftIntro();
  }

  /** Same first-visit intro guard as the scheduled-tasks POM. */
  private async dismissCraftIntro(): Promise<void> {
    const intro = this.page
      .getByRole("dialog")
      .filter({ hasText: "Meet Craft" });
    const appeared = await intro
      .waitFor({ state: "visible", timeout: 3000 })
      .then(() => true)
      .catch(() => false);
    if (appeared) {
      await this.page.keyboard.press("Escape");
      await expect(intro).toBeHidden();
    }
  }

  isCraftEnabled(): boolean {
    return new URL(this.page.url()).pathname.startsWith(LOOPS_LIST_PATH);
  }

  // ---------------------------------------------------------------------------
  // API helpers (seed data through the same session cookies)
  // ---------------------------------------------------------------------------

  async createLoopViaApi(name: string): Promise<LoopApiShape> {
    const res = await this.page.request.post(API_BASE, {
      data: {
        name,
        description: "e2e loop",
        playbook: { prompt: "say hi" },
        ship_actions: [{ action: "im_push", gate: "hold" }],
        trigger_cron: null,
      },
    });
    expect(res.ok()).toBeTruthy();
    return (await res.json()) as LoopApiShape;
  }

  async seedItemViaApi(loopId: string, sourceKey: string): Promise<void> {
    const res = await this.page.request.post(`${API_BASE}/${loopId}/items`, {
      data: { items: [{ source_key: sourceKey, source_summary: "e2e item" }] },
    });
    expect(res.ok()).toBeTruthy();
  }

  async deleteLoopViaApi(loopId: string): Promise<void> {
    await this.page.request.delete(`${API_BASE}/${loopId}`);
  }

  // ---------------------------------------------------------------------------
  // Assertions
  // ---------------------------------------------------------------------------

  async expectLoopRow(name: string): Promise<Locator> {
    const row = this.page.getByRole("row").filter({ hasText: name });
    await expect(row).toBeVisible();
    return row;
  }

  async expectNoLoopRow(name: string): Promise<void> {
    const row = this.page.getByRole("row").filter({ hasText: name });
    await expect(row).toHaveCount(0);
  }

  async openLoop(name: string): Promise<void> {
    const row = this.page.getByRole("row").filter({ hasText: name });
    await row.click();
    await this.page.waitForLoadState("networkidle");
  }

  async expectStateBadge(state: string): Promise<void> {
    await expect(
      this.page.getByTestId(`loop-state-${state}`).first()
    ).toBeVisible();
  }

  async expectLedgerRow(sourceKey: string): Promise<void> {
    await expect(
      this.page.getByRole("row").filter({ hasText: sourceKey })
    ).toBeVisible();
  }
}
