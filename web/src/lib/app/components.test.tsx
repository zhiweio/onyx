// Guards the white-label contract of the shared Logo component: custom
// assets win over the default Onyx SVG, the display styles behave, and the
// "Powered by" tagline honors the enterprise name and the hide flag.
import { cleanup, render, screen } from "@tests/setup/test-utils";
import { Logo } from "./components";

const mockUseSettings = jest.fn();
const mockResolvedTheme = jest.fn().mockReturnValue("light");

jest.mock("@/lib/settings/hooks", () => ({
  useSettings: () => mockUseSettings(),
}));
jest.mock("next-themes", () => ({
  useTheme: () => ({ resolvedTheme: mockResolvedTheme() }),
}));
// next-intl is NOT mocked: the shared test provider already renders the
// English catalog, so assertions run against the real copy.

function settingsFor(overrides: Record<string, unknown> = {}) {
  return {
    enterprise: null,
    appName: "Onyx",
    logoUrl: null,
    logoDarkUrl: null,
    logotypeUrl: null,
    logotypeDarkUrl: null,
    version: "1.2.3",
    ...overrides,
  };
}

describe("Logo", () => {
  beforeEach(() => {
    mockUseSettings.mockReset();
    mockResolvedTheme.mockReturnValue("light");
  });

  it("falls back to the default Onyx SVG without enterprise settings", () => {
    mockUseSettings.mockReturnValue(settingsFor());
    const { container } = render(<Logo />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("svg")).not.toBeNull();
  });

  it("renders the custom logo and app name when branded", () => {
    mockUseSettings.mockReturnValue(
      settingsFor({
        enterprise: {
          application_name: "Acme AI",
          use_custom_logo: true,
          logo_display_style: null,
          hide_onyx_branding: false,
        },
        appName: "Acme AI",
        logoUrl: "/api/enterprise-settings/logo?v=1",
      })
    );
    const { container } = render(<Logo />);
    const img = container.querySelector("img");
    expect(img).not.toBeNull();
    expect(img?.getAttribute("src")).toBe("/api/enterprise-settings/logo?v=1");
    // Truncated renders a measuring copy, so query with the all-variant.
    expect(screen.getAllByText("Acme AI").length).toBeGreaterThan(0);
    // The tagline carries the enterprise name, not "Onyx".
    expect(screen.getByText("Powered by Acme AI")).toBeInTheDocument();
  });

  it("serves the dark asset in dark mode when the flag is on", () => {
    mockResolvedTheme.mockReturnValue("dark");
    mockUseSettings.mockReturnValue(
      settingsFor({
        enterprise: {
          application_name: "Acme AI",
          use_custom_logo: true,
          logo_display_style: null,
        },
        appName: "Acme AI",
        logoUrl: "/api/enterprise-settings/logo?v=1",
        logoDarkUrl: "/api/enterprise-settings/logo-dark?v=1",
      })
    );
    const { container } = render(<Logo />);
    expect(container.querySelector("img")?.getAttribute("src")).toBe(
      "/api/enterprise-settings/logo-dark?v=1"
    );
  });

  it("logo_only style hides the name; name_only hides the mark", () => {
    mockUseSettings.mockReturnValue(
      settingsFor({
        enterprise: {
          application_name: "Acme AI",
          use_custom_logo: true,
          logo_display_style: "logo_only",
        },
        appName: "Acme AI",
        logoUrl: "/api/enterprise-settings/logo?v=1",
      })
    );
    const { container: logoOnly } = render(<Logo />);
    expect(logoOnly.querySelector("img")).not.toBeNull();
    // The name heading is gone; the powered-by tagline remains by design.
    expect(screen.getByText("Powered by Acme AI")).toBeInTheDocument();
    // No standalone "Acme AI" text nodes (Truncated renders two when shown).
    expect(screen.queryAllByText("Acme AI")).toHaveLength(0);
    cleanup();

    // name_only: no logo image, name text only
    mockUseSettings.mockReturnValue(
      settingsFor({
        enterprise: {
          application_name: "Acme AI",
          use_custom_logo: true,
          logo_display_style: "name_only",
        },
        appName: "Acme AI",
        logoUrl: "/api/enterprise-settings/logo?v=1",
      })
    );
    const { container: nameOnly } = render(<Logo />);
    expect(nameOnly.querySelector("img")).toBeNull();
    expect(screen.getAllByText("Acme AI").length).toBeGreaterThan(0);
  });

  it("hides the powered-by tagline when hide_onyx_branding is set", () => {
    mockUseSettings.mockReturnValue(
      settingsFor({
        enterprise: {
          application_name: "Acme AI",
          use_custom_logo: true,
          logo_display_style: null,
          hide_onyx_branding: true,
        },
        appName: "Acme AI",
        logoUrl: "/api/enterprise-settings/logo?v=1",
      })
    );
    render(<Logo />);
    expect(screen.queryByText(/Powered by/)).toBeNull();
  });

  it("renders the custom logotype instead of the name text when uploaded", () => {
    mockUseSettings.mockReturnValue(
      settingsFor({
        enterprise: {
          application_name: "Acme AI",
          use_custom_logo: true,
          use_custom_logotype: true,
          logo_display_style: null,
        },
        appName: "Acme AI",
        logoUrl: "/api/enterprise-settings/logo?v=1",
        logotypeUrl: "/api/enterprise-settings/logotype?v=1",
      })
    );
    const { container } = render(<Logo />);
    const srcs = Array.from(container.querySelectorAll("img")).map((img) =>
      img.getAttribute("src")
    );
    expect(srcs).toContain("/api/enterprise-settings/logotype?v=1");
  });
});
