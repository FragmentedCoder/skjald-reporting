import { sveltekit } from "@sveltejs/kit/vite";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [sveltekit()],
  build: {
    // Never inline assets as data: URLs, so the CSP can stay at 'self'.
    assetsInlineLimit: 0,
  },
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
  test: {
    include: ["src/**/*.test.ts", "scripts/**/*.test.mjs"],
  },
});
