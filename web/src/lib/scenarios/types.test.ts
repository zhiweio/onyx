import {
  collectCustomScenarioDomains,
  isBuiltinScenarioDomain,
  isUncategorizedDomain,
  normalizeScenarioDomain,
  scenarioDomain,
  type Scenario,
} from "@/lib/scenarios/types";

function pack(domain: string): Scenario {
  return {
    id: domain,
    name: domain,
    description: "",
    author_user_id: "owner",
    public_permission: null,
    rules: { domain },
    report_template: null,
    skill_ids: [],
    skills: [],
    access_level: "OWNER",
    shared_user_ids: [],
    shared_group_ids: [],
  };
}

describe("scenario domain helpers", () => {
  it("keeps built-in domains and treats blank as custom", () => {
    expect(isBuiltinScenarioDomain("tax")).toBe(true);
    expect(isBuiltinScenarioDomain("新能源")).toBe(false);
    expect(isUncategorizedDomain("custom")).toBe(true);
    expect(normalizeScenarioDomain("  新能源  ")).toBe("新能源");
    expect(normalizeScenarioDomain("")).toBe("custom");
    expect(scenarioDomain(pack("biomed"))).toBe("biomed");
  });

  it("collects unique custom domain names", () => {
    expect(
      collectCustomScenarioDomains([
        pack("tax"),
        pack("新能源"),
        pack("custom"),
        pack("新能源"),
        pack("制造业"),
      ])
    ).toEqual(["制造业", "新能源"]);
  });
});
