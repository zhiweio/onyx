import { placeholdersToSchema } from "@/sections/reportTemplates/placeholdersToSchema";

describe("placeholdersToSchema", () => {
  it("maps Word placeholders onto Schema Builder fields", () => {
    const schema = placeholdersToSchema([
      {
        name: "company",
        kind: "text",
        required: true,
        description: "Company name",
        example: "Acme",
      },
      {
        name: "revenue",
        kind: "number",
        required: false,
        description: "",
        example: "100",
      },
      {
        name: "rows",
        kind: "table",
        required: false,
        description: "Line items",
        example: "",
      },
    ]);

    expect(schema.properties).toEqual([
      {
        id: "company",
        key: "company",
        type: "string",
        description: "Company name",
        items: undefined,
      },
      {
        id: "revenue",
        key: "revenue",
        type: "number",
        description: "100",
        items: undefined,
      },
      {
        id: "rows",
        key: "rows",
        type: "array",
        description: "Line items",
        items: { type: "string" },
      },
    ]);
  });
});
