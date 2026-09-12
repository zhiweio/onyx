import {
  allowedComposerStop,
  toComposerThoughtLevel,
} from "@/sections/input/thoughtLevel";

describe("toComposerThoughtLevel", () => {
  it("maps High onto Max", () => {
    expect(toComposerThoughtLevel("high")).toBe("xhigh");
  });

  it("keeps composer stops", () => {
    expect(toComposerThoughtLevel("off")).toBe("off");
    expect(toComposerThoughtLevel("low")).toBe("low");
    expect(toComposerThoughtLevel("medium")).toBe("medium");
    expect(toComposerThoughtLevel("xhigh")).toBe("xhigh");
  });
});

describe("allowedComposerStop", () => {
  it("treats a High admin cap as Max", () => {
    expect(allowedComposerStop("high")).toBe(allowedComposerStop("xhigh"));
  });

  it("keeps Medium below Max", () => {
    expect(allowedComposerStop("medium")).toBeLessThan(
      allowedComposerStop("xhigh")
    );
  });
});
