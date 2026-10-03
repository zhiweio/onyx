/**
 * Page object for the craft session view composer and its surroundings: the
 * shared-kernel message input, the send/stop/queue primary action, the queue
 * panel, and the timeline landmarks the specs assert on.
 */

import { type Locator, type Page, expect } from "@playwright/test";

export class CraftSessionPage {
  readonly page: Page;
  readonly messageInput: Locator;
  readonly primaryAction: Locator;
  readonly queuePanel: Locator;
  readonly queueRows: Locator;
  readonly turnStatus: Locator;
  readonly agentCopyButton: Locator;
  readonly userEditButton: Locator;
  readonly retryButton: Locator;
  readonly deepTaskToggle: Locator;

  constructor(page: Page) {
    this.page = page;
    this.messageInput = page.getByTestId("craft-message-input");
    this.primaryAction = page.getByTestId("composer-primary-action");
    this.queuePanel = page.getByTestId("craft-queue-panel");
    this.queueRows = page.getByTestId("craft-queue-row");
    this.turnStatus = page.getByTestId("craft-turn-status");
    this.agentCopyButton = page.getByTestId("CraftAgentMessage/copy-button");
    this.userEditButton = page.getByTestId("CraftUserMessage/edit-button");
    this.retryButton = page.getByTestId("CraftAgentMessage/retry-button");
    this.deepTaskToggle = page.getByTestId("craft-deep-task-toggle");
  }

  /** Flip the deep-task switch so the next send launches a long job. */
  async enableDeepTask(): Promise<void> {
    await this.deepTaskToggle.click();
    await expect(this.deepTaskToggle).toHaveAttribute("aria-pressed", "true");
  }

  async goto(sessionId: string): Promise<void> {
    await this.page.goto(`/craft/v1?sessionId=${sessionId}`);
    await this.expectInputEnabled();
  }

  async expectInputEnabled(): Promise<void> {
    await expect(this.messageInput).toBeVisible({ timeout: 15000 });
    await expect(this.messageInput).toBeEnabled({ timeout: 15000 });
  }

  async typeMessage(text: string): Promise<void> {
    await this.messageInput.click();
    await this.messageInput.pressSequentially(text);
  }

  async pressEnter(): Promise<void> {
    await this.messageInput.press("Enter");
  }

  queueRow(text: string): Locator {
    return this.page.getByTestId("craft-queue-row").filter({ hasText: text });
  }

  async expectPrimaryAction(named: RegExp): Promise<void> {
    await expect(this.primaryAction).toHaveAccessibleName(named);
  }
}
