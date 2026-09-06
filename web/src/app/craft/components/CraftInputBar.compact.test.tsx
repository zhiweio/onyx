import React from "react";
import { act } from "@testing-library/react";
import { render } from "@tests/setup/test-utils";
import CraftInputBar from "@/app/craft/components/CraftInputBar";
import type { PickerEntry } from "@/lib/skills/picker";
import { COMPACT_COMMAND_SLUG } from "@/lib/skills/picker";

const mockAddEntryPath: { onSelect?: (entry: PickerEntry) => void } = {};

jest.mock("@/app/craft/contexts/UploadFilesContext", () => {
  const actual = jest.requireActual<
    typeof import("@/app/craft/contexts/UploadFilesContext")
  >("@/app/craft/contexts/UploadFilesContext");
  return {
    ...actual,
    useUploadFilesContext: () => ({
      currentMessageFiles: [],
      uploadFiles: jest.fn(),
      removeFile: jest.fn(),
      clearFiles: jest.fn(),
      hasUploadingFiles: false,
    }),
  };
});

jest.mock("@/sections/input/BaseInputBar", () => {
  const React = jest.requireActual<typeof import("react")>("react");
  return {
    __esModule: true,
    default: React.forwardRef(() => <div data-testid="base-input" />),
  };
});

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: [], mutate: jest.fn() }),
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

jest.mock("@/hooks/useEscapeInterrupt", () => ({
  useEscapeInterrupt: jest.fn(),
}));

jest.mock("@/hooks/useSlashPicker", () => ({
  __esModule: true,
  default: ({ onSelect }: { onSelect: (entry: PickerEntry) => void }) => {
    mockAddEntryPath.onSelect = onSelect;
    return {
      open: false,
      anchorRect: null,
      query: "",
      onInput: jest.fn(),
      onSelectionChange: jest.fn(),
      onSelect,
      onClose: jest.fn(),
      reset: jest.fn(),
    };
  },
}));

jest.mock("@/app/craft/components/buildEntryMenuItems", () => ({
  buildEntryMenuItems: () => [],
}));

jest.mock("@/sections/input/EntryInfoPopover", () => () => null);
jest.mock("@/sections/input/EntryPickerPopover", () => () => null);
jest.mock("@/app/craft/components/InterruptHint", () => () => null);
jest.mock("@/app/craft/components/ContextRing", () => () => null);
jest.mock("@/sections/input/InputChipStrip", () => ({
  InputChipStrip: () => null,
}));
jest.mock("@/sections/input/PlusMenuButton", () => ({
  PlusMenuButton: () => null,
}));
jest.mock("@/app/craft/components/UserLibraryModal", () => () => null);

describe("CraftInputBar compact command", () => {
  it("routes a compact picker selection to onCompact, not a chip", () => {
    const onCompact = jest.fn();
    const onSubmit = jest.fn();

    render(
      <CraftInputBar
        onSubmit={onSubmit}
        isRunning={false}
        compactAvailable
        onCompact={onCompact}
      />
    );

    expect(mockAddEntryPath.onSelect).toBeDefined();
    act(() => {
      mockAddEntryPath.onSelect?.({
        kind: "command",
        slug: COMPACT_COMMAND_SLUG,
        name: "Compact context",
        description: "Summarize earlier context to free up space",
      });
    });

    expect(onCompact).toHaveBeenCalledTimes(1);
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
