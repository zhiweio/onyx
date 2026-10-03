import { detectTriggerInText } from "@/sections/input/lexical/TriggerMenusPlugin";
import type { TriggerMenuConfig } from "@/sections/input/lexical/types";
import type { PickerSections } from "@/lib/skills/picker";

const sections: PickerSections = {
  commands: [
    {
      kind: "command",
      slug: "compact",
      name: "Compact",
      description: "Compact the conversation",
    },
  ],
  scenarios: [],
  skills: [
    { kind: "skill", slug: "pptx", name: "pptx", description: "Slides" },
  ],
  apps: [],
  files: [],
};

const slash: TriggerMenuConfig = {
  id: "slash",
  triggerChars: ["/"],
  sections,
};
const skills: TriggerMenuConfig = {
  id: "skills",
  triggerChars: ["$", "¥", "￥"],
  sections: {
    commands: [],
    scenarios: [],
    skills: sections.skills,
    apps: [],
    files: [],
  },
};
const configs = [slash, skills];

describe("detectTriggerInText", () => {
  it("detects / at the text start with its query", () => {
    expect(detectTriggerInText(configs, "/doc")).toEqual({
      configId: "slash",
      triggerChar: "/",
      query: "doc",
    });
  });

  it("detects / after whitespace only", () => {
    expect(detectTriggerInText(configs, "hello /do")).toEqual({
      configId: "slash",
      triggerChar: "/",
      query: "do",
    });
    // Mid-word slash is not a trigger.
    expect(detectTriggerInText(configs, "hello/do")).toBeNull();
  });

  it("detects the $ trigger and its aliases", () => {
    for (const char of ["$", "¥", "￥"]) {
      expect(detectTriggerInText(configs, char)).toEqual({
        configId: "skills",
        triggerChar: char,
        query: "",
      });
      expect(detectTriggerInText(configs, `${char}pp`)).toEqual({
        configId: "skills",
        triggerChar: char,
        query: "pp",
      });
    }
  });

  it("returns null without a token", () => {
    expect(detectTriggerInText(configs, "")).toBeNull();
    expect(detectTriggerInText(configs, "plain text")).toBeNull();
  });

  it("prefers the first matching config", () => {
    // "/" only matches the slash config; "$" only the skills config —
    // a shared char would resolve to the earlier config in the list.
    const overlapping: TriggerMenuConfig[] = [
      skills,
      { id: "also-$", triggerChars: ["$"], sections },
    ];
    expect(detectTriggerInText(overlapping, "$x")?.configId).toBe("skills");
  });
});
