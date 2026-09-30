type JsonPrimitive = string | number | boolean | null;
interface JsonObject {
  [key: string]: JsonValue;
}
type JsonValue = JsonPrimitive | JsonValue[] | JsonObject;

function isJsonObject(value: JsonValue): value is JsonObject {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function asJsonValue(value: unknown): JsonValue | undefined {
  if (value === null) return null;
  if (
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  ) {
    return value;
  }
  if (Array.isArray(value)) {
    const items: JsonValue[] = [];
    for (const item of value) {
      const next = asJsonValue(item);
      if (next === undefined) return undefined;
      items.push(next);
    }
    return items;
  }
  if (typeof value === "object") {
    const record: JsonObject = {};
    for (const [key, item] of Object.entries(value)) {
      const next = asJsonValue(item);
      if (next === undefined) return undefined;
      record[key] = next;
    }
    return record;
  }
  return undefined;
}

function parseJsonText(text: string): JsonValue | undefined {
  try {
    return asJsonValue(JSON.parse(text));
  } catch {
    return undefined;
  }
}

function parseJsonContainer(text: string): JsonValue | undefined {
  const trimmed = text.trim();
  if (trimmed.length < 2) return undefined;
  const first = trimmed[0];
  const last = trimmed[trimmed.length - 1];
  if (!((first === "{" && last === "}") || (first === "[" && last === "]"))) {
    return undefined;
  }
  return parseJsonText(trimmed);
}

function reviveJsonStrings(value: JsonValue, depth = 0): JsonValue {
  if (depth > 6) return value;
  if (typeof value === "string") {
    const nested = parseJsonContainer(value);
    return nested === undefined ? value : reviveJsonStrings(nested, depth + 1);
  }
  if (Array.isArray(value)) {
    return value.map((item) => reviveJsonStrings(item, depth + 1));
  }
  if (isJsonObject(value)) {
    const next: JsonObject = {};
    for (const [key, item] of Object.entries(value)) {
      next[key] = reviveJsonStrings(item, depth + 1);
    }
    return next;
  }
  return value;
}

/** Pretty-print a JSON payload, unfolding nested JSON strings. */
export function formatJsonValue(
  value: Record<string, unknown> | null | undefined
): string {
  const json = asJsonValue(value ?? null) ?? null;
  return JSON.stringify(reviveJsonStrings(json), null, 2);
}
