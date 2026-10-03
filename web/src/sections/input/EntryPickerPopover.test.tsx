import React from "react";
import { fireEvent, screen } from "@testing-library/react";
import { render } from "@tests/setup/test-utils";
import EntryPickerPopover from "@/sections/input/EntryPickerPopover";
import type { PickerSections } from "@/lib/skills/picker";

const sections: PickerSections = {
  commands: [
    {
      kind: "command",
      slug: "compact",
      name: "Compact",
      description: "Compact the conversation",
    },
  ],
  scenarios: [
    {
      kind: "scenario",
      scenarioId: "s1",
      name: "Quarterly review",
      description: "compile the quarterly business review",
    },
  ],
  skills: [
    {
      kind: "skill",
      slug: "pptx",
      name: "pptx",
      description: "Build slide decks",
    },
    {
      kind: "skill",
      slug: "docx",
      name: "docx",
      description: "Write documents",
    },
  ],
  apps: [
    {
      kind: "app",
      externalAppId: 1,
      name: "Slack",
      appType: "SLACK",
      authenticated: true,
    },
  ],
  files: [
    {
      kind: "file",
      fileId: "f1",
      name: "notes.txt",
      path: "user_library/notes.txt",
      source: "library",
    },
  ],
};

const ANCHOR = new DOMRect(10, 10, 400, 1);

function renderPopover(
  props: Partial<React.ComponentProps<typeof EntryPickerPopover>> = {}
) {
  const onSelect = jest.fn();
  const onClose = jest.fn();
  const onQueryChange = jest.fn();
  const utils = render(
    <EntryPickerPopover
      open
      anchorRect={ANCHOR}
      query=""
      sections={sections}
      onSelect={onSelect}
      onClose={onClose}
      onQueryChange={onQueryChange}
      searchable
      {...props}
    />
  );
  return { ...utils, onSelect, onClose, onQueryChange };
}

describe("EntryPickerPopover (searchable)", () => {
  it("renders every group header uppercase with rows and the footer tip", () => {
    renderPopover();
    for (const header of ["Commands", "Scenarios", "Skills", "Apps", "Files"]) {
      expect(screen.getByText(header)).toBeInTheDocument();
    }
    expect(screen.getByTestId("picker-footer-tip")).toHaveTextContent(
      "Type to search commands, skills, apps, and more"
    );
    expect(screen.getByTestId("skill-picker-row-pptx")).toBeInTheDocument();
    expect(screen.getByTestId("scenario-picker-row-s1")).toBeInTheDocument();
  });

  it("filters across groups from the search input", () => {
    const view = renderPopover();
    const input = screen.getByPlaceholderText(
      "Search commands, skills, apps, and files…"
    );
    fireEvent.change(input, { target: { value: "docx" } });
    expect(view.onQueryChange).toHaveBeenCalledWith("docx");

    // The host mirrors the query back (controlled component).
    view.rerender(
      <EntryPickerPopover
        open
        anchorRect={ANCHOR}
        query="docx"
        sections={sections}
        onSelect={jest.fn()}
        onClose={jest.fn()}
        onQueryChange={jest.fn()}
        searchable
      />
    );
    expect(screen.getByTestId("skill-picker-row-docx")).toBeInTheDocument();
    expect(screen.queryByTestId("skill-picker-row-pptx")).toBeNull();
    expect(screen.queryByTestId("app-picker-row-1")).toBeNull();
  });

  it("Enter selects the highlighted row from the search input focus", () => {
    const { onSelect } = renderPopover({ query: "pptx" });
    const input = screen.getByPlaceholderText(
      "Search commands, skills, apps, and files…"
    );
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "skill", slug: "pptx" })
    );
  });

  it("Escape closes the menu", () => {
    const { onClose } = renderPopover();
    fireEvent.keyDown(screen.getByTestId("skill-picker-popover"), {
      key: "Escape",
    });
    expect(onClose).toHaveBeenCalled();
  });

  it("shows the empty state when nothing matches", () => {
    renderPopover({ query: "zzz" });
    expect(screen.getByText("No matching skills")).toBeInTheDocument();
    // The footer tip stays.
    expect(screen.getByTestId("picker-footer-tip")).toBeInTheDocument();
  });

  it("hides the search input when not searchable", () => {
    renderPopover({ searchable: false });
    expect(
      screen.queryByPlaceholderText(
        "Search commands, skills, apps, and files…"
      )
    ).toBeNull();
    // The footer tip is trigger-menu-only furniture too? No: it renders for
    // any popover; ScheduleTaskForm keeps its compact look via searchable.
    expect(screen.getByTestId("picker-footer-tip")).toBeInTheDocument();
  });
});
