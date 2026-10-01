/**
 * Runtime key-parity check for the message catalogs — the fast replacement
 * for the compile-time check that used to live in messages/keyParity.ts.
 *
 * Why: typing nine ~550KB catalogs as TS literal key-trees (plus the
 * bidirectional subtype checks) bloated `tsc`/`tsgo` to multi-tens-of-GB RSS
 * and CPU saturation on every types:check run. The English catalog alone
 * stays in the type graph (next-intl `Messages` autocomplete); full parity
 * between locales is enforced here in ~50ms.
 *
 * Exit 1 with a per-locale diff when any locale misses or adds keys vs
 * en.json.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const MESSAGES_DIR = join(
  dirname(fileURLToPath(import.meta.url)),
  "../src/i18n/messages"
);
const LOCALES = ["ar", "de", "es", "fr", "ja", "ko", "pt", "zh"];

/** Sorted dotted paths of every leaf/non-leaf key in the tree. */
function keyPaths(tree, prefix = "") {
  const paths = [];
  for (const [key, value] of Object.entries(tree)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (value && typeof value === "object") {
      paths.push(path, ...keyPaths(value, path));
    } else {
      paths.push(path);
    }
  }
  return paths;
}

const english = JSON.parse(readFileSync(join(MESSAGES_DIR, "en.json"), "utf8"));
const englishKeys = new Set(keyPaths(english));

let failed = false;
for (const locale of LOCALES) {
  const catalog = JSON.parse(
    readFileSync(join(MESSAGES_DIR, `${locale}.json`), "utf8")
  );
  const localeKeys = new Set(keyPaths(catalog));
  const missing = [...englishKeys].filter((path) => !localeKeys.has(path));
  const extra = [...localeKeys].filter((path) => !englishKeys.has(path));
  if (missing.length === 0 && extra.length === 0) continue;
  failed = true;
  for (const path of missing) console.error(`${locale}: missing ${path}`);
  for (const path of extra) console.error(`${locale}: extra ${path}`);
}

if (failed) {
  console.error(
    "i18n key parity failed — sync the locale catalogs with en.json."
  );
  process.exit(1);
}
console.log(`i18n key parity ok (${LOCALES.length} locales vs en.json)`);
