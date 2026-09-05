import {
  placeholderToken,
  suggestReportTemplateSlug,
} from "@/lib/report-templates/types";

describe("suggestReportTemplateSlug", () => {
  it("turns a display name into a slug", () => {
    expect(suggestReportTemplateSlug("Compliance Risk")).toBe(
      "compliance_risk",
    );
    expect(suggestReportTemplateSlug("  CMC-Quality  ")).toBe("cmc_quality");
  });

  it("returns empty when the name has no latin letters", () => {
    expect(suggestReportTemplateSlug("合规风险")).toBe("");
  });
});

describe("placeholderToken", () => {
  it("wraps the name in braces", () => {
    expect(
      placeholderToken({
        name: "entity_name",
        kind: "text",
        required: true,
        description: "",
        example: "",
      }),
    ).toBe("{{entity_name}}");
  });
});
