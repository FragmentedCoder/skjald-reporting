// Builds src/lib/styles/tokens.css from docs/brand/tokens.json, the brand's one source.
// Run `npm run tokens` after changing tokens.json; a test fails if the two drift apart.
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

export const TOKENS_JSON = fileURLToPath(new URL("../../docs/brand/tokens.json", import.meta.url));
export const TOKENS_CSS = fileURLToPath(new URL("../src/lib/styles/tokens.css", import.meta.url));

/** @param {any} tokens */
export function buildCss(tokens) {
  const light = [];
  const dark = [];
  const fixed = [];
  for (const { name, value } of tokens.color.tokens) {
    if (typeof value === "string") {
      fixed.push(`  --${name}: ${value};`);
    } else {
      light.push(`  --${name}: ${value.light};`);
      dark.push(`  --${name}: ${value.dark};`);
    }
  }
  for (const { name, value } of [...tokens.spacing.tokens, ...tokens.radius.tokens]) {
    fixed.push(`  --${name}: ${value};`);
  }
  for (const [name, stack] of Object.entries(tokens.type.families)) {
    fixed.push(`  --font-${name}: ${stack};`);
  }
  for (const group of tokens.type.groups) {
    for (const style of group.styles) {
      fixed.push(`  --type-${style.name}: ${style.fontWeight} ${style.fontSize}/${style.lineHeight} var(--font-${group.family});`);
      if (style.letterSpacing) fixed.push(`  --type-${style.name}-tracking: ${style.letterSpacing};`);
    }
  }
  return [
    "/* Generated from docs/brand/tokens.json by scripts/tokens.mjs. Do not edit by hand. */",
    ":root {",
    "  color-scheme: light;",
    ...fixed,
    ...light,
    "}",
    "",
    "/* Dark follows the system unless the user picked a theme (data-theme on <html>). */",
    "@media (prefers-color-scheme: dark) {",
    '  :root:not([data-theme="light"]) {',
    "    color-scheme: dark;",
    ...dark.map((line) => `  ${line}`),
    "  }",
    "}",
    "",
    ':root[data-theme="dark"] {',
    "  color-scheme: dark;",
    ...dark,
    "}",
    "",
  ].join("\n");
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  writeFileSync(TOKENS_CSS, buildCss(JSON.parse(readFileSync(TOKENS_JSON, "utf8"))));
  console.log(`Wrote ${TOKENS_CSS}`);
}
