/**
 * Runtime brand-color overrides for the Opal design tokens.
 *
 * The Opal token build maps `--theme-primary-*` (buttons, chrome) and
 * `--action-selection-*` (selection, links) to fixed neutrals/blues. When an
 * admin configures brand colors we re-point those variables with CSS
 * `color-mix()` derivations, injected as a single <style> tag — server-side
 * in the root layout (no flash) and live in the branding admin page preview.
 *
 * Dark mode is only overridden when a dark brand color was explicitly set;
 * otherwise the dark theme keeps its neutral defaults.
 */

export const BRAND_THEME_STYLE_ID = "onyx-brand-theme";

function assertHexColor(color: string): string {
  // Server-side validation guarantees hex, but this CSS is interpolated into
  // a style tag — enforce the shape here so nothing else can slip through.
  if (!/^#[0-9a-fA-F]{3,8}$/.test(color)) {
    return "";
  }
  return color;
}

export function buildBrandThemeCss(colors: {
  brandColor?: string | null;
  brandColorDark?: string | null;
}): string {
  const light = assertHexColor(colors.brandColor?.trim() ?? "");
  const dark = assertHexColor(colors.brandColorDark?.trim() ?? "");
  if (!light && !dark) return "";

  const rules: string[] = [];
  if (light) {
    rules.push(`:root {
  --theme-primary-06: color-mix(in srgb, ${light} 78%, #000);
  --theme-primary-05: ${light};
  --theme-primary-04: color-mix(in srgb, ${light} 88%, #fff);
  --action-selection-06: color-mix(in srgb, ${light} 80%, #000);
  --action-selection-05: ${light};
  --action-selection-04: color-mix(in srgb, ${light} 85%, #fff);
  --action-selection-03: color-mix(in srgb, ${light} 45%, #fff);
  --action-selection-02: color-mix(in srgb, ${light} 30%, #fff);
  --action-selection-01: color-mix(in srgb, ${light} 18%, #fff);
  --action-selection-00: color-mix(in srgb, ${light} 8%, #fff);
  --action-text-link-05: ${light};
}`);
  }
  if (dark) {
    rules.push(`.dark {
  --theme-primary-06: color-mix(in srgb, ${dark} 85%, #fff);
  --theme-primary-05: color-mix(in srgb, ${dark} 92%, #fff);
  --theme-primary-04: color-mix(in srgb, ${dark} 78%, #fff);
  --action-selection-06: color-mix(in srgb, ${dark} 75%, #fff);
  --action-selection-05: color-mix(in srgb, ${dark} 88%, #fff);
  --action-selection-04: ${dark};
  --action-selection-03: color-mix(in srgb, ${dark} 45%, #000);
  --action-selection-02: color-mix(in srgb, ${dark} 30%, #000);
  --action-selection-01: color-mix(in srgb, ${dark} 20%, #000);
  --action-selection-00: color-mix(in srgb, ${dark} 10%, #000);
  --action-text-link-05: color-mix(in srgb, ${dark} 88%, #fff);
}`);
  }
  return rules.join("\n");
}
