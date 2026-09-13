/**
 * Page Object Model for the Craft library settings page (/craft/v1/library)
 * and the plus-menu path that opens it.
 */

import { expect, type Locator, type Page } from "@playwright/test";

async function suppressCraftIntro(page: Page): Promise<void> {
  const me = await page.request.get("/api/me");
  if (!me.ok()) return;
  const body = (await me.json()) as { id?: string };
  if (!body.id) return;
  await page.addInitScript((userId: string) => {
    window.localStorage.setItem(`onyx:craftOnboardingSeen:${userId}`, "true");
  }, body.id);
}

export class CraftLibraryPage {
  readonly page: Page;
  readonly container: Locator;
  readonly search: Locator;
  readonly newFolderButton: Locator;
  readonly uploadButton: Locator;
  readonly dropzone: Locator;
  readonly folderNameInput: Locator;
  readonly plusMenu: Locator;

  constructor(page: Page) {
    this.page = page;
    this.container = page.getByTestId("CraftLibraryPage/container");
    this.search = page.getByPlaceholder(/Search files|搜索文件/);
    this.newFolderButton = page.getByRole("button", {
      name: /New folder|新建文件夹/,
    });
    this.uploadButton = page.getByRole("button", { name: /^(Upload|上传)$/ });
    this.dropzone = page.getByRole("button", {
      name: /Drag files here or click to upload|将文件拖到此处或点击上传/,
    });
    this.folderNameInput = page.getByPlaceholder(
      /Enter folder name|输入文件夹名称/
    );
    this.plusMenu = page.getByTestId("craft-plus-menu");
  }

  async goto(): Promise<void> {
    await suppressCraftIntro(this.page);
    await this.page.goto("/craft/v1/library");
    await this.page.waitForURL("**/craft/v1/library**");
    await expect(this.container).toBeVisible({ timeout: 15000 });
  }

  async expectSettingsPage(): Promise<void> {
    await expect(this.container).toBeVisible();
    await expect(this.search).toBeVisible();
    await expect(this.uploadButton).toBeVisible();
    await expect(this.page.getByRole("dialog")).toHaveCount(0);
  }

  async expectSidebarSelected(): Promise<void> {
    await expect(this.sidebarTab()).toBeVisible();
  }

  sidebarTab(): Locator {
    return this.page.getByRole("button", { name: /^(Library|资料库)$/ }).first();
  }

  async openNewFolderPanel(): Promise<void> {
    await this.newFolderButton.click();
    await expect(this.folderNameInput).toBeVisible();
    await expect(this.page.getByRole("dialog")).toHaveCount(0);
  }

  async cancelNewFolder(): Promise<void> {
    await this.page.getByRole("button", { name: /Cancel|取消/ }).click();
    await expect(this.folderNameInput).toBeHidden();
  }

  async manageFromPlusMenu(): Promise<void> {
    await this.page
      .getByRole("button", { name: /Open add menu|打开添加菜单/ })
      .click();
    await expect(this.plusMenu).toBeVisible();
    await this.plusMenu
      .getByRole("button", { name: /^(Library|资料库)$/ })
      .click();
    await this.plusMenu.getByRole("link", { name: /^(Manage|管理)$/ }).click();
    await this.page.waitForURL("**/craft/v1/library**");
    await expect(this.container).toBeVisible({ timeout: 15000 });
  }
}
