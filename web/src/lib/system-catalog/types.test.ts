import {
  categoryMessageKey,
  categoryTagColor,
  collectCatalogCategories,
  filterCatalogItems,
  groupCatalogItemsByCategory,
  isDocxCatalogTemplate,
  isForkOutdated,
  isSystemSkillItem,
  publishStatusMessageKey,
  publishStatusTagColor,
  type CatalogItem,
  type SystemReportTemplateItem,
} from "@/lib/system-catalog/types";

function item(overrides: Partial<CatalogItem> = {}): CatalogItem {
  return {
    id: "entry-1",
    slug: "docx",
    name: "Word document",
    description: "Create and edit Word files",
    category: "DOCUMENT",
    tags: ["docx", "word"],
    publish_status: "PUBLISHED",
    version: 1,
    changelog: "",
    origin: "BUILTIN",
    published_at: "2026-09-01T00:00:00Z",
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    ...overrides,
  };
}

describe("filterCatalogItems", () => {
  const docx = item();
  const tax = item({
    id: "entry-2",
    slug: "tax-compliance",
    name: "Tax compliance",
    description: "Assess compliance risk",
    category: "TAX",
    tags: ["compliance"],
  });
  const draft = item({
    id: "entry-3",
    slug: "draft-one",
    name: "Draft entry",
    description: "Not published yet",
    category: "GENERAL",
    tags: [],
    publish_status: "DRAFT",
  });
  const items = [docx, tax, draft];

  it("returns everything when no filters are set", () => {
    expect(filterCatalogItems(items, {})).toEqual(items);
  });

  it("matches name, slug, description and tags", () => {
    expect(filterCatalogItems(items, { query: "Word" })).toEqual([docx]);
    expect(filterCatalogItems(items, { query: "tax-comp" })).toEqual([tax]);
    expect(filterCatalogItems(items, { query: "Assess" })).toEqual([tax]);
    expect(filterCatalogItems(items, { query: "docx" })).toEqual([docx]);
  });

  it("matches a substring within one field, not tokens across fields", () => {
    // "Tax compliance" is the name and "Assess compliance risk" the
    // description; neither field holds the whole phrase.
    expect(filterCatalogItems(items, { query: "compliance risk" })).toEqual([
      tax,
    ]);
    expect(filterCatalogItems(items, { query: "Tax compliance risk" })).toEqual(
      [],
    );
  });

  it("ignores case and surrounding whitespace", () => {
    expect(filterCatalogItems(items, { query: "  WORD  " })).toEqual([docx]);
  });

  it("filters by category, treating 'all' as no filter", () => {
    expect(filterCatalogItems(items, { category: "TAX" })).toEqual([tax]);
    expect(filterCatalogItems(items, { category: "all" })).toEqual(items);
  });

  it("filters by publish status", () => {
    expect(filterCatalogItems(items, { statuses: ["DRAFT"] })).toEqual([draft]);
  });

  it("applies query and category together", () => {
    expect(
      filterCatalogItems(items, { query: "compliance", category: "DOCUMENT" }),
    ).toEqual([]);
    expect(
      filterCatalogItems(items, { query: "word", category: "DOCUMENT" }),
    ).toEqual([docx]);
  });
});

describe("collectCatalogCategories", () => {
  it("returns only categories present, in display order", () => {
    const items = [
      item({ category: "TAX" }),
      item({ id: "b", category: "DOCUMENT" }),
      item({ id: "c", category: "TAX" }),
    ];
    expect(collectCatalogCategories(items)).toEqual(["DOCUMENT", "TAX"]);
  });

  it("returns nothing for an empty list", () => {
    expect(collectCatalogCategories([])).toEqual([]);
  });
});

describe("groupCatalogItemsByCategory", () => {
  it("keeps display order and drops empty categories", () => {
    const items = [
      item({ id: "tax", category: "TAX" }),
      item({ id: "doc", category: "DOCUMENT" }),
      item({ id: "bio", category: "BIOMED" }),
    ];
    expect(
      groupCatalogItemsByCategory(items).map((group) => group.category),
    ).toEqual(["DOCUMENT", "TAX", "BIOMED"]);
  });
});

describe("isDocxCatalogTemplate", () => {
  it("is true only for Word catalog templates", () => {
    const word: SystemReportTemplateItem = {
      ...item(),
      body: "# Guide",
      kind: "DOCX",
      asset_filename: "close.docx",
    };
    expect(isDocxCatalogTemplate(word)).toBe(true);
    expect(isDocxCatalogTemplate(item())).toBe(false);
  });
});

describe("isForkOutdated", () => {
  it("is true only when the fork trails the upstream version", () => {
    expect(isForkOutdated(1, 2)).toBe(true);
    expect(isForkOutdated(2, 2)).toBe(false);
    expect(isForkOutdated(3, 2)).toBe(false);
  });

  it("is false when either version is unknown", () => {
    expect(isForkOutdated(null, 2)).toBe(false);
    expect(isForkOutdated(1, null)).toBe(false);
    expect(isForkOutdated(undefined, undefined)).toBe(false);
  });
});

describe("message key and colour helpers", () => {
  it("maps every category to a distinct message key", () => {
    const keys = (
      ["all", "TAX", "BIOMED", "OFFICE", "DOCUMENT", "GENERAL"] as const
    ).map(categoryMessageKey);
    expect(new Set(keys).size).toBe(keys.length);
    expect(categoryMessageKey("TAX")).toBe("category.tax.label");
  });

  it("maps every publish status to a distinct message key", () => {
    const keys = (["DRAFT", "PUBLISHED", "ARCHIVED"] as const).map(
      publishStatusMessageKey,
    );
    expect(new Set(keys).size).toBe(keys.length);
    expect(publishStatusMessageKey("PUBLISHED")).toBe("status.published.label");
  });

  it("recognizes skill listings by the built-in flag", () => {
    expect(
      isSystemSkillItem({
        ...item(),
        is_built_in_content: true,
        instructions_markdown: null,
      })
    ).toBe(true);
    expect(isSystemSkillItem(item())).toBe(false);
  });

  it("only returns colours the design system supports", () => {
    const supported = ["blue", "purple", "green", "amber", "gray"];
    for (const category of [
      "TAX",
      "BIOMED",
      "OFFICE",
      "DOCUMENT",
      "GENERAL",
    ] as const) {
      expect(supported).toContain(categoryTagColor(category));
    }
    for (const status of ["DRAFT", "PUBLISHED", "ARCHIVED"] as const) {
      expect(supported).toContain(publishStatusTagColor(status));
    }
  });
});
