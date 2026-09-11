import type { Page } from "@playwright/test";
import { test, expect } from "@tests/e2e/chat/fixtures";
import { ChatPage } from "@tests/e2e/chat/ChatPage";
import {
  buildMockStream,
  resetTurnCounter,
} from "@tests/e2e/utils/chatMock";
import { ensureOnboardingComplete } from "@tests/e2e/utils/chatActions";
import { OnyxApiClient } from "@tests/e2e/utils/onyxApiClient";

interface CapturedChatPayload {
  message?: string;
  selected_skill_ids?: string[] | null;
  selected_mcp_server_ids?: number[] | null;
}

async function openExistingChat(
  chatPage: ChatPage,
  api: OnyxApiClient
): Promise<void> {
  const chatId = await api.createChatSession("E2E slash picker");
  await chatPage.page.goto(`/app?chatId=${chatId}`);
  await chatPage.inputBar.textbox.waitFor({ state: "visible", timeout: 15000 });
  await ensureOnboardingComplete(chatPage.page);
}

async function mockAndCaptureSend(page: Page): Promise<CapturedChatPayload> {
  const payload: CapturedChatPayload = {};
  await page.route("**/api/chat/send-chat-message", async (route) => {
    Object.assign(payload, route.request().postDataJSON());
    await route.fulfill({
      status: 200,
      contentType: "text/plain",
      body: buildMockStream("ok"),
    });
  });
  return payload;
}

test.describe("Chat slash picker", () => {
  test.beforeEach(async ({ chatPage, api }) => {
    resetTurnCounter();
    await openExistingChat(chatPage, api);
  });

  test("sends no skill or MCP ids when the picker is unused", async ({
    chatPage,
  }) => {
    const payload = await mockAndCaptureSend(chatPage.page);
    const sent = chatPage.page.waitForRequest("**/api/chat/send-chat-message");
    await chatPage.inputBar.typeText("hello without tools");
    await chatPage.inputBar.clickSend();
    await sent;
    await chatPage.expectHumanMessage("hello without tools");

    expect(payload.selected_skill_ids ?? []).toEqual([]);
    expect(payload.selected_mcp_server_ids ?? []).toEqual([]);
  });

  test("selecting a built-in skill sends selected_skill_ids", async ({
    chatPage,
  }) => {
    const payload = await mockAndCaptureSend(chatPage.page);
    await chatPage.inputBar.openSlashPicker("docx");
    await expect(chatPage.inputBar.skillPickerRow("docx")).toBeVisible();
    await chatPage.inputBar.pickSkill("docx");

    const sent = chatPage.page.waitForRequest("**/api/chat/send-chat-message");
    await chatPage.inputBar.typeText("draft a memo");
    await chatPage.inputBar.clickSend();
    await sent;

    expect(payload.selected_skill_ids).toEqual(["docx"]);
    expect(payload.selected_mcp_server_ids ?? []).toEqual([]);
  });

  test("selecting an MCP server sends selected_mcp_server_ids", async ({
    chatPage,
    api,
  }) => {
    const name = `E2E Slash MCP ${Date.now()}`;
    let serverId: number | null = null;
    try {
      serverId = await api.createPersonalMcpServer(
        name,
        "http://127.0.0.1:9/mcp",
        { authType: "NONE" }
      );
    } catch {
      test.skip(true, "Personal MCP is not available on this deployment");
    }
    if (serverId === null) {
      return;
    }

    await openExistingChat(chatPage, api);
    const payload = await mockAndCaptureSend(chatPage.page);

    await chatPage.inputBar.openSlashPicker();
    await expect(chatPage.inputBar.mcpPickerRow(serverId)).toBeVisible();
    await chatPage.inputBar.pickMcpServer(serverId, name);

    const sent = chatPage.page.waitForRequest("**/api/chat/send-chat-message");
    await chatPage.inputBar.typeText("use this server");
    await chatPage.inputBar.clickSend();
    await sent;

    expect(payload.selected_mcp_server_ids).toEqual([serverId]);
    expect(payload.selected_skill_ids ?? []).toEqual([]);

    await api.deletePersonalMcpServer(serverId);
  });
});
