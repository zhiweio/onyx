import { render, screen, setupUser } from "@tests/setup/test-utils";
import { SvgMcp, SvgSparkle } from "@opal/icons";
import PlusMenuButton, {
  type PlusMenuItem,
} from "@/sections/input/PlusMenuButton";

const skillsItem: PlusMenuItem = {
  key: "skills",
  icon: SvgSparkle,
  label: "Skills",
  panel: {
    searchPlaceholder: "Search skills...",
    manageLabel: "Manage",
    manageHref: "/craft/v1/skills",
    manageTarget: "_blank",
    emptyLabel: "No skills yet.",
    rows: [
      {
        key: "pptx",
        icon: SvgSparkle,
        label: "PPTX",
        checked: false,
        onCheckedChange: jest.fn(),
      },
    ],
  },
};

const mcpItem: PlusMenuItem = {
  key: "mcp",
  icon: SvgMcp,
  label: "MCP",
  panel: {
    searchPlaceholder: "Search MCPs...",
    manageLabel: "Manage",
    manageHref: "/craft/v1/mcp-actions",
    manageTarget: "_blank",
    emptyLabel: "No MCP servers yet.",
    rows: [],
  },
};

describe("PlusMenuButton", () => {
  it("drills into a panel with search, manage, and a switch", async () => {
    const user = setupUser();
    const onCheckedChange = jest.fn();
    skillsItem.panel!.rows[0]!.onCheckedChange = onCheckedChange;

    render(<PlusMenuButton items={[skillsItem, mcpItem]} />);

    await user.click(screen.getByRole("button", { name: "Open add menu" }));
    expect(screen.getByRole("button", { name: "Skills" })).toBeVisible();
    expect(screen.getByRole("button", { name: "MCP" })).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Skills" }));

    expect(screen.getByPlaceholderText("Search skills...")).toBeVisible();
    expect(screen.getByRole("link", { name: "Manage" })).toHaveAttribute(
      "href",
      "/craft/v1/skills"
    );
    await user.click(screen.getByRole("switch", { name: "Toggle PPTX" }));
    expect(onCheckedChange).toHaveBeenCalledWith(true);
    expect(screen.getByPlaceholderText("Search skills...")).toBeVisible();
  });
});
