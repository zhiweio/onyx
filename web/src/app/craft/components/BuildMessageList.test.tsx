import React from "react";
import { fireEvent, screen } from "@testing-library/react";
import { render } from "@tests/setup/test-utils";
import { TooltipProvider } from "@radix-ui/react-tooltip";
import BuildMessageList from "@/app/craft/components/BuildMessageList";
import type { BuildMessage } from "@/app/craft/types/streamingTypes";
import type { StreamItem } from "@/app/craft/types/displayTypes";

jest.mock("@/lib/app/components", () => ({
  Logo: () => <div data-testid="onyx-logo" />,
}));

jest.mock("@/components/chat/MinimalMarkdown", () => ({
  __esModule: true,
  default: ({ content }: { content: string }) => <div>{content}</div>,
}));

jest.mock("@/app/app/message/BlinkingBar", () => ({
  BlinkingBar: () => <span data-testid="blinking-bar" />,
}));

jest.mock("motion/react", () => ({
  AnimatePresence: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
  motion: {
    div: ({
      children,
      initial: _initial,
      animate: _animate,
      exit: _exit,
      transition: _transition,
      ...props
    }: React.HTMLAttributes<HTMLDivElement> & {
      initial?: unknown;
      animate?: unknown;
      exit?: unknown;
      transition?: unknown;
    }) => <div {...props}>{children}</div>,
  },
}));

function scrollRef() {
  const el = document.createElement("div");
  el.scrollTo = jest.fn();
  return { current: el };
}

function renderList(props: {
  messages?: BuildMessage[];
  streamItems?: StreamItem[];
  isStreaming?: boolean;
}) {
  return render(
    <TooltipProvider>
      <BuildMessageList
        sessionId="session-1"
        messages={props.messages ?? []}
        streamItems={props.streamItems ?? []}
        isStreaming={props.isStreaming}
        autoScrollEnabled={false}
        scrollContainerRef={scrollRef()}
      />
    </TooltipProvider>
  );
}

const settledTaskItem: StreamItem = {
  type: "tool_call",
  id: "task-1",
  toolCall: {
    id: "task-1",
    kind: "task",
    toolName: "task",
    title: "Researcher",
    description: "Researcher",
    command: "",
    status: "completed",
    rawOutput: "",
  },
};

const savedAssistantMessage: BuildMessage = {
  id: "assistant-1",
  type: "assistant",
  content: "Final answer",
  timestamp: new Date("2026-01-01T00:00:00Z"),
  message_metadata: {
    streamItems: [
      {
        type: "thinking",
        id: "thought-1",
        content: "Checking the app structure.",
        isStreaming: false,
      },
      {
        type: "text",
        id: "text-1",
        content: "Final answer",
        isStreaming: false,
      },
    ],
  },
};

describe("BuildMessageList thinking visibility", () => {
  it("renders image attachments on user messages", () => {
    renderList({
      messages: [
        {
          id: "user-1",
          type: "user",
          content: "Use this image",
          timestamp: new Date("2026-01-01T00:00:00Z"),
          attachments: [
            {
              name: "reference image.png",
              path: "attachments/reference image.png",
              mimeType: "image/png",
            },
          ],
        },
      ],
    });

    expect(
      screen.getByRole("img", { name: "reference image.png" })
    ).toHaveAttribute(
      "src",
      "/api/build/sessions/session-1/artifacts/attachments/reference%20image.png"
    );
  });

  it("shows restored thought packets as collapsed thinking rows", () => {
    renderList({ messages: [savedAssistantMessage] });

    const thought = screen.getByRole("button", { name: /Thought/ });
    expect(thought).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText("Checking the app structure.")).toBeInTheDocument();

    fireEvent.click(thought);

    expect(thought).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Thought")).toBeInTheDocument();
    expect(screen.getAllByText("Checking the app structure.").length).toBeGreaterThan(
      1
    );
    expect(screen.getByText("Final answer")).toBeInTheDocument();
  });

  it("does not open restored thought packets by default", () => {
    renderList({ messages: [savedAssistantMessage] });

    expect(screen.getByRole("button", { name: /Thought/ })).toHaveAttribute(
      "aria-expanded",
      "false"
    );
    expect(screen.getByText("Checking the app structure.")).toBeInTheDocument();
    expect(screen.getByText("Final answer")).toBeInTheDocument();
  });

  it("keeps completed thought packets collapsed in the active stream", () => {
    renderList({
      isStreaming: true,
      streamItems: [
        {
          type: "thinking",
          id: "settled-thought",
          content: "Checking the app structure.",
          isStreaming: false,
        },
        {
          type: "text",
          id: "stream-text",
          content: "Final answer",
          isStreaming: false,
        },
      ],
    });

    expect(screen.getByRole("button", { name: /Thought/ })).toHaveAttribute(
      "aria-expanded",
      "false"
    );
    expect(screen.getByText("Checking the app structure.")).toBeInTheDocument();
    expect(screen.getByText("Final answer")).toBeInTheDocument();
  });

  it("shows live thought packets as collapsed progress by default", () => {
    renderList({
      isStreaming: true,
      streamItems: [
        {
          type: "thinking",
          id: "live-thought",
          content: "Checking the app structure.",
          isStreaming: true,
        },
      ],
    });

    const thinking = screen.getByRole("button", { name: /Thinking/ });
    expect(thinking).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText("Checking the app structure.")).toBeInTheDocument();

    fireEvent.click(thinking);

    expect(thinking).toHaveAttribute("aria-expanded", "true");
    expect(screen.getAllByText("Checking the app structure.").length).toBeGreaterThan(
      1
    );
  });

  it("does not show planning next after a settled task when idle", () => {
    renderList({
      isStreaming: false,
      streamItems: [settledTaskItem],
    });
    expect(screen.getByRole("button", { name: /Ran task/ })).toBeInTheDocument();
    expect(screen.queryByText("Planning next moves")).not.toBeInTheDocument();
  });

  it("shows planning next after a settled task only while live", () => {
    renderList({
      isStreaming: true,
      streamItems: [settledTaskItem],
    });
    expect(screen.getByRole("button", { name: /Ran task/ })).toBeInTheDocument();
    expect(screen.getByText("Planning next moves")).toBeInTheDocument();
  });

  it("shows stream error packets inline", () => {
    renderList({
      streamItems: [
        {
          type: "error",
          id: "error-1",
          content: "provider model not found",
        },
      ],
    });

    expect(screen.getByRole("alert")).toHaveTextContent(
      "provider model not found"
    );
  });
});
