import { readFileSync } from "node:fs";
import { expect, test } from "vitest";
import { buildCss, TOKENS_CSS, TOKENS_JSON } from "./tokens.mjs";

test("tokens.css matches docs/brand/tokens.json (run `npm run tokens` if not)", () => {
  const expected = buildCss(JSON.parse(readFileSync(TOKENS_JSON, "utf8")));
  expect(readFileSync(TOKENS_CSS, "utf8")).toBe(expected);
});
