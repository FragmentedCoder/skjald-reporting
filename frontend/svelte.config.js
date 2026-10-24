import adapter from "@sveltejs/adapter-static";
import { vitePreprocess } from "@sveltejs/vite-plugin-svelte";

// SvelteKit's route announcer (it reads the new page's title to screen readers)
// has an inline style attribute. 'unsafe-hashes' plus this hash allows exactly
// that style and no other. scripts/csp.test.mjs fails if SvelteKit changes it.
export const ANNOUNCER_STYLE_HASH = "sha256-S8qMpvofolR8Mpjy4kQvEm7m1q8clzU4dfDH0AmvZjo=";

/** @type {import('@sveltejs/kit').Config} */
const config = {
  preprocess: vitePreprocess(),
  kit: {
    adapter: adapter({
      fallback: "index.html",
    }),
    // A strict CSP in a <meta> tag; SvelteKit adds the hash of its own inline
    // bootstrap script. No inline styles or scripts of ours, nothing third-party.
    // frame-ancestors can't go in a meta tag; Caddy sends it as a header.
    csp: {
      mode: "hash",
      directives: {
        "default-src": ["self"],
        "script-src": ["self"],
        "style-src": ["self", "unsafe-hashes", ANNOUNCER_STYLE_HASH],
        "img-src": ["self"],
        "font-src": ["self"],
        "connect-src": ["self"],
        "object-src": ["none"],
        "base-uri": ["none"],
        "form-action": ["self"],
      },
    },
  },
};

export default config;
