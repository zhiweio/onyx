import {
  collectCustomScenarioDomains,
  isBuiltinScenarioDomain,
  isUncategorizedDomain,
  normalizeScenarioDomain,
  renderPlaybookSection,
  renderScenarioProtocolPreview,
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

describe("scenario protocol preview", () => {
  it("matches Craft SCENARIO.md playbook sections", () => {
    const extraId = "skill-patent";
    const preview = renderScenarioProtocolPreview({
      name: "Due diligence",
      description: "Tax pack",
      skillNames: ["Alpha skill"],
      reportTemplate: "compliance_risk",
      skillLabels: { [extraId]: "Patent search" },
      rules: {
        domain: "tax",
        objective: "Cite the filing.",
        required_inputs: ["entity"],
        conditional: [
          {
            if: { query_contains_any: ["专利", "patent"] },
            add_skill_ids: [extraId],
          },
        ],
      },
    });
    expect(preview).toContain("Use only these skills unless the user asks otherwise:");
    expect(preview).toContain("## Domain");
    expect(preview).toContain("tax");
    expect(preview).toContain("## Extra skills");
    expect(preview).toContain(
      "If the query contains `专利` or `patent`, add `Patent search`"
    );
    expect(preview).toContain("Preferred report template: `compliance_risk`");
    expect(preview).not.toContain("## Skills");
  });

  it("renders intent-only extra skills", () => {
    const lines = renderPlaybookSection(
      {
        conditional: [
          { if: { intent: "enforcement" }, add_skill_slugs: ["legal-review"] },
        ],
      },
      { "legal-review": "Legal review" }
    );
    expect(lines.join("\n")).toContain(
      "If the intent is `enforcement`, add `Legal review`"
    );
  });
});
