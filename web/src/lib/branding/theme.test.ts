import { buildBrandThemeCss } from "./theme";

describe("buildBrandThemeCss", () => {
  it("returns empty css when no colors are configured", () => {
    expect(buildBrandThemeCss({})).toBe("");
    expect(buildBrandThemeCss({ brandColor: null })).toBe("");
    expect(buildBrandThemeCss({ brandColor: "  ", brandColorDark: "" })).toBe(
      ""
    );
  });

  it("emits light-mode overrides for :root only", () => {
    const css = buildBrandThemeCss({ brandColor: "#0055FF" });
    expect(css).toContain(":root {");
    expect(css).toContain("--theme-primary-05: #0055FF");
    expect(css).toContain("--action-selection-05: #0055FF");
    expect(css).toContain("--action-text-link-05: #0055FF");
    expect(css).toContain("color-mix(in srgb, #0055FF 78%, #000)");
    expect(css).not.toContain(".dark {");
  });

  it("emits dark-mode overrides only when a dark color is set", () => {
    const css = buildBrandThemeCss({ brandColorDark: "#003366" });
    expect(css).toContain(".dark {");
    expect(css).toContain(
      "--theme-primary-05: color-mix(in srgb, #003366 92%, #fff)"
    );
    expect(css).not.toContain(":root {");
  });

  it("emits both blocks when both colors are set", () => {
    const css = buildBrandThemeCss({
      brandColor: "#0055FF",
      brandColorDark: "#66AAFF",
    });
    expect(css).toContain(":root {");
    expect(css).toContain(".dark {");
    expect(css.indexOf(":root {")).toBeLessThan(css.indexOf(".dark {"));
  });

  it("rejects values that are not hex colors (style-tag injection guard)", () => {
    expect(
      buildBrandThemeCss({ brandColor: "red; } body { display:none" })
    ).toBe("");
    expect(buildBrandThemeCss({ brandColor: "url(javascript:alert(1))" })).toBe(
      ""
    );
    // Short hex and 8-digit hex are still valid.
    expect(buildBrandThemeCss({ brandColor: "#FFF" })).toContain("#FFF");
    expect(buildBrandThemeCss({ brandColor: "#0055FFAA" })).toContain(
      "#0055FFAA"
    );
  });
});
