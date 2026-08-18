# Drawry.

Tracking Drawry.'s live schedule and setlists — a data pipeline, and
DrawryDB, the static site built on top of it:
**https://ganbaramen.github.io/drawrydb/**

```
pipeline/        scripts that fetch, parse, clean, and export → pipeline/README.md
data/input/      what you maintain by hand (safe to edit)
data/generated/  what the pipeline writes (never edit)
site/            DrawryDB — an Astro site, deployed to GitHub Pages
.github/workflows/  CI: rebuild the calendar hourly, deploy the site on push
```

## Quick start

```sh
python3 pipeline/export_calendar.py     # refresh the calendar
python3 pipeline/sync_setlists.py       # rebuild everything else
python3 pipeline/export_site_data.py    # rebuild site/'s data/generated/site_data.json
```

Run the calendar first — setlist posts are matched against it. All three work
from any directory. Python 3.9+, standard library only.

Or run all three at once with `pipeline/refresh_all.sh` — a plain wrapper
around the same three commands, for the common "just refresh everything"
case. Prefer the individual commands when testing one script's own change.
If you've only edited `event_overrides.csv`, add `--offline`
(`refresh_all.sh --offline` or `export_calendar.py --offline`) to reapply
it from the last fetch's cache instead of hitting the calendar again.

To run the site itself:

```sh
cd site && npm install && npm run dev
```

It reads `data/generated/site_data.json` at build time, so re-run
`export_site_data.py` after any pipeline change before `npm run dev`/`build`.

## Automation

Two GitHub Actions workflows keep the live site current without a manual
pipeline run:

- **`refresh-data.yml`** — hourly, refreshes `drawry_schedule.csv` from the
  public calendar feed, re-runs `sync_setlists.py`, rebuilds
  `site_data.json`, and commits if anything changed. Setlists still need a
  human to paste the source posts (see below) — this only keeps the
  calendar half current.
- **`deploy.yml`** — on every push that touches `site/` or `site_data.json`,
  builds the Astro site and deploys it to GitHub Pages.

## What's here

The band's public Google Calendar and their `#Drawryセトリ` posts on X become
CSVs you can sort, filter, and chart:

| | |
| --- | --- |
| `data/generated/shows.csv` | one row per performance — the canonical show list |
| `data/generated/setlists.csv` | one row per song played |
| `data/generated/song_stats.csv` | per track: plays, debut date, play rate |
| `data/generated/venue_stats.csv` | per venue: shows, first/last played |
| `data/generated/set_length_stats.csv` | what a 20/25/30-minute set looks like |
| `data/generated/site_data.json` | events/songs/venues joined and denormalized for the site |

Setlists are copy-paste driven — X search can't be scripted for free — so
`data/input/setlist_posts/` holds the raw post text you paste in. The three
other files in `data/input/` are corrections and overrides you fill in; the
pipeline flags what needs attention and never overwrites your answers.

**[pipeline/README.md](pipeline/README.md)** covers all of it: the data flow,
every column, the paste workflow, and troubleshooting.

## Docs

| File | What it's for |
| --- | --- |
| [pipeline/README.md](pipeline/README.md) | How the pipeline works — start here |
| `DRAWRYDB.md` | The website's plan and phases — local notes, not tracked in git |
| `IDEAS.md` | Backlog and undecided questions — local notes, not tracked in git |
| [CLAUDE.md](CLAUDE.md) | Notes for Claude — the *why* behind the code |
