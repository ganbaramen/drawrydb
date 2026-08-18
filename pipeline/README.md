# Drawry. schedule & setlist tracker

Turns the band's public Google Calendar and their setlist posts on X into CSVs
you can sort, filter, and chart.

Python standard library only — no `pip install`, no venv, no API keys.
Python 3.9+.

---

## How the data flows

```
STEP 1   python3 pipeline/export_calendar.py

    Google Calendar                ·  the public iCal feed
  + event_overrides.csv            ·  YOURS — venue/times the calendar lacks
  ─────────────────────────
  → drawry_schedule.csv         one row per calendar EVENT


STEP 2   python3 pipeline/sync_setlists.py

    data/input/setlist_posts/*.txt   ·  YOURS — posts you paste from X
  + drawry_schedule.csv            ·  supplies year, event_uid, venue, times
  + song_corrections.csv           ·  YOURS — name merges you confirmed
  + venue_corrections.csv          ·  YOURS
  ─────────────────────────
  → setlists.csv                one row per SONG PLAYED
      │
      ├→ shows.csv              one row per SHOW  (+ calendar times)
      ├→ song_stats.csv         per track: plays, debut, play rate
      ├→ venue_stats.csv        per venue: shows, first/last played
      ├→ set_length_stats.csv   per set-length bucket  (+ calendar times)
      │
      ├→ venue_review.csv  ─────→  you read it, then add confirmed
      │                            merges to venue_corrections.csv ⤴
      └→ event_overrides.csv ───→  blank rows added for every gap,
                                   for you to fill in ⤴
```

Three kinds of file:

**Sources** — where facts actually come from. The calendar is fetched; setlist
posts you paste yourself, because X search can't be scripted for free.

**Yours** (marked above) — hand-edited files that only ever *correct or add to*
what the sources say. Delete one and you lose nothing but your corrections;
the raw parse comes back. They're re-applied on every run, so regenerating
never discards your work.

**Generated** — rebuilt from scratch every run. Don't hand-edit these; your
change disappears on the next run. Fix a source or a correction file instead.

The two arrows curving back up are the loops worth knowing:
`venue_review.csv` exists to be *read* (you decide, then write merges into
`venue_corrections.csv`), and `event_overrides.csv` gets blank rows added for
you automatically, so you never have to hunt for which shows are missing data.

---

## The files

| File | Role | What it is |
| --- | --- | --- |
| `data/input/setlist_posts/*.txt` | **source** | Post text you paste from X |
| `data/input/event_overrides.csv` | **yours** | Venue/times the calendar didn't state (rows auto-added) |
| `data/input/song_corrections.csv` | **yours** | Song-name typo merges, `wrong,correct,reason` |
| `data/input/venue_corrections.csv` | **yours** | Venue-name merges, `wrong,correct` |
| `data/generated/drawry_schedule.csv` | generated | One row per **calendar event** (199) |
| `data/generated/setlists.csv` | generated | One row per **song played** (1021) |
| `data/generated/shows.csv` | generated | One row per **actual performance** (141) |
| `data/generated/song_stats.csv` | generated | One row per track — plays, debut, play rate (22) |
| `data/generated/venue_stats.csv` | generated | One row per venue — shows, first/last played (55) |
| `data/generated/set_length_stats.csv` | generated | One row per set-length bucket |
| `data/generated/venue_review.csv` | generated | Worksheet: venues that might be duplicates |

Note that **calendar event ≠ show**: a 2-day event is one calendar row but two
shows, and one day can hold two events. `shows.csv` is the canonical show list;
join it to the calendar on `event_uid` ↔ `uid`.

---

## Everyday use

```sh
python3 pipeline/export_calendar.py     # refresh the calendar
python3 pipeline/sync_setlists.py       # rebuild everything else
```

Run the calendar first — setlist posts are matched against it.

### Adding setlists

1. Open the [#Drawryセトリ search](https://x.com/search?q=%23Drawry%E3%82%BB%E3%83%88%E3%83%AA&src=hashtag_click).
2. Select as many posts as you can and copy. X's timeline is virtualized, so a
   long drag-select only captures a screenful or two — that's a browser limit,
   not one here.
3. Paste into a **new** file in `data/input/setlist_posts/`, named however you like.
4. Run `python3 pipeline/sync_setlists.py`.

Don't worry about what the copy mangles — display names, `@Drawry0920`, the
`·`, timestamps, and `Show more` lines are all discarded. **Overlapping pastes
are fine**; duplicates are ignored, so you never have to remember where you
left off. Batch size doesn't matter either (1000 posts parse in under a tenth
of a second).

### Filling in gaps

Every run tops up `event_overrides.csv` with a row for each show whose calendar
entry is missing a venue or any time, and sorts rows-needing-attention first:

```
event_overrides.csv: 66/77 rows still need something — fill in what you know on those
```

Each row arrives with `date`, `match`, and everything the calendar already knew
prefilled — usually only the band's own slot (`live_start`/`live_end`, and
`meet_start`/`meet_end`) is actually blank, since 開場/開演 is normally stated
but ライブ/特典会 often isn't. Fill in what you know; leave the rest.

Rewriting only *adds* or *reorders* rows — cells you've filled in survive
byte-for-byte. Some rows arrive already complete: those are venues the calendar
stated ambiguously that got resolved from the setlist post. Leave them —
deleting one makes the calendar's venue revert to the unresolved text.

### Checking coverage

```sh
python3 pipeline/sync_setlists.py --missing
```

```
setlist coverage: 139/177 past events have a setlist (35 non-show entries ignored)
  3 without a setlist:
    2026-01-24  【イベント】こぐまカリーPresents「BEAR CUB CLUB」
```

Non-performances (`×`/`△` placeholders, 特典会, 配信, オフ会, solo-member events,
product releases) are filtered out. `--missing-all` includes them.

---

## Reference

### `drawry_schedule.csv`

Every event is an **all-day entry** — the venue and times live in prose inside
`description`, so they're parsed out:

| Column | From | Coverage |
| --- | --- | --- |
| `venue` | The `@venue` in the description's date line | 160/199 |
| `doors` / `showtime` | 開場 / 開演 — when the *event* opens and starts | 150/199 |
| `live_start` / `live_end` | ライブ — Drawry.'s own set | ~80/199 |
| `meet_start` / `meet_end` | 特典会 — their meet-and-greet | ~80/199 |

That distinction matters: most events are multi-group bills, so 開場/開演 is the
whole event's schedule while `live_start` is when *this band* plays. Two events
the same day can share a showtime but have different slots.

Plus `uid`, `start`, `end`, `all_day`, `summary`, `location`, `description`,
`status`, `recurrence`, `last_modified`. Times are `HH:MM`, Asia/Tokyo. Rows
sort by date then `live_start` (falling back to `showtime`, then `doors`).

Some descriptions name several venues at once — a shared bill
(`duo MUSIC EXCHANGE&SHIBUYA RING`), a circuit event
(`下北沢シャングリラ / MOSAiC / ERA / Flowers LOFT`), a multi-stage complex
(`大塚Hearts+、Hearts Next、…`). Those are flagged, never guessed at, and get
resolved automatically from the setlist post once it's pasted (via an
`event_overrides.csv` row).

### `setlists.csv`

One row per song: `event_date`, `live_start`, `showtime`, `event_uid`,
`position`, `song`, `corrected_from`, `is_se`, `is_interlude`, `is_encore`,
`note`, `venue`, `post_event_name`, `calendar_summary`, `source_file`.

- **`position`** is true running order counted from the top of the post, not the
  number printed beside it — posts occasionally misnumber (`01, 02, 02, 03…`),
  and the run tells you when they disagree.
- **Annotations go to `note`**, so `Fly By(初披露)` and `SE(Moving Lights!) ※New`
  stay the same track as their plain versions.
- **SE and Interlude are categories, not single tracks.** SE keeps its full name
  (`SE(スタンドバイミー)` ≠ `スタンドバイミー`); interludes are all written as a
  bare `Interlude`, so separate pieces can't be told apart. Both have flag
  columns so you can exclude them from a "songs performed" count.

### `shows.csv`

One row per actual performance — the canonical show list. `venue` comes from the
post (the reliable source); event name, times, counts, and `length_bucket` are
merged in from the matched calendar event.

A double-header day is two rows with different venues; a multi-day event is two
rows sharing one `event_uid`.

> Known gap: calendar times are per-*event*, not per-*day*, so both days of a
> multi-day event show the same times. Hasn't mattered yet — neither known
> multi-day event needs different ones.

### `song_stats.csv`

| Column | Notes |
| --- | --- |
| `plays` / `shows` | Total performances / distinct shows (differ if played twice a night) |
| `first_performed` / `last_performed` | Earliest and most recent appearance |
| `debut_confirmed` | `yes` when the band tagged that performance `初披露` |
| `shows_since_debut` / `play_rate` | Eligible shows, and `shows / shows_since_debut` |
| `encores`, `is_se`, `is_interlude` | Encore count and category flags |

`play_rate` compares fairly across debut dates — a track played at every show
since it debuted scores 1.00 whether it arrived in September or July.

When `debut_confirmed` is `no`, `first_performed` is only a **lower bound**: the
oldest performance captured, not necessarily the real debut.

### `venue_stats.csv` and `set_length_stats.csv`

`venue_stats.csv` is one row per venue (`shows`, `first_played`, `last_played`),
sorted by shows descending.

`set_length_stats.csv` buckets shows into 5-minute set lengths:

```
length,shows,avg_songs,avg_se,most_common_songs
20 min,13,4.8,0.7,"ルミナス (12/13), 朝焼けと車窓 (12/13), Moving Lights! (11/13), ..."
25 min,46,5.9,0.8,"朝焼けと車窓 (46/46), ルミナス (44/46), Dear,History (29/46), ..."
30 min,20,7.0,0.8,"ルミナス (19/20), 朝焼けと車窓 (19/20), ラブストーリーが始まらない (15/20), ..."
```

`avg_songs` excludes SE and Interlude (they're categories, not song choices);
`most_common_songs` ranks by rate within the bucket, so buckets stay comparable.
Coverage is partial — only shows whose calendar entry has both `live_start` and
`live_end`, and the run reports how many were excluded.

### `song_corrections.csv` and `venue_corrections.csv`

`song_corrections.csv` is `wrong,correct,reason`; `venue_corrections.csv` is
`wrong,correct` (no reason column — a venue rename doesn't need one the way a
song typo's source-post citation does). Every run flags candidates; **nothing
merges until you say so.**

```
  possible typo: 'Dear,Hisoty' (1x) vs 'Dear,History' (23x)
```

```csv
wrong,correct,reason
"Dear,Hisoty","Dear,History",typo in the source post (2026-04-25)
```

Corrections apply at parse time — your paste files are never modified, and
`corrected_from` preserves what was actually posted. A correction that stops
matching anything is reported rather than failing quietly.

For venues, read **`venue_review.csv`** first — it groups names that might be
the same place, with a `suggested_canonical` guess:

```
cluster,venue,shows,first_played,last_played,suggested_canonical
1,Spotify O-Crest,6,2025-09-20,2026-05-30,Spotify O-Crest
1,Spotify O-WEST,1,2026-01-03,2026-01-03,Spotify O-Crest
1,Spotify O-nest,1,2026-01-04,2026-01-04,Spotify O-Crest
```

**Read every group before merging — grouped does not mean duplicate.** That
example is exactly the trap: `O-Crest`, `O-WEST`, and `O-nest` are three
genuinely different venues in the same Shibuya complex, and merging them would
corrupt the venue stats. Same for `大塚Hearts+` vs `大塚Hearts Next` — plausibly
sister venues, not variant spellings. The grouping is a prompt to look, not a
recommendation, and `suggested_canonical` is just the most-played spelling.

Venue merges only affect display and venue stats — never which calendar event a
post matches — so they're safe to get wrong and fix later.

### `event_overrides.csv`

```csv
date,match,venue,doors,showtime,live_start,live_end,meet_start,meet_end
2025-12-20,BREAKING RizM,,,,13:20,13:45,14:00,15:00
```

- **`date`** (required), `YYYY-MM-DD`.
- **`match`** — any substring of the event's `summary`. Only needed to
  disambiguate two events on the same day.
- **Blank** means "keep whatever was parsed"; a lone **`-`** *clears* a value the
  parser got wrong.

The run reports what it applied, and warns about rows that no longer match
anything (stale) or match more than one event (ambiguous).

---

## Flags

**`export_calendar.py`**

| Flag | Effect |
| --- | --- |
| `--tz UTC` | Render times in another timezone (default `Asia/Tokyo`) |
| `--quiet` | Print only on change or warning — good for cron |
| `--watch 3600` | Stay running, refresh every N seconds |
| `-o`, `--overrides` | Override paths |

Writes are atomic, so a spreadsheet reading mid-refresh never sees a partial
file. For automatic updates, either leave `--watch` running or add a cron entry:

```cron
0 * * * * /usr/bin/python3 /path/to/drawrydb/pipeline/export_calendar.py --quiet >> /tmp/drawry-export.log 2>&1
```

No `cd` needed — both scripts resolve `data/` against the repo root rather than
the working directory, so they run correctly from anywhere.

**`sync_setlists.py`**

| Flag | Effect |
| --- | --- |
| `--missing` | Past events with no setlist |
| `--missing-all` | Include non-show entries (特典会, 配信, `×`…) |
| `--posts-dir`, `--calendar`, `-o`, … | Override paths |

---

## Troubleshooting

**A paste produced fewer shows than I copied.** Blocks are skipped when they
have no `月/日` date line or no numbered song lines — usually a post truncated
by `Show more` before the songs. Expand it on X and re-copy; deduping means you
can just paste the whole batch again.

**`conflict: <date> @ <venue> — two pastes disagree`.** One of them is truncated
or the post was edited. Find it via `source_file`, fix or delete it, re-run.

**Wrong year on a show.** Posts write `8月16日` with no year, so the year comes
from matching against the calendar. If the month/day wasn't there, it falls back
to the nearest past year — refresh the calendar and re-run.

**`no calendar event for <date> @ <venue>`.** The setlist is still kept, just
with an empty `event_uid`. Usually means the calendar needs refreshing.
