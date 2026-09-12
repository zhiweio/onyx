import type { PlaceholderSpec } from "@/lib/report-templates/types";
import type {
  SchemaBuilderProperty,
  SchemaBuilderSchema,
} from "@/sections/extend/schema-builder";

function propertyType(
  kind: PlaceholderSpec["kind"]
): SchemaBuilderProperty["type"] {
  if (kind === "number") return "number";
  if (kind === "table") return "array";
  return "string";
}

export function placeholdersToSchema(
  placeholders: PlaceholderSpec[]
): SchemaBuilderSchema {
  return {
    properties: placeholders.map((placeholder) => ({
      id: placeholder.name,
      key: placeholder.name,
      type: propertyType(placeholder.kind),
      description: placeholder.description || placeholder.example || "",
      items:
        placeholder.kind === "table" ? { type: "string" as const } : undefined,
    })),
  };
}
