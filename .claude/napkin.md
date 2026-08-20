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

## Current state anchors (update when they change)

- Layout since 2026-08-17: `pipeline/` scripts, `data/input/`, `data/generated/`.
  Scripts resolve paths from repo root — runnable from anywhere.
- Healthy run: 141 shows, 1021 setlist rows, 0 unlinked, 0 dropped lines.
- Git repo on `main`; user pushes, I commit locally. DrawryDB site plan in
  DRAWRYDB.md (gitignored).
- Show grouping lives in `show_key()`/`group_shows()` (sync_setlists.py); the
  three `*_details.csv` files are read by one `load_details()`
  (export_site_data.py). Don't re-add per-kind loaders.
