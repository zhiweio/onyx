import { SOURCE_METADATA_MAP } from "@/lib/sources";
import { ValidSources } from "@/lib/types";

/**
 * Backend-registered document sources that must carry frontend metadata.
 * Mirrors the China workplace platforms + enterprise systems group in
 * backend/onyx/configs/constants.py (DocumentSource). A missing entry makes
 * the indexing status table fall back to the "Not Applicable" placeholder.
 */
const BACKEND_REGISTERED_SOURCES: readonly string[] = [
  "feishu",
  "wecom",
  "dingtalk",
  "wps365",
  "sap_odata",
];

// Sources intentionally without a metadata entry (placeholder itself).
const ALLOWED_MISSING = new Set<string>([ValidSources.NotApplicable]);

describe("SOURCE_METADATA_MAP covers backend sources", () => {
  it.each(BACKEND_REGISTERED_SOURCES)(
    "has real metadata for backend source %s (no 'Not Applicable' fallback)",
    (source) => {
      const metadata = SOURCE_METADATA_MAP[source as ValidSources];
      expect(metadata).toBeDefined();
      expect(metadata.displayName).not.toBe("Not Applicable");
      expect(metadata.icon).toBeDefined();
    }
  );

  it("covers every ValidSources member except the documented allowlist", () => {
    const missing = Object.values(ValidSources).filter(
      (source) =>
        !ALLOWED_MISSING.has(source) && !(source in SOURCE_METADATA_MAP)
    );
    expect(missing).toEqual([]);
  });
});
