import {
  CATALOG_TAG_MAX,
  CATALOG_TAGS_MAX_COUNT,
  canAcceptCatalogTag,
  normalizeCatalogTag,
} from "@/lib/system-catalog/limits";

describe("normalizeCatalogTag", () => {
  it("trims and lowercases tags", () => {
    expect(normalizeCatalogTag(" Route ")).toBe("route");
  });
});

describe("canAcceptCatalogTag", () => {
  it("rejects empty, duplicate, over-long, and over-count tags", () => {
    expect(canAcceptCatalogTag("", [])).toBe(false);
    expect(canAcceptCatalogTag("route", ["route"])).toBe(false);
    expect(canAcceptCatalogTag("x".repeat(CATALOG_TAG_MAX + 1), [])).toBe(
      false
    );
    expect(
      canAcceptCatalogTag(
        "next",
        Array.from({ length: CATALOG_TAGS_MAX_COUNT }, (_, index) => `t${index}`)
      )
    ).toBe(false);
  });

  it("accepts a new tag within the caps", () => {
    expect(canAcceptCatalogTag("chart", ["graphic"])).toBe(true);
  });
});
