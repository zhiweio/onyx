import { render, screen, setupUser } from "@tests/setup/test-utils";
import CraftMcpActionsPage from "@/app/craft/v1/mcp-actions/page";

const mockPageContent = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), back: jest.fn() }),
  usePathname: () => "/craft/v1/mcp-actions",
  useSearchParams: () => new URLSearchParams(),
}));

jest.mock("@/sections/actions/MCPPageContent", () => ({
  __esModule: true,
  default: (props: { variant?: string }) => {
    mockPageContent(props);
    return (
      <div data-testid="mcp-page-content" data-variant={props.variant ?? ""} />
    );
  },
}));

beforeEach(() => {
  mockPageContent.mockClear();
});

test("craft MCP page starts on Mine and switches to a read-only gallery", async () => {
  const user = setupUser();
  render(<CraftMcpActionsPage />);

  expect(screen.getByTestId("GalleryTabs/mine")).toBeInTheDocument();
  expect(screen.getByTestId("GalleryTabs/gallery")).toBeInTheDocument();
  expect(screen.getByTestId("mcp-page-content")).toHaveAttribute(
    "data-variant",
    "personal"
  );

  await user.click(screen.getByTestId("GalleryTabs/gallery"));

  expect(screen.getByTestId("mcp-page-content")).toHaveAttribute(
    "data-variant",
    "gallery"
  );
});
