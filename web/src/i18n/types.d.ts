import type { Locale } from "@/i18n/config";

// NOTE: deliberately NO `Messages` augmentation. Typing Messages as
// `typeof en.json` feeds next-intl's NestedKeyOf recursion over the entire
// ~40k-key catalog at every `useTranslations` call site, which pushed
// `tsc`/`tsgo` to tens of GB of RSS and hours of CPU without ever finishing
// (Map-maximum-size crashes). Message keys are therefore plain strings for
// the compiler; correctness is guarded at runtime instead:
// - key parity across locales: scripts/i18n-parity.mjs (runs in types:check)
// - ICU placeholder parity: src/i18n/__tests__/catalog.test.ts
// - missing keys log MISSING_MESSAGE errors in dev/test runs
declare module "next-intl" {
  interface AppConfig {
    Locale: Locale;
  }
}
