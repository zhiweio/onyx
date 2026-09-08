/**
 * Page Object Model for the craft welcome page (/craft/v1) and its provider
 * onboarding surfaces: the first-visit intro modal, the inline LLM-provider
 * setup card shown to admins without a build-mode provider, and the locked
 * notice shown to non-admins. Encapsulates every locator these flows need so
 * specs stay declarative.
 */

import { type Page, type Locator, expect } from "@playwright/test";

export class CraftWelcomePage {
  readonly page: Page;
  readonly introHeading: Locator;
  readonly llmSetup: Locator;
  readonly llmSetupToggle: Locator;
  readonly lockedState: Locator;
  readonly messageInput: Locator;
  readonly providerModal: Locator;
  readonly longJobToggle: Locator;
  readonly jobBanner: Locator;
  readonly jobAskBar: Locator;
  readonly jobAskApprove: Locator;
  readonly jobAskReject: Locator;

  constructor(page: Page) {
    this.page = page;
    // Fixed title of the Living Map intro tour.
    this.introHeading = page.getByText("Meet Craft", { exact: true });
    this.llmSetup = page.locator('[aria-label="craft-llm-setup"]');
    this.llmSetupToggle = this.llmSetup.getByRole("switch");
    this.lockedState = page.locator('[aria-label="craft-llm-locked"]');
    this.messageInput = page.getByRole("textbox");
    this.providerModal = page.getByRole("dialog");
    this.longJobToggle = page.getByTestId("craft-long-job-toggle");
    this.jobBanner = page.getByTestId("craft-job-banner");
    this.jobAskBar = page.getByTestId("craft-ask-bar");
    this.jobAskApprove = page.getByTestId("craft-ask-approve");
    this.jobAskReject = page.getByTestId("craft-ask-reject");
  }

  async goto(): Promise<void> {
    await this.page.goto("/craft/v1");
  }

  /** Open a blank welcome so the first prompt can start a long job. */
  async startNewSession(): Promise<void> {
    await this.page
      .getByRole("button", { name: /Start Crafting|开始创作/ })
      .click();
    await this.page.waitForURL((url) => !url.searchParams.has("sessionId"), {
      timeout: 15000,
    });
  }

  /** Dismisses the first-visit intro tour (Escape closes the dialog). */
  async dismissIntro(): Promise<void> {
    await expect(this.introHeading).toBeVisible({ timeout: 15000 });
    await this.page.keyboard.press("Escape");
    await expect(this.introHeading).not.toBeVisible();
  }

  providerCard(name: string): Locator {
    return this.llmSetup.getByText(name, { exact: true });
  }

  /** Flips the "Recommended providers only" switch on the setup card. */
  async toggleRecommendedOnly(): Promise<void> {
    await this.llmSetupToggle.click();
  }

  async openProviderSetup(name: string): Promise<void> {
    await this.providerCard(name).click();
    await expect(this.providerModal.getByText(`Set up ${name}`)).toBeVisible({
      timeout: 10000,
    });
  }

  async expectInputDisabled(): Promise<void> {
    await expect(this.messageInput).toHaveAttribute("aria-disabled", "true");
  }

  async expectInputEnabled(): Promise<void> {
    await expect(this.messageInput).toBeVisible({ timeout: 15000 });
    await expect(this.messageInput).toHaveAttribute("aria-disabled", "false");
  }

  async enableLongJob(): Promise<void> {
    await expect(this.longJobToggle).toBeVisible({ timeout: 15000 });
    await this.longJobToggle.click();
  }

  async submitMessage(text: string): Promise<void> {
    await this.expectInputEnabled();
    await this.messageInput.click();
    await this.messageInput.pressSequentially(text);
    await this.page.getByRole("button", { name: /Send|发送/ }).click();
  }
}
