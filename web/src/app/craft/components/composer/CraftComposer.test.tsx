import React, { createRef } from "react";
import { act, fireEvent, screen } from "@testing-library/react";
import { render } from "@tests/setup/test-utils";
import CraftComposer from "@/app/craft/components/composer/CraftComposer";
import {
  UploadFileStatus,
  type BuildFile,
} from "@/app/craft/contexts/UploadFilesContext";
import type { LexicalPromptInputHandle } from "@/sections/input/lexical";
import type { SkillsList } from "@/lib/skills/types";
import type { SlashSelection } from "@/lib/skills/picker";

const mockClearFiles = jest.fn();
let mockSkillsData: SkillsList | undefined;
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
  default: () => ({ data: mockSkillsData }),
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

function builtinSkill(id: string): SkillsList["builtins"][number] {
  return {
    source: "builtin",
    id,
    name: id,
    description: "",
    is_available: true,
    unavailable_reason: null,
    is_valid: true,
    is_personal: false,
    enabled: true,
    can_toggle: true,
    author_user_id: null,
    author_email: null,
    owner: null,
    ownership_vacant: false,
    created_at: null,
    updated_at: null,
    user_shares: [],
    group_shares: [],
    public_permission: "VIEWER",
    user_permission: null,
    external_app: null,
  };
}

function renderComposer(
  props: Partial<React.ComponentProps<typeof CraftComposer>> = {}
) {
  const editorHandleRef = createRef<LexicalPromptInputHandle | null>();
  const onSubmit = jest.fn();
  const onQueueMessage = jest.fn();
  const baseProps: React.ComponentProps<typeof CraftComposer> = {
    sessionId: "session-1",
    editorHandleRef,
    onSubmit,
    onQueueMessage,
    isRunning: false,
    modelSelection: null,
    onModelChange: jest.fn(),
    ...props,
  };
  const utils = render(<CraftComposer {...baseProps} />);
  return {
    editorHandleRef,
    onSubmit,
    onQueueMessage,
    rerender: (selection: SlashSelection) =>
      utils.rerender(
        <CraftComposer {...baseProps} persistedSelection={selection} />
      ),
  };
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
      emptySelection
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
      emptySelection
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
      window.localStorage.getItem("onyx-composer-draft:v1:craft:session-1")
    ).toContain("draft in progress");

    fireEvent.keyDown(screen.getByTestId("craft-message-input"), {
      key: "Enter",
      keyCode: 13,
    });
    expect(
      window.localStorage.getItem("onyx-composer-draft:v1:craft:session-1")
    ).toBeNull();
  });

  it("serializes each distinct library file exactly once", () => {
    const { editorHandleRef, onSubmit } = renderComposer();
    const years = ["2021", "2022", "2023", "2024", "2025"];
    act(() => {
      editorHandleRef.current?.insertMention({
        id: "skill:financial-report-analysis",
        category: "skills",
        label: "/financial-report-analysis",
        value: "financial-report-analysis",
        markdown: "/financial-report-analysis",
      });
      editorHandleRef.current?.appendText("为雪龙集团撰写财报分析");
      years.forEach((year) => {
        editorHandleRef.current?.insertMention({
          id: `file:${year}`,
          category: "files",
          label: `@雪龙集团${year}.pdf`,
          value: year,
          markdown: `@雪龙集团${year}.pdf`,
          data: { fileId: year, scope: "library" },
        });
      });
    });
    fireEvent.keyDown(screen.getByTestId("craft-message-input"), {
      key: "Enter",
      keyCode: 13,
    });

    const text = onSubmit.mock.calls[0]?.[0] as string;
    expect(text.match(/\/financial-report-analysis/g)).toHaveLength(1);
    for (const year of years) {
      const chip = `@雪龙集团${year}.pdf`;
      const count = text.split(chip).length - 1;
      expect(count).toBe(1);
    }
  });

  it("re-arms exactly one skill chip after submit", async () => {
    mockSkillsData = { builtins: [builtinSkill("pptx")], customs: [] };
    const { editorHandleRef, onSubmit, rerender } = renderComposer();
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

    // Hold the re-arm frame back so the persisted-selection effect (fired by
    // the post-submit rerender) sees the cleared editor first — the exact
    // ordering that used to double-insert the chip.
    const frames: FrameRequestCallback[] = [];
    const rafSpy = jest
      .spyOn(window, "requestAnimationFrame")
      .mockImplementation((cb: FrameRequestCallback) => {
        frames.push(cb);
        return frames.length;
      });
    try {
      fireEvent.keyDown(screen.getByTestId("craft-message-input"), {
        key: "Enter",
        keyCode: 13,
      });
      expect(onSubmit.mock.calls[0]?.[0]).toBe("/pptx make slides");

      // Post-submit rerender delivers the session's persistent selection.
      rerender({
        skillIds: ["pptx"],
        mcpServerIds: [],
      });
      // Now let the re-arm frame land.
      act(() => {
        frames.splice(0).forEach((cb) => cb(0));
      });
    } finally {
      rafSpy.mockRestore();
    }

    const mentions = editorHandleRef.current?.getMentions() ?? [];
    expect(mentions.filter((m) => m.category === "skills")).toHaveLength(1);
  });
});
