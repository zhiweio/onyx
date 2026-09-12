import { isoWindowForInclusiveDateRange } from "./dateWindow";

describe("isoWindowForInclusiveDateRange", () => {
  it("covers a late UTC call from a local end-of-day picker", () => {
    const isoWindow = isoWindowForInclusiveDateRange({
      from: new Date(2026, 8, 6),
      to: new Date(2026, 8, 12, 23, 59, 59, 999),
    });

    expect(isoWindow.from).toBe("2026-09-06T00:00:00.000Z");
    expect(isoWindow.to).toBe("2026-09-13T00:00:00.000Z");

    const call = new Date("2026-09-12T19:14:59.000Z");
    expect(
      call >= new Date(isoWindow.from) && call < new Date(isoWindow.to)
    ).toBe(true);
  });
});
