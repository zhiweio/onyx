import { clampPage, pageCount, slicePage } from "@/lib/browse/page";

describe("browse page helpers", () => {
  it("counts pages and never returns zero", () => {
    expect(pageCount(0)).toBe(1);
    expect(pageCount(12)).toBe(1);
    expect(pageCount(13)).toBe(2);
  });

  it("clamps the current page into range", () => {
    expect(clampPage(0, 24)).toBe(1);
    expect(clampPage(9, 24)).toBe(2);
  });

  it("slices the requested page", () => {
    const items = Array.from({ length: 13 }, (_, index) => index);
    expect(slicePage(items, 1)).toEqual(items.slice(0, 12));
    expect(slicePage(items, 2)).toEqual([12]);
    expect(slicePage(items, 9)).toEqual([12]);
  });
});
