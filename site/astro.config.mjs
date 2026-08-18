// @ts-check
import { defineConfig } from 'astro/config';

// https://astro.build/config
export default defineConfig({
  // GitHub Pages serves this project at github.com/ganbaramen/drawrydb, so
  // the site lives under /drawrydb/, not at the domain root.
  site: 'https://ganbaramen.github.io',
  base: '/drawrydb',

  i18n: {
    // Only `ja` routes are built for now (Phase 1) — `en` is declared here
    // so adding it later (Phase 3) is a new directory, not a routing
    // rewrite. defaultLocale still governs the redirect from `/`.
    defaultLocale: 'ja',
    locales: ['ja', 'en'],
    routing: {
      prefixDefaultLocale: true,
    },
  },
});
