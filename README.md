# Drawry.

Tracking Drawry.'s live schedule and setlists — a data pipeline now, a website
([DrawryDB](DRAWRYDB.md)) later.

```
pipeline/     scripts that fetch, parse, and clean          → pipeline/README.md
data/input/   what you maintain by hand (safe to edit)
data/generated/  what the pipeline writes (never edit)
site/         DrawryDB — not built yet                      → DRAWRYDB.md
```

## Quick start

```sh
python3 pipeline/export_calendar.py     # refresh the calendar
python3 pipeline/sync_setlists.py       # rebuild everything else
```

Run the calendar first — setlist posts are matched against it. Both work from
any directory. Python 3.9+, standard library only.

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
| [DRAWRYDB.md](DRAWRYDB.md) | Plan for the website |
| [IDEAS.md](IDEAS.md) | Backlog and undecided questions |
| [CLAUDE.md](CLAUDE.md) | Notes for Claude — the *why* behind the code |
