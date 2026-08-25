## Development

When starting the dev server, use background mode:

```
astro dev --background
```

Manage the background server with `astro dev stop`, `astro dev status`, and `astro dev logs`.

## Documentation

Full documentation: https://docs.astro.build

Consult these guides before working on related tasks:

- [Adding pages, dynamic routes, or middleware](https://docs.astro.build/en/guides/routing/)
- [Working with Astro components](https://docs.astro.build/en/basics/astro-components/)
- [Using React, Vue, Svelte, or other framework components](https://docs.astro.build/en/guides/framework-components/)
- [Adding or managing content](https://docs.astro.build/en/guides/content-collections/)
- [Adding styles or using Tailwind](https://docs.astro.build/en/guides/styling/)
- [Supporting multiple languages](https://docs.astro.build/en/guides/internationalization/)

## UI layer: Fulldev UI (adopted 2026-08-25)

The site's components come from [Fulldev UI](https://ui.full.dev), a
shadcn-format registry of **Astro** components (no React anywhere). Docs have
a Markdown twin: append `.md` to any page URL, and `/index.md` is the agent
entry point.

Installed as *source files* under `src/components/ui/`, so they are ours to
edit — but the shadcn model is that you retheme through tokens, not by editing
component classes. Add one with:

```sh
npx shadcn@latest add @fulldev/<name>
```

`components.json` maps the `@fulldev` namespace and points the CLI at
`src/styles/global.css`; `tsconfig.json`'s `@/*` path is what makes installed
files' imports resolve.

### Theming contract

`src/styles/global.css` is the only place colors are defined. The site's
palette predates Fulldev and was **kept unchanged** — only the token *names*
moved to shadcn's vocabulary (`--bg` → `--background`, `--accent` →
`--primary`, and so on; the mapping is written out in a comment there).

Two things there are not stock and will be clobbered by a careless
`@fulldev/init --overwrite`:

- **`--link`.** shadcn has no link token; its components reuse `--primary`.
  Here links are navy and `--primary` is the purple, which is reserved for
  attention (pending badges, the next-live card). Body-copy links get it via
  `main a:not([class])`, which deliberately skips component-owned anchors
  (Button, Item, Badge) since those set their own color.
- **The `dark` variant.** Stock Fulldev ships `@custom-variant dark
  (&:is(.dark *))`. This site has *three* theme states (OS default / explicit
  light / explicit dark, keyed on `data-theme` — see Layout.astro's head
  script), so the variant is redeclared in block form against both
  `[data-theme="dark"]` and `prefers-color-scheme`. Without that, `dark:`
  utilities inside the installed components would never fire.

### Local components

`src/components/` holds the compositions built on top: `EventCard` (every
event-ish list row, on Fulldev's `Item`), `MetaTable`/`MetaRow` (the detail
pages' label/value tables), `PageHeader`, `SectionHeading`, `SpecialFilter`,
`CreditNames`.

`EventCard`'s `.event-date` / `.event-title` / `.event-venue` classes are
**script hooks, not styling** — the home page's inline "next live" script
rewrites those three nodes on the visitor's clock. Same for `.event-card-content`
(where it appends a venue line) and `#include-special`, `#event-list`,
`.month-heading`.

### `ui/icon` is edited on purpose

`src/components/ui/icon/icon.astro`'s `import.meta.glob` was narrowed from the
registry's `icons/*.svg` wildcards to an explicit allowlist. `eager: true`
means every matched file is emitted: the stock version shipped ~4,900 Lucide
and Simple Icons SVGs into `dist/` — 23MB of assets for the dozen this site
renders. Using a new icon means adding its name to that glob; an unmatched
name logs a build-time warning rather than rendering nothing.
