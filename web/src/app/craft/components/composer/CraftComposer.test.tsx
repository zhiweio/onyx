import React, { createRef } from "react";
import { act, fireEvent, screen } from "@testing-library/react";
import { render } from "@tests/setup/test-utils";
import CraftComposer from "@/app/craft/components/composer/CraftComposer";
import {
  UploadFileStatus,
  type BuildFile,
} from "@/app/craft/contexts/UploadFilesContext";
import type { LexicalPromptInputHandle } from "@/sections/input/lexical";
import type { SlashSelection } from "@/lib/skills/picker";

const mockClearFiles = jest.fn();
const attachedFiles: BuildFile[] = [
  {
    id: "file-1",
    name: "reference.png",
    status: UploadFileStatus.COMPLETED,
    file_type: "image/png",
    size: 123,
    created_at: "2026-07-28T00:00:00.000Z",
    path: "attachments/reference.png",
  },
];

jest.mock("@/app/craft/contexts/UploadFilesContext", () => {
  const actual = jest.requireActual<
    typeof import("@/app/craft/contexts/UploadFilesContext")
  >("@/app/craft/contexts/UploadFilesContext");
  return {
    ...actual,
    useUploadFilesContext: () => ({
      currentMessageFiles: attachedFiles,
      uploadFiles: jest.fn(),
      removeFile: jest.fn(),
      clearFiles: mockClearFiles,
      hasUploadingFiles: false,
    }),
  };
});

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: [] }),
  SWRConfig: jest.requireActual("swr").SWRConfig,
}));

jest.mock("@/hooks/useUserSkills", () => ({
  __esModule: true,
  default: () => ({ data: undefined }),
}));

jest.mock("@/hooks/useUserExternalApps", () => ({
  __esModule: true,
  default: () => ({ data: undefined }),
}));

jest.mock("@/lib/tools/hooks", () => ({
  useCraftMcpServers: () => ({ data: undefined }),
}));

jest.mock("@/providers/UserProvider", () => ({
  useUser: () => ({ user: { id: "user-1" } }),
}));

jest.mock("@/app/craft/components/ModelPickerButton", () => () => null);

jest.mock("@/app/craft/components/buildEntryMenuItems", () => ({
  buildEntryMenuItems: () => [],
}));

const emptySelection: SlashSelection = { skillIds: [], mcpServerIds: [] };

function renderComposer(
  props: Partial<React.ComponentProps<typeof CraftComposer>> = {},
) {
  const editorHandleRef = createRef<LexicalPromptInputHandle | null>();
  const onSubmit = jest.fn();
  const onQueueMessage = jest.fn();
  render(
    <CraftComposer
      sessionId="session-1"
      editorHandleRef={editorHandleRef}
      onSubmit={onSubmit}
      onQueueMessage={onQueueMessage}
      isRunning={false}
      modelSelection={null}
      onModelChange={jest.fn()}
      {...props}
    />,
  );
  return { editorHandleRef, onSubmit, onQueueMessage };
}

describe("CraftComposer", () => {
  beforeEach(() => {
    window.localStorage.clear();
    jest.clearAllMocks();
  });

  it("submits text, attachments, and the empty selection on Enter", () => {
    const { editorHandleRef, onSubmit } = renderComposer();
    act(() => {
      editorHandleRef.current?.setText("build a landing page");
    });
    fireEvent.keyDown(screen.getByTestId("craft-message-input"), {
      key: "Enter",
      keyCode: 13,
    });

    expect(onSubmit).toHaveBeenCalledWith(
      "build a landing page",
      attachedFiles,
      emptySelection,
    );
    expect(mockClearFiles).toHaveBeenCalledWith({ suppressRefetch: true });
  });

  it("serializes skill chips into the message and the structured selection", () => {
    const { editorHandleRef, onSubmit } = renderComposer();
    act(() => {
      editorHandleRef.current?.insertMention({
        id: "skill:pptx",
        category: "skills",
        label: "/pptx",
        value: "pptx",
        markdown: "/pptx",
      });
      editorHandleRef.current?.appendText("make slides");
    });
    fireEvent.keyDown(screen.getByTestId("craft-message-input"), {
      key: "Enter",
      keyCode: 13,
    });

    expect(onSubmit).toHaveBeenCalledWith("/pptx make slides", attachedFiles, {
      skillIds: ["pptx"],
      mcpServerIds: [],
    });
  });

  it("queues a follow-up with attachments while running", () => {
    const { editorHandleRef, onSubmit, onQueueMessage } = renderComposer({
      isRunning: true,
    });
    act(() => {
      editorHandleRef.current?.setText("add charts");
    });
    fireEvent.keyDown(screen.getByTestId("craft-message-input"), {
      key: "Enter",
      keyCode: 13,
    });

    expect(onQueueMessage).toHaveBeenCalledWith(
      "add charts",
      attachedFiles,
      emptySelection,
    );
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("serializes file chips inline with the @ prefix", () => {
    const { editorHandleRef, onSubmit } = renderComposer();
    act(() => {
      editorHandleRef.current?.insertMention({
        id: "file:1",
        category: "files",
        label: "@brand-guidelines.pdf",
        value: "1",
        markdown: "@brand-guidelines.pdf",
        data: { fileId: "1", scope: "library" },
      });
    });
    fireEvent.keyDown(screen.getByTestId("craft-message-input"), {
      key: "Enter",
      keyCode: 13,
    });

    expect(onSubmit.mock.calls[0]?.[0]).toContain("@brand-guidelines.pdf");
    expect(onSubmit.mock.calls[0]?.[2]).toEqual(emptySelection);
  });

  it("persists a draft per session and clears it on submit", async () => {
    const { editorHandleRef } = renderComposer();
    act(() => {
      editorHandleRef.current?.setText("draft in progress");
    });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 600));
    });
    expect(
      window.localStorage.getItem("onyx-composer-draft:v1:craft:session-1"),
    ).toContain("draft in progress");

    fireEvent.keyDown(screen.getByTestId("craft-message-input"), {
      key: "Enter",
      keyCode: 13,
    });
    expect(
      window.localStorage.getItem("onyx-composer-draft:v1:craft:session-1"),
    ).toBeNull();
  });
});
