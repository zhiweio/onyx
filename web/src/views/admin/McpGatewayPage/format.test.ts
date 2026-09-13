import { formatBytes, formatLatency } from "./format";

describe("formatBytes", () => {
  it("keeps the number and unit on one line", () => {
    expect(formatBytes(371)).toBe("371\u00A0B");
    expect(formatBytes(5324)).toBe("5.2\u00A0KB");
  });
});

describe("formatLatency", () => {
  it("uses milliseconds below one second", () => {
    expect(formatLatency(508)).toBe("508\u00A0ms");
  });

  it("uses seconds for longer calls", () => {
    expect(formatLatency(2508)).toBe("2.5\u00A0s");
    expect(formatLatency(20377)).toBe("20\u00A0s");
  });
});
