#!/usr/bin/env node

/**
 * check-i18n.js — Validate locale JSON files against en.json (source of truth).
 *
 * Checks:
 *   1. Every key in en.json exists in each locale file.
 *   2. No locale file has keys not present in en.json (typos/extras).
 *   3. Every {{placeholder}} in each English value appears (unchanged) in the
 *      translated value.
 *   4. (WARN only) Values in locale files that are byte-identical to en.json,
 *      indicating possible untranslated leftovers.
 *
 * Usage:
 *   node scripts/check-i18n.js
 *   docker compose exec client npm run check:i18n
 *
 * Exits 0 on success, 1 if any locale has a missing/extra/placeholder mismatch.
 */

import { readFileSync, readdirSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

// ── Paths ─────────────────────────────────────────────────────────────
const __dirname = dirname(fileURLToPath(import.meta.url));
const I18N_DIR = resolve(__dirname, "..", "..", "projects", "uwuchat", "client", "i18n");
const SOURCE_FILE = "en.json";

// ── Helpers ───────────────────────────────────────────────────────────

/** Recursively collect dotted key paths from a plain object. */
function collectKeys(obj, prefix = "") {
  /** @type {string[]} */
  const keys = [];
  for (const [k, v] of Object.entries(obj)) {
    const full = prefix ? `${prefix}.${k}` : k;
    keys.push(full);
    if (v && typeof v === "object" && !Array.isArray(v)) {
      keys.push(...collectKeys(v, full));
    }
  }
  return keys;
}

/** Extract all {{placeholder}} tokens from a string. */
function extractPlaceholders(str) {
  if (typeof str !== "string") return [];
  const re = /\{\{(\w+)\}\}/g;
  const tokens = [];
  let m;
  while ((m = re.exec(str)) !== null) {
    tokens.push(m[0]);
  }
  return tokens;
}

/**
 * Walk a dotted path like "a.b.c" into a nested object and return the
 * leaf value, or undefined if any segment is missing.
 *
 * @param {Record<string, unknown>} obj
 * @param {string} path
 * @returns {unknown}
 */
function getValueAt(obj, path) {
  const parts = path.split(".");
  let cur = obj;
  for (const p of parts) {
    if (cur == null || typeof cur !== "object") return undefined;
    cur = cur[p];
  }
  return cur;
}

// ── Main ──────────────────────────────────────────────────────────────

function main() {
  const sourcePath = resolve(I18N_DIR, SOURCE_FILE);
  let sourceData;
  try {
    sourceData = JSON.parse(readFileSync(sourcePath, "utf-8"));
  } catch {
    console.error(`ERROR: cannot read source file ${sourcePath}`);
    process.exit(1);
  }

  const sourceKeys = collectKeys(sourceData);
  const sourceKeySet = new Set(sourceKeys);

  // Build a map of source key → English value for placeholder checking.
  /** @type {Map<string, string>} */
  const sourceValueMap = new Map();
  for (const key of sourceKeys) {
    const val = getValueAt(sourceData, key);
    if (typeof val === "string") {
      sourceValueMap.set(key, val);
    }
  }

  const localeFiles = readdirSync(I18N_DIR).filter(
    (f) => f.endsWith(".json") && f !== SOURCE_FILE,
  );

  if (localeFiles.length === 0) {
    console.log("No locale files found to check.");
    process.exit(0);
  }

  let exitCode = 0;
  const totalErrors = { missing: 0, extra: 0, placeholder: 0 };

  for (const file of localeFiles) {
    const filePath = resolve(I18N_DIR, file);
    /** @type {Record<string, unknown>} */
    let localeData;
    try {
      localeData = JSON.parse(readFileSync(filePath, "utf-8"));
    } catch (err) {
      console.error(`ERROR: cannot parse ${file}: ${err.message}`);
      exitCode = 1;
      continue;
    }

    const localeKeys = collectKeys(localeData);
    const localeKeySet = new Set(localeKeys);

    // Missing keys (in source but not locale).
    const missing = sourceKeys.filter((k) => !localeKeySet.has(k));
    // Extra keys (in locale but not source).
    const extra = localeKeys.filter((k) => !sourceKeySet.has(k));

    // Placeholder mismatches.
    /** @type {Array<{key: string, locale: string}>} */
    const placeholderErrors = [];
    for (const key of sourceKeys) {
      const sourceVal = sourceValueMap.get(key);
      if (!sourceVal) continue;
      const sourceTokens = extractPlaceholders(sourceVal);
      if (sourceTokens.length === 0) continue;

      const localeVal = getValueAt(localeData, key);
      if (typeof localeVal !== "string") {
        placeholderErrors.push({
          key,
          locale: `expected string but got ${typeof localeVal}`,
        });
        continue;
      }

      const localeTokens = extractPlaceholders(localeVal);
      const missingTokens = sourceTokens.filter(
        (t) => !localeTokens.includes(t),
      );
      if (missingTokens.length > 0) {
        placeholderErrors.push({
          key,
          locale: `missing placeholders: ${missingTokens.join(", ")}`,
        });
      }
      const extraTokens = localeTokens.filter(
        (t) => !sourceTokens.includes(t),
      );
      if (extraTokens.length > 0) {
        placeholderErrors.push({
          key,
          locale: `extra/unexpected placeholders: ${extraTokens.join(", ")}`,
        });
      }
    }

    // Check 4: Identical-to-English values (warn-only).
    /** @type {Array<{key: string, enValue: string}>} */
    const identicalValues = [];
    for (const key of sourceKeys) {
      const enVal = sourceValueMap.get(key);
      if (!enVal) continue;
      const locVal = getValueAt(localeData, key);
      if (typeof locVal === "string" && locVal === enVal) {
        identicalValues.push({ key, enValue: enVal });
      }
    }

    const hasErrors =
      missing.length > 0 || extra.length > 0 || placeholderErrors.length > 0;

    if (!hasErrors && identicalValues.length === 0) {
      console.log(
        `PASS  ${file} — all ${sourceKeys.length} keys match, no placeholder issues.`,
      );
      continue;
    }

    if (hasErrors) {
      exitCode = 1;
      console.log(`\nFAIL  ${file}`);

      if (missing.length > 0) {
        console.log(`  ${missing.length} missing key(s):`);
        for (const k of missing) {
          console.log(`    - ${k}`);
        }
        totalErrors.missing += missing.length;
      }

      if (extra.length > 0) {
        console.log(`  ${extra.length} extra key(s) not in en.json:`);
        for (const k of extra) {
          console.log(`    - ${k}`);
        }
        totalErrors.extra += extra.length;
      }

      if (placeholderErrors.length > 0) {
        console.log(`  ${placeholderErrors.length} placeholder mismatch(es):`);
        for (const e of placeholderErrors) {
          console.log(`    - ${e.key}: ${e.locale}`);
        }
        totalErrors.placeholder += placeholderErrors.length;
      }
    }

    if (identicalValues.length > 0) {
      // Print group header only if we haven't already printed a FAIL header
      // for this file (the block above). WARN header always uses "WARN".
      console.log(
        `WARN  ${file} — ${identicalValues.length} value(s) identical to en.json (verify these are real translations, not leftovers):`,
      );
      for (const iv of identicalValues) {
        console.log(`    - ${iv.key}: ${JSON.stringify(iv.enValue)}`);
      }
    }
  }

  console.log(
    `\n---\nSummary: ${totalErrors.missing} missing, ${totalErrors.extra} extra, ${totalErrors.placeholder} placeholder issues across ${localeFiles.length} locale(s).`,
  );

  process.exit(exitCode);
}

main();
