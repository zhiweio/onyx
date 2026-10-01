/**
 * Bounded TypeScript gate: run tsgo, fail only on errors that are NOT in the
 * checked-in baseline (`scripts/types-baseline.txt`).
 *
 * Why: the repo carries ~250 pre-existing type errors that were invisible
 * for a long time because the old typecheck never completed (see
 * src/i18n/types.d.ts for why). Making the gate green immediately while
 * preventing NEW debt:
 *   - new error → exit 1, printed with its file/line
 *   - baseline entry no longer reproduces → hint to shrink the baseline
 *   - `node scripts/types-check.mjs --update-baseline` rewrites the baseline
 *
 * Burn the baseline down file-by-file; the goal is an empty file.
 */
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const WEB_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const BASELINE_PATH = join(WEB_ROOT, "scripts/types-baseline.txt");

const update = process.argv.includes("--update-baseline");

const tsc = spawnSync(
  process.execPath,
  [
    join(WEB_ROOT, "node_modules/typescript-7/bin/tsc"),
    "--noEmit",
    "--project",
    join(WEB_ROOT, "tsconfig.types.json"),
  ],
  { cwd: WEB_ROOT, encoding: "utf8", maxBuffer: 64 * 1024 * 1024 }
);

// tsc exits 1 on any type error; anything else (crash, missing binary) is a
// real failure of the check itself.
if (tsc.status !== 0 && tsc.status !== 1) {
  console.error(tsc.stderr || `tsc exited with ${tsc.status}`);
  process.exit(2);
}

const current = (tsc.stdout || "")
  .split("\n")
  .filter((line) => /^\S+.*error TS\d+:/.test(line))
  .sort();

const baseline = new Set(
  (() => {
    try {
      return readFileSync(BASELINE_PATH, "utf8")
        .split("\n")
        .map((line) => line.trim())
        .filter((line) => line.length > 0 && !line.startsWith("#"));
    } catch {
      return [];
    }
  })()
);

const fresh = current.filter((line) => !baseline.has(line));
const fixed = [...baseline].filter((line) => !current.includes(line));

if (update) {
  const header = [
    "# Pre-existing tsc errors grandfathered by scripts/types-check.mjs.",
    "# Shrink by fixing code, then: bun run types:baseline-update",
    `# ${current.length} entries.`,
    "",
  ].join("\n");
  writeFileSync(BASELINE_PATH, header + current.join("\n") + "\n");
  console.log(
    `baseline updated: ${current.length} entries (${fixed.length} removed)`
  );
  process.exit(0);
}

if (fresh.length > 0) {
  console.error(`types:check found ${fresh.length} NEW type error(s):`);
  for (const line of fresh) console.error(`  ${line}`);
  console.error(
    "Fix them, or acknowledge explicitly with: bun run types:baseline-update"
  );
  process.exit(1);
}

if (fixed.length > 0) {
  console.log(
    `${fixed.length} baseline error(s) no longer reproduce — shrink the baseline with: bun run types:baseline-update`
  );
}

console.log(`types:check ok (${current.length} baseline errors, 0 new)`);
