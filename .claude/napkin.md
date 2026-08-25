# Napkin — drawry

Process lessons for working in this repo. Domain rationale lives in CLAUDE.md;
this is about *how to work here without repeating mistakes*.

## Mistakes actually made here (don't repeat)

- **Ran `rm -f event_overrides.csv` on the real file to test regeneration.**
  Destroyed hand-entered times; recovered only because the values happened to
  be in session scrollback. Test destructive flows against a scratch copy in
  the scratchpad dir, always. (The later repo reorg did this right: full
  backup to scratch first, then byte-compare outputs after.)
- **Backfill scripts got the lookup key wrong twice.** Keyed by `summary`
  alone (wrong venue for recurring titles like TOKYO BEATREC), then by exact
  `summary` equality against a hand-typed substring `match` (overwrote a real
  value with blank). Rule: match `(date, match)` with substring containment,
  same as `apply_overrides()`.
- **Verified a backfill against contaminated data.** Checked venues against
  `drawry_schedule.csv`, which had already absorbed a wrong override — it
  confirmed its own error. Ground truth for venues is `setlists.csv`
  (post-derived), independent of the override chain.
- **Appended without checking `(date, match)` already existed** → duplicate
  override row. Any one-off script touching event_overrides.csv must dedupe
  against existing rows.
- **Wrote a doc claim without checking current data** ("O-Crest/O-nest/O-WEST
  would never cluster together" — they were clustered at that very moment).
  Re-run and look before asserting behavior in docs.
- **Referenced `first_performed` as if it were module-level** in
  export_site_data.py's build_songs() — it's a local of
  build_set_length_stats(). Per-song debut comes from the song_stats row;
  pass it explicitly.
- **Regex bracket trap that ate ~an hour**: writing `[）)])?` inside an
  open `(?:` group — the ) closes the GROUP early, ? quantifies the group,
  and the close-bracket class becomes mandatory within it. Symptom: pattern
  matched the parenthesized variant "(火)" but silently failed on bare "木",
  looking like a Python re bug. Fix/shape to remember:
  `[）)]?)?` — ? on the class, THEN close the group. When a regex
  "impossibly" fails, print `_parser.parse(pat)` and check where groups
  actually close before suspecting the engine.

- **An `import.meta.glob(..., {eager: true})` wildcard emits every matched
  file.** Fulldev's stock `ui/icon` globs all of lucide-static and
  simple-icons; installing it grew `dist/` from ~15MB to 38MB (23MB of
  unused SVGs) with no build error and no warning. `du -sh dist` after
  adding any dependency that globs node_modules.

## Patterns that keep working

- After changing `parse_post`/regexes: run the dropped-line audit in
  CLAUDE.md § Verifying changes. Counts alone hide dropped lines.
- The user's "does X actually cover everything?" question has been answered
  "no" three times (venue trigger, per-field time triggers, ambiguous-venue
  trigger). Treat that question as a bug report, and check *existing* rows
  after widening prefill logic — append-only files don't retro-fill.
- Prove regeneration claims by deleting-and-regenerating **a scratch copy**
  and diffing byte-for-byte.
- User prefers: flag automatically, merge only on their confirmation
  (songs, venues); worksheets (CSV) over console listings for decisions;
  everything regenerated on every run rather than behind flags.

- **Proposed "optimizations" without measuring first.** Before the 2026-08-19
  cleanup, the instinct was to chase payload size (the events index looked
  like 81KB of repeated `data-astro-cid` attributes). Gzip takes it to 11KB;
  the pipeline runs in 0.3s and the site builds in 1.2s. Nothing here is
  slow. Measure, then say plainly that speed isn't the problem, rather than
  optimizing something that isn't costing anything.

## Patterns that keep working (cont.)

- **Refactor verification that actually proves something:** snapshot every
  generated CSV + `site_data.json` to scratch, refactor, regenerate, `cmp`
  each one. For site code, build → copy dist → `git stash` → rebuild from
  original source → `diff -rq` the two dists. 0 differences across 533 pages
  is the claim worth making; "the build passed" isn't.

## Domain notes

- Generated CSVs have a UTF-8 BOM — read with `encoding='utf-8-sig'` or the
  first column name comes back `\ufeffevent_date`.
- Group setlist rows by `event_date|event_uid`, sort by int(position).
- Signature sequence: ルミナス → 朝焼けと車窓 appears in ~half of all shows
  (71/141 as a pair); encore-crossing pairs are essentially never repeated
  (all 1x), so encores are where variation lives.

## Current state anchors (update when they change)

- Layout since 2026-08-17: `pipeline/` scripts, `data/input/`, `data/generated/`.
  Scripts resolve paths from repo root — runnable from anywhere.
- Healthy run: 141 shows, 1021 setlist rows, 0 unlinked, 0 dropped lines.
- Git repo on `main`; user pushes, I commit locally. DrawryDB site plan in
  DRAWRYDB.md (gitignored).
- Show grouping lives in `show_key()`/`group_shows()` (sync_setlists.py); the
  three `*_details.csv` files are read by one `load_details()`
  (export_site_data.py). Don't re-add per-kind loaders.
- Input-file vocabulary (settled 2026-08-19, see CLAUDE.md's table): **rename**
  = rewrite a string everywhere (`song_renames.csv`, `venue_renames.csv`, was
  `*_corrections.csv`); **override** = replace a field on one event
  (`event_overrides.csv`); **details** = per-name facts (`*_details.csv`);
  **note** = freeform per-event prose (`event_notes.csv`).
- `setlists.csv` has no `corrected_from` column (removed 2026-08-19 — unread,
  4/1021 rows populated). The raw posted spelling lives in
  `data/input/setlist_posts/`, which is never edited.
- UI stack since 2026-08-25: Astro + Tailwind v4 + **Fulldev UI**
  (`npx shadcn@latest add @fulldev/<name>`, source lands in
  `site/src/components/ui/`). Palette unchanged, retokenized to shadcn names
  in `site/src/styles/global.css` — see `site/CLAUDE.md` for the two
  non-stock bits (`--link`, the three-state `dark` variant) that
  `@fulldev/init --overwrite` would destroy.
- Streak fields (added 2026-08-21): songs carry `current_streak`/
  `longest_streak`, computed in build_songs() per show *date* (double-header
  day = one unit), denominator starts at the song's debut, only shows with a
  posted setlist count. Rendered on song pages with build-time days-since.
- Site slugs: song/venue ids are hand-maintained slugs (e.g. `luminous`,
  `asayake-to-shasou`), not raw Japanese — dist paths use them.
- Theme toggle (2026-08-25): rectangle View Transition reveal on theme
  switch (beui.dev's ThemeToggle look, re-implemented as vanilla JS in
  Layout.astro — the original needs React/shadcn). No-API and
  reduced-motion fall back to instant swap. global.css disables the UA
  cross-fade via ::view-transition-* rules; keep those if touching themes.
- Ticket sales (added 2026-08-22): `parse_ticket_sales()` in
  export_site_data.py extracts 発売 phases from calendar descriptions into
  events[].ticket_sales ({label, start, end}, "YYYY-MM-DD HH:MM", year
  resolved against the event date). Rendered on event pages below ticket
  links. One description uses U+2028 line separators, not \n. The bare
  "[一般発売]" header (no time) is intentionally skipped.
- "Next live" bug (fixed 2026-08-24): homepage used `date >= today` only,
  so a same-JST-day show with its setlist already posted still showed as
  next live. Rule now: upcoming = no setlist yet AND date >= today.
  has_setlist is the authoritative "this show is over" flag — setlists are
  only entered post-show. Then (same day) made the pick view-time instead
  of build-time: homepage embeds all pending events as JSON + inline script
  re-picks on the visitor's JST clock; build-time choice stays as no-JS
  fallback. Static files unchanged; only setlist-entry staleness still
  needs a deploy.
