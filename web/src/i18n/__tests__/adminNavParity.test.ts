/**
 * Runtime guard for the admin sidebar label catalog. `useAdminNavLabels`
 * resolves every `AdminNavItemId` through `sidebar.adminNav.items.<id>.label`,
 * but the repo's `tsc` run currently crashes before reporting missing keys,
 * so drift ships silently (four admin pages once rendered icon-only).
 *
 * Checks, per locale:
 * - every nav id used by NAV_ITEM_IDS has a non-empty label,
 * - the items key set is identical across locales,
 * - the dead `admin.sidebar.*` namespace stays gone.
 */
import { NAV_ITEM_IDS } from "@/lib/admin-sidebar-utils";

import ar from "@/i18n/messages/ar.json";
import de from "@/i18n/messages/de.json";
import en from "@/i18n/messages/en.json";
import es from "@/i18n/messages/es.json";
import fr from "@/i18n/messages/fr.json";
import ja from "@/i18n/messages/ja.json";
import ko from "@/i18n/messages/ko.json";
import pt from "@/i18n/messages/pt.json";
import zh from "@/i18n/messages/zh.json";

type MessageTree = { [key: string]: string | MessageTree };

const CATALOGS: Record<string, MessageTree> = {
  ar,
  de,
  en,
  es,
  fr,
  ja,
  ko,
  pt,
  zh,
};

const NAV_IDS = new Set(
  Object.values(NAV_ITEM_IDS).filter((id) => id !== null)
);

function navItems(tree: MessageTree): Record<string, MessageTree> {
  const sidebar = tree["sidebar"];
  if (typeof sidebar !== "object" || sidebar === null) {
    throw new Error("locale is missing the sidebar namespace");
  }
  const adminNav = (sidebar as MessageTree)["adminNav"];
  if (typeof adminNav !== "object" || adminNav === null) {
    throw new Error("locale is missing sidebar.adminNav");
  }
  const items = (adminNav as MessageTree)["items"];
  if (typeof items !== "object" || items === null) {
    throw new Error("locale is missing sidebar.adminNav.items");
  }
  return items as Record<string, MessageTree>;
}

describe("admin sidebar nav labels", () => {
  test("NAV_ITEM_IDS yields at least one nav id", () => {
    expect(NAV_IDS.size).toBeGreaterThan(0);
  });

  for (const [locale, catalog] of Object.entries(CATALOGS)) {
    test(`${locale}: every nav id has a non-empty label`, () => {
      const items = navItems(catalog);
      for (const id of NAV_IDS) {
        const entry = items[id];
        const label =
          entry && typeof entry === "object"
            ? (entry as MessageTree)["label"]
            : undefined;
        expect({
          id,
          label: typeof label === "string" && label.length > 0,
        }).toEqual({ id, label: true });
      }
    });
  }

  test("items key sets are identical across locales", () => {
    const reference = Object.keys(navItems(en)).sort();
    for (const [locale, catalog] of Object.entries(CATALOGS)) {
      expect({ locale, keys: Object.keys(navItems(catalog)).sort() }).toEqual({
        locale,
        keys: reference,
      });
    }
  });

  test("the dead admin.sidebar namespace stays removed", () => {
    for (const [locale, catalog] of Object.entries(CATALOGS)) {
      const admin = catalog["admin"];
      const dead =
        admin && typeof admin === "object"
          ? "sidebar" in (admin as MessageTree)
          : false;
      expect({ locale, hasDeadNamespace: dead }).toEqual({
        locale,
        hasDeadNamespace: false,
      });
    }
  });
});
