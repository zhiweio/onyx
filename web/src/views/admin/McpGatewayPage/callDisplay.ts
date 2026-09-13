export interface ArgumentPreviewPair {
  key: string;
  value: string;
}

type JsonPrimitive = string | number | boolean | null;
interface JsonObject {
  [key: string]: JsonValue;
}
type JsonValue = JsonPrimitive | JsonValue[] | JsonObject;

const PREVIEW_PAIR_RE =
  /['"]([^'"]+)['"]\s*:\s*(?:['"]([^'"]*)['"]|(True|False|None|true|false|null|-?\d+(?:\.\d+)?))/g;

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

function formatScalar(value: JsonValue): string {
  if (value === null) return "null";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

function pairsFromRecord(record: JsonObject): ArgumentPreviewPair[] {
  return Object.entries(record).map(([key, value]) => ({
    key,
    value: formatScalar(value),
  }));
}

function pythonDictToJson(text: string): string {
  return text
    .replace(/\bTrue\b/g, "true")
    .replace(/\bFalse\b/g, "false")
    .replace(/\bNone\b/g, "null")
    .replace(/'/g, '"');
}

function parseJsonText(text: string): JsonValue | undefined {
  try {
    return asJsonValue(JSON.parse(text));
  } catch {
    return undefined;
  }
}

function tryParseRecord(text: string): JsonObject | undefined {
  const candidates = [text, pythonDictToJson(text)];
  for (const candidate of candidates) {
    const parsed = parseJsonText(candidate);
    if (parsed !== undefined && isJsonObject(parsed)) return parsed;
  }
  return undefined;
}

function pairsFromLooseText(text: string): ArgumentPreviewPair[] {
  const pairs: ArgumentPreviewPair[] = [];
  const seen = new Set<string>();
  for (const match of text.matchAll(PREVIEW_PAIR_RE)) {
    const key = match[1];
    if (!key || seen.has(key)) continue;
    seen.add(key);
    const quoted = match[2];
    const literal = match[3];
    pairs.push({
      key,
      value: quoted ?? literal ?? "",
    });
  }
  return pairs;
}

/** Turn a gateway arguments digest into key/value chips for the calls table. */
export function parseArgumentsPreview(
  preview: string | null | undefined
): ArgumentPreviewPair[] {
  const text = preview?.trim() ?? "";
  if (!text) return [];

  const record = tryParseRecord(text);
  if (record) return pairsFromRecord(record);

  return pairsFromLooseText(text);
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

/** Pretty-print a call argument or payload, unfolding nested JSON strings. */
export function formatJsonValue(
  value: Record<string, unknown> | null | undefined
): string {
  const json = asJsonValue(value ?? null) ?? null;
  return JSON.stringify(reviveJsonStrings(json), null, 2);
}
