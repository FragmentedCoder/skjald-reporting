import svelte from "eslint-plugin-svelte";
import tseslint from "@typescript-eslint/eslint-plugin";
import tsParser from "@typescript-eslint/parser";
import svelteParser from "svelte-eslint-parser";

export default [
  {
    files: ["**/*.ts"],
    languageOptions: {
      parser: tsParser,
    },
    plugins: { "@typescript-eslint": tseslint },
    rules: {},
  },
  ...svelte.configs.recommended,
  {
    files: ["**/*.svelte", "**/*.svelte.ts"],
    languageOptions: {
      parser: svelteParser,
      parserOptions: {
        parser: tsParser,
      },
    },
  },
  {
    ignores: [".svelte-kit/", "build/", "node_modules/"],
  },
];
