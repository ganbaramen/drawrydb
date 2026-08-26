# Notes for Claude

Personal project: track Drawry.'s live schedule and setlists as CSVs, with a
static site (DrawryDB — see `DRAWRYDB.md`) planned on top.
See `pipeline/README.md` for the user-facing workflow. This file is the *why*.

Layout: scripts in `pipeline/`, hand-maintained inputs in `data/input/`,
generated CSVs in `data/generated/`. Both scripts resolve paths against the
repo root (`ROOT` in each), so they run correctly from any working directory
— keep that property; cron depends on it.

## Constraints that shaped everything

- **Standard library only, both scripts.** They're meant to run from cron with
  system `/usr/bin/python3`. Don't add `icalendar`, `requests`, `pandas`, etc.
  without asking — a venv that goes stale silently breaks the cron job.
- **The CSVs in `data/generated/` are generated artifacts.** Never hand-edit
  them; fix the script or the input file and regenerate. Hand-maintained files
  live only in `data/input/`.

## Hand-maintained input files: renames vs overrides vs details vs notes

Six files in `data/input/`, varying along two axes — what a row is keyed by,
and whether it replaces something the source said or adds something it never
had. `pipeline/README.md` has the same table for the user-facing version:

| | replaces what the source says | adds what the source never had |
| --- | --- | --- |
| keyed by a name | `song_renames.csv`, `venue_renames.csv` | `song_details.csv`, `venue_details.csv`, `creator_details.csv` |
| keyed by an event (`date` + optional `match`) | `event_overrides.csv` | `event_notes.csv` |

The `*_renames.csv` pair were called `*_corrections.csv` until 2026-08-19 —
renamed because "corrections" and "overrides" read as synonyms while sitting
in the *same* column of that table, which is exactly the distinction the
names needed to carry. A **rename** rewrites one string wherever it appears;
an **override** replaces a named field on one event. `load_renames()` (was
`load_corrections()`) stays generic across both rename files.

`setlists.csv` briefly kept a `corrected_from` column recording the posted
spelling; it was dropped rather than renamed to `renamed_from` (see the data
quality section) — nothing consumed it and the paste files already hold the
original verbatim.

## Calendar (`export_calendar.py`)

- Source is the **public iCal feed**, not the API:
  `https://calendar.google.com/calendar/ical/<url-encoded-id>/public/basic.ics`.
  No auth, no key. Confirmed working; the calendar is public
  (`X-WR-CALNAME: Drawry.公開スケジュール`, `X-WR-TIMEZONE: Asia/Tokyo`).
- The feed had **199 events and zero `RRULE`s** when built. The parser still
  passes any `RRULE` through to a `recurrence` column rather than silently
  dropping it, but recurrence expansion is *not* implemented. If recurring
  events ever appear, that column is the signal to implement it.
- **Every event is all-day.** All times are prose inside `DESCRIPTION`. Don't
  assume `start` carries one.
- `parse_times()` reads 開場/開演 into `doors`/`showtime` (149/199). Two
  spellings, both handled: labelled separately (`開場 18:30 / 開演 19:00`, 146)
  and combined (`開場 / 開演 11:00 / 11:30`, 3). Watch for NBSP (`\xa0`) between
  label and time — `\s` covers it.
- `parse_slots()` reads ライブ/特典会 into `live_start`/`live_end` (80) and
  `meet_start`/`meet_end` (79). **This is the important one**: most events are
  multi-group bills, so 開場/開演 is the *event's* schedule while ライブ is when
  Drawry. actually plays. Two events on one day can share a showtime (2025-12-20
  does) and only the slot distinguishes them.
  - Two layouts. Label-first (`ライブ 19:30~20:00`) is the common one; its regex
    uses `[^\S\n]` rather than `\s` for gaps, because crossing a newline made
    `20:50 特典会\n22:00 特典会終了` read 22:00 as the *start*.
  - Time-first timetables (`20:10 Drawry.` / `20:50 特典会` / `22:00 特典会終了`)
    are 3 entries, handled by `TIMETABLE_LINE`. `live_end` is deliberately left
    blank there — the source only gives the next act's start, which is not when
    this set ended.
  - Requiring a digit after the label keeps `特典会：バレンタインコスプレ` and
    `ライブ会場：…` out.
- `parse_venue()` reads the description's `@venue` line into `venue` (156/199).
  A description naming multiple venues at once is common, not a one-off:
  `&`-joined shared bills (`duo MUSIC EXCHANGE&SHIBUYA RING`), `/`-joined
  rotating circuit events (`下北沢シャングリラ / MOSAiC / ERA / Flowers LOFT`),
  and `、`-joined multi-stage venue complexes (`大塚Hearts+、Hearts Next、
  MEETS、...`) all showed up once looked for — 12 events total.
  `VENUE_AMBIGUOUS` (`.+[&/、].+`) flags these rather than guessing.
  - **Every one found so far resolved via the setlist post** — the post always
    names the one specific venue/stage actually played, even when the
    calendar description lists several. Check `setlists.csv`'s `venue` for
    that date before asking the user; there was nothing to ask in any of the
    12 real cases.
  - `・` is deliberately **excluded** despite also being a list separator in
    some strings (`大阪・心斎橋エリアライブハウス8会場`) — it's overloaded
    here as a plain connector inside area descriptors (`THE LIVE HOUSE
    soma(大阪・心斎橋)`) and room-size suffixes (`TFTホール 1000・500・300`),
    both single real venues. Adding it would false-positive on those. If a
    genuinely ambiguous `・`-joined case shows up, it needs a smarter check
    than "contains this character," not just adding it to the class.
- Rows sort by `(start, live_start or showtime or doors, summary)` so same-day
  events land in the order the band played; untimed entries sort last that day.
- **`event_overrides.csv` is the hand-entry escape hatch** for venue or times
  the description doesn't state or states unreadably. `OVERRIDE_FIELDS` is
  generic — `apply_overrides()` doesn't care which columns it's setting, so
  `venue` slotted in alongside the time fields with no special-casing. Applied
  after parsing and *before* sorting (the sort keys off these times), on every
  run — that is what makes them survive regeneration. Keyed by `date` plus an
  optional `match` substring of `summary` for double-header days.
  - Blank cell = keep the parsed value; a lone `-` = clear it. Both are needed:
    without the sentinel there'd be no way to delete a wrong parse.
  - Ambiguous and stale rows are reported rather than silently skipped, and
    those warnings print even under `--quiet` (the "applied" lines don't, so
    cron stays silent).
  - Same principle as `song_renames.csv`: the generated CSV is never
    hand-edited, the fix lives in its own tracked input file.
- All-day `DTEND` is exclusive in iCal; the script subtracts a day so `end` is
  the last day the event actually covers.
- `DESCRIPTION` contains **HTML** (`<br>`, entities) — flattened to plain text.
- Output is **UTF-8 with BOM** (`utf-8-sig`) so Excel doesn't mangle Japanese.
  Read it back with `utf-8-sig` too.
- Writes are atomic (tempfile + `os.replace`) and skipped entirely when the
  diff is empty, so cron doesn't churn the file's mtime.

## Setlists (`sync_setlists.py`)

### Why copy-paste

Access to `#Drawryセトリ` was investigated and every automated route was ruled
out — **don't re-litigate this without new information**:

| Route | Finding |
| --- | --- |
| Logged-out `x.com/search` scrape | HTTP 200 but returns the "JavaScript is not available" shell — no data |
| `nitter.net` | 200 with a zero-byte body; instance dead |
| `xcancel.com` | Behind an Anubis "Verifying your browser…" challenge |
| X API | Viable but paid — pay-per-usage since Feb 2026, ~$0.005/post read. **Rejected by the user because the historical archive wasn't reachable** (recent search only covers 7 days; full-archive is gated) |
| Playwright on the user's Chrome profile | Offered; user chose paste instead |

### Post format the parser assumes

Posts come from `@Drawry0920` and are remarkably consistent:

```
【セットリスト】
8月16日(日)@ LIVLIV(静岡ARTIE)
いつかの夜に僕たちが、&こぐまカリー共催「いつクマッ！」
01. SE(Moving Lights!)
02. Moving Lights!
...
#Drawry #Drawryセトリ
```

Parsing anchors, in order:

1. Split on the `【セットリスト】` header — one post per occurrence.
2. Each post body ends at its trailing hashtag line — either one containing
   `セトリ`, or (once songs have started) any line made only of hashtags, since
   some posts close with a bare `#Drawry`. **This matters:** without it, the
   next post's author block (display name, `@handle`, `·`, timestamp) would be
   read as setlist content. The "once songs have started" guard is load-bearing:
   several event names are themselves hashtags (`#ﾆｷﾌﾟﾚ『シキサイ。』`) and would
   otherwise terminate the post before any song was read.
3. First `N月N日` line gives date + venue (venue follows `@`).
4. Lines between the date line and the first numbered line are the event name.
5. Numbered lines (`01.`, `1.`, `M1.`, full-width digits) are the songs.
6. **Encore lines are not numbered** — `En. Moving Lights!` has its own regex
   (`ENCORE_LINE`). This was found only by auditing for lines the parser
   silently ignored; a song line that matches nothing vanishes without warning.
   **After changing the parser, re-run that audit** (see below) rather than
   trusting the post/song counts, which look fine when a line is dropped.

Copy-paste noise (`Show more`, `Show less`, `Translate post`, bare `·`) is
filtered by an explicit set. Add to `NOISE_LINES` if X introduces more.

**`トークパート` marks a pre-set talk segment and is excluded from the
counted setlist entirely**, not parsed as a song — everything between it and
the `本編` line that closes it is dropped from `setlists.csv` and printed by
`build_rows()` (always, not gated by `--quiet`) so it stays visible rather
than silently vanishing. This exists because of exactly one real case,
2026-04-04@下北沢MOSAiC, where the talk part is an acoustic rendition of
`ラブストーリーが始まらない` tagged `※初披露` — that song is *also* played
normally later in the same set's `本編` (track 06), so counting the talk-part
line as a song row double-counted it and made `build_stats()`'s "初披露 tag
looks wrong" check misfire (the acoustic version's debut tag doesn't apply to
the studio version). An earlier version of this parser folded トークパート
content into the *event name* instead (wrong: it isn't the event's name), then
a version after that turned it into a song row with a `トークパート` note
(wrong for the double-counting reason above) — this is the third iteration,
now dropped from the setlist and surfaced as a free-text event note instead
(see below).

## Event notes (`event_notes.csv`)

`data/input/event_notes.csv` (`date,match,note`) is a freeform per-event note,
hand-maintained the same way `event_overrides.csv` is — same `date` +
optional `match` (substring of the event's calendar summary, for double-header
days) keying, applied in `export_site_data.py`'s `apply_event_notes()`, which
mirrors `export_calendar.py`'s `apply_overrides()` including its "ambiguous or
stale match gets reported, not silently skipped" behavior. `note` can be
multi-line — a quoted CSV field already supports embedded newlines, so no
special parsing is needed on either the read or write side; the site renders
it with `white-space: pre-line` (`.event-note` in global.css) rather than
splitting it into paragraphs itself.

This is also where a dropped トークパート block's text is meant to end up —
`build_rows()`'s print (see above) exists specifically to remind you to copy
it in here, since nothing does that automatically.

Careful: the account's **display name** is
`Drawry. 10/26(月) 2nd ONEMAN LIVE@渋谷WWW` — it contains both a date-like
string and an `@venue`. Anchoring on `【セットリスト】` and taking the *next*
line avoids it. Don't rewrite the date/venue extraction to scan freely.

### Year inference

Posts write `8月16日` with **no year**. The calendar CSV is the oracle:
month/day is matched against real event dates, which also yields `event_uid`
for the join. Fallback when unmatched is nearest past year, and the show is
reported to the user with an empty `event_uid` rather than dropped.

Implication: **the calendar must be refreshed before parsing recent posts.**

Matching runs against an event's **whole span**, not just its start day
(`event_days()`), because a two-day festival is a single calendar entry that
gets one setlist post per day. There were 3 multi-day events out of 199, and
both initially-unmatched shows (2026-04-19, 2026-05-24) turned out to be day 2
of one. Both days share the event's `uid`; `event_date` is what separates them.

**A date is not a unique key.** The band plays two events on the same day
regularly (at least 6 such days). When several calendar events share the matched
date, `match_score()` breaks the tie on venue (checked against the event's
`description`, which repeats it — worth 2.0) and event name (a fuzzy ratio;
weaker, because the two sources abbreviate differently). Before this existed,
both posts from a double-header got the *same* uid and the other event looked
uncovered — which presents as "the setlist is missing" even though it was
parsed fine. If shows ever go missing despite being pasted, check this first.

### Row ordering

`setlists.csv` sorts by `(event_date, live_start or showtime, venue, position)`.
Both times are copied from the matched calendar event for exactly this reason:
sorting by `(event_date, position)` alone **interleaves** two same-day setlists
into one another (pos 1 of show A, pos 1 of show B, pos 2 of show A…), which
looks like a single scrambled setlist. `live_start` leads because two events on
a day can share a `showtime`. Don't drop them from the sort key.

### Deduping

Key is `(event_date, venue)`, first paste wins. Overlapping pastes are the
expected workflow, not an error. If the same key appears with a *different*
song list, that's reported as a conflict (truncated or edited post) rather than
silently resolved.

Known limit: two genuinely different shows on the same date at the same venue
would collide. Hasn't happened; a 昼/夜 double-header would trigger it.

### Song naming decisions (user-specified)

- **SE tracks keep their verbatim name.** `SE(Draw a Story)` is its own track,
  *not* `Draw a Story`. An earlier version stripped the wrapper; the user
  corrected it. The `is_se` flag exists so they can still be filtered out.
- **Interlude is a category too** (user-specified), flagged by `is_interlude`.
  Every one is written as a bare `Interlude`, so distinct pieces are
  indistinguishable by name. This is why `Interlude` carries a `初披露` tag on
  both 2026-03-15 and 2026-06-28 despite being played from 2026-01-11 — those
  are different interludes, not bad data. `report_stats()` exempts SE and
  Interlude from its "marker looks wrong" check for exactly this reason; don't
  remove that exemption.
- `(初披露)`-style suffixes are split into the `note` column so a debut doesn't
  fork the song name — `Fly By(初披露)` and `Fly By` must stay one track. The
  keyword list in `SONG_NOTE` is deliberately explicit rather than "any trailing
  paren", because `SE(曲名)` is a paren that belongs to the title. Real data has
  already needed `拡張イントロ` added (it was splitting `プライマリ` into two
  tracks); expect to extend the list as new annotations appear.
- `※` introduces a free-form aside (`SE(Moving Lights!) ※New`), handled by
  `SONG_ASIDE`. Unlike parens, everything after `※` is always commentary, so it
  needs no keyword gate. Both kinds can co-occur; notes join with `; `.

`position` is **running order derived from order of appearance**, not the number
printed in the post — two posts number their songs `01, 02, 02, 03…`. The
posted sequence is compared and reported (`numbering typo in post: …`) but never
used. Don't "fix" this by trusting `SONG_LINE`'s captured number.

## Data quality

The source posts contain occasional typos — `Dear,Hisoty` for `Dear,History`
appears once. `report_typos()` flags near-identical names (difflib ≥ 0.85, only
when the rarer name occurs ≤2 times) so they surface on every run. It compares
SE names only against other SE names, since `SE(ラブストーリーが始まらない)` vs
`ラブストーリーが始まらない` is a real distinction, not a typo.

Renames live in **`song_renames.csv`** (`wrong,correct,reason`), applied
at parse time. Two rules, both deliberate:

- **Never edit the paste files.** They are the raw record of what was posted,
  and the only place the original spelling survives — `setlists.csv` used to
  carry a `corrected_from` column for that, removed 2026-08-19 because
  nothing read it and it was populated on 4 of 1021 rows. "What did the post
  actually say" is still answerable: `data/input/setlist_posts/` has the
  verbatim text, and `song_renames.csv` maps every rewrite. If a consumer
  ever genuinely needs it in the CSV, re-adding the column is two lines in
  `build_rows()` — but don't re-add it speculatively.

Only add a rename the user has confirmed — flagging is automatic, merging is
not. A rename that matches nothing is reported as possibly stale rather than
ignored.

**Venue names get the identical treatment via `venue_renames.csv`**
(`load_renames()` is reused as-is — the function is generic, "wrong ->
correct" doesn't care whether the strings are song or venue names). Applied in
`build_rows()` only to the row's output `venue` field, *not* to the value used
by `match_score()`/`resolve_date()` for finding the calendar event — the raw
posted text is more likely to appear verbatim in the calendar `description`
than a canonicalized name would be, so correcting before matching could make
matching worse, not better.

### Venue clustering (`venue_review.csv`)

The single-threshold `report_typos()` approach (fuzzy ratio, one gate) doesn't
work for venues — a plain "possible variant" list per-pair, printed to the
console, isn't the interface the user wanted; they asked for a way to *decide*
canonical names and merges, i.e. a worksheet grouping the candidates, which is
`report_venue_review()` writing `venue_review.csv` (one row per venue, grouped
by `cluster`, with a `suggested_canonical` guess — the most-played spelling in
the group — that is never applied anywhere, purely a typing shortcut).

**No `counts[other] <= 2` gate** the way `report_typos()` has for songs — a
venue variant isn't necessarily rare, the band may have played there several
times under each spelling.

`venue_related()` (the pairwise test feeding union-find in `cluster_venues()`)
went through three rounds of false-positive hunting against the real dataset,
each one worth knowing before touching the thresholds:

1. **Naive fuzzy ratio + substring + shared-token, no area handling.**
   `SHIBUYA` alone chained nine unrelated venues into one 9-member cluster
   (`SHIBUYA RING`, `SHIBUYA CYCLONE`, `Veats SHIBUYA`, …), and `アメリカ村`
   transitively pulled `BEYOND` and `アメリカ村DROP` together through
   `アメリカ村BEYOND`. **Fix:** `VENUE_AREA_WORDS`/`strip_area()` — every
   heuristic runs on the area-stripped name. This is exactly why
   `Spotify O-Crest`/`O-nest`/`O-WEST` do *not* cluster: their distinguishing
   suffix survives stripping and stays different.
2. **Ratio threshold at 0.6.** Let through `大塚Hearts+`/`Veats SHIBUYA`
   (0.67, coincidental shared letters after stripping) and `下北沢ADRIFT`/
   `渋谷GRIT` (0.60). Every true positive that relies on ratio (not caught by
   substring alone) sits at 0.75+ — `下北沢Flowers Loft` vs `Flowers LOFT` is
   the floor. **Fix:** raised to 0.75. If you ever need to lower it again,
   recheck both floors first; the gap between them is narrow.
3. **Substring match, no length or generic-word floor.** `渋谷音楽堂` ("concert
   hall") stripped to `音楽堂` (3 chars) and matched as a substring of an
   unrelated venue's name. Separately, `新宿LOFT` stripped to `LOFT` (4 chars,
   passing a naive length check) and matched inside `下北沢Flowers LOFT` —
   `LOFT` is a nationwide live-house chain, so two different buildings share
   the word by brand, not identity. **Fix:** substring/token matches require
   both sides ≥4 chars *and* the shorter side isn't in `VENUE_GENERIC_WORDS`
   (`LOFT`, `HALL`, `STUDIO`, `CLUB`, `LIVE`, `THEATER`/`THEATRE`).

Both stoplists (`VENUE_AREA_WORDS`, `VENUE_GENERIC_WORDS`) are **not claimed
complete** — built from what actually appeared in this dataset's false
positives, not a general gazetteer. Expect to extend either if a new area name
or chain brand causes a bad cluster; that's the normal failure mode here, not
a sign the approach is wrong.

Even after all three fixes, a clean cluster isn't a merge order — `渋谷WOMB`
and `渋谷WOMBLIVE` cluster correctly (real name relationship) but may be a main
room and a sister room, not the same room under two names. **Never
auto-populate `venue_renames.csv`** — the worksheet's job is to make the
candidates cheap to review, not to substitute for the user's local knowledge
of which venues are actually the same place.

## Stats (`song_stats.csv`, `venue_stats.csv`, `set_length_stats.csv`)

All three written on every run alongside `setlists.csv`. Tables rather than
printed output because the data is tabular and sorting a column subsumes
multiple useful orderings. Stays in the same CSV pipeline as everything else.

`first_performed` (song_stats) is derived from the data, not from `初披露`
tags, because the tags are unreliable (see the Interlude note above).
`debut_confirmed` records whether a tag corroborates it; when `no`, the date is
only a lower bound on the real debut, limited by how far back the pastes reach.
It is a **maintainer-facing column only** — it stays in `song_stats.csv` and in
`report_stats()`'s summary, and is deliberately not exported to the site.
`export_site_data.py` shipped it to the browser until 2026-08-25, where no page
ever read it; don't re-add it without a page that actually shows something.

`shows_since_debut` / `play_rate` (song_stats) exist because raw `plays` isn't
a fair comparison across songs with different debut dates — a song that's been
in the set since day one racks up plays just by being older. `shows_since_debut`
counts all shows (not just this song's) with `event_date >= first_performed`;
`play_rate = shows / shows_since_debut`. Both counted by `(event_date, venue)`
pairs, not bare date, so a double-header day counts as two eligible shows.

`venue_stats.csv` is built from `setlists.csv`'s `venue` column (post-derived),
not the calendar's — the calendar can have the ambiguous multi-venue problem
above; the post never does, it always names one specific venue.

`set_length_stats.csv` buckets shows by `live_end - live_start` from the
calendar (`show_duration()`), rounded to the nearest 5 minutes
(`length_bucket()`). Coverage is inherently partial — only 78/141 shows have
both times in the calendar as of writing — and the report says so explicitly
rather than pretending full coverage. **`avg_songs` excludes SE and Interlude**
(user-specified) — they're categories, not song choices, and would otherwise
inflate the count; `avg_se` tracks SE separately, and `most_common_songs` is
left including them (still informative there). `most_common_songs` per bucket
is each song's *rate within that bucket* (`plays_in_bucket / shows_in_bucket`), not a
raw count, so buckets with different show counts stay comparable.

## `shows.csv` — the canonical show list

Every stats function that needs "which shows exist" was independently
re-grouping `setlists.csv` by `(event_date, venue)` — `build_stats()`,
`build_set_length_stats()`, `build_shows()`, `main()`'s own `shows = {...}`
set. `build_shows()` materializes that grouping into `shows.csv`, one row per
real performance, to directly answer "which show was at which venue" as a
user-facing question.

**The grouping itself is now `show_key()` / `group_shows()`**, and all four
call sites go through them, so "what counts as one show" is defined once.
Note what this deliberately does *not* do: the other functions don't consume
`build_shows()`'s *output*, only the same grouping primitive.
`build_stats()` and `main()` take `rows` alone and have no `calendar` to hand
it, and threading one through purely to reuse a richer return value would
couple song stats to calendar availability for no gain. Sharing the key, not
the row shape, is the part that was actually duplicated.

(`build_venue_stats()` is *not* one of these call sites, despite an earlier
version of this section listing it — it groups by venue with a set of dates,
never by `(event_date, venue)`.)

`venue` in `shows.csv` comes from `setlists.csv`, not `drawry_schedule.csv` —
deliberately. The venue-ambiguity investigation (see above) established that
the calendar's `venue` is sometimes an unresolved list of candidates, while
the post always names one specific venue. Everything else (event name, times,
`length_bucket`) is looked up from the calendar by `event_uid`.

**Known granularity gap, not fixed here:** `drawry_schedule.csv`'s
doors/showtime/live_*/meet_* are per calendar *event*, not per *day*, because
`apply_overrides()` matches an override to a calendar row by that row's own
`start` date — for a multi-day event there's exactly one row, whose `start` is
day 1, so an override can never target day 2 specifically. Both known
multi-day events (2026-04-18/19, 2026-05-23/24) don't currently need
per-day times, so this hasn't forced the issue. If it ever does, the fix is in
`apply_overrides()` — it would need to key on the *show's* date (which
`event_days()` already enumerates) rather than the calendar row's `start`,
which is a real change to how overrides resolve, not a one-line patch.

### Auto-filling `event_overrides.csv`'s gaps

`add_override_templates()` runs unconditionally on every `sync_setlists.py`
call (not behind a flag — it was originally one, but the cross-reference
against the calendar already happens for `set_length_stats.csv`/`shows.csv`,
so gating a second, cheap pass over the same data added friction with no real
safety benefit). It appends an `event_overrides.csv` row for every show whose
calendar entry is missing **`venue`, or any one of the six time fields**
(`doors`, `showtime`, `live_start`, `live_end`, `meet_start`, `meet_end`) —
each field is checked independently (`missing_fields` in the code), not
lumped into a single "has times / doesn't" boolean. A show missing only
`meet_start`/`meet_end` (times otherwise fully known) still gets a row.

Every field the calendar *does* already know is prefilled — not just `venue`,
all six time fields too, via `**{field: cal_row.get(field, "") for field in
time_fields}`. Only fields the calendar genuinely doesn't have come through
blank. This wasn't true at first: an earlier version treated `live_start`/
`live_end` as unconditionally blank, reasoning that they were "the reason the
row exists" — true for rows generated by a missing-*time* trigger, false for
rows generated by a missing-*venue* trigger whose times were already fully
known. The result: 13 rows had a real, already-parsed `live_start`/`live_end`
sitting in `drawry_schedule.csv` that the override row never surfaced — the
user noticed from the outside as "why does this row have `meet_start` but no
`live_start`," which was exactly the tell (meet_start prefilled fine, since
that field's prefill was already unconditional; live_start wasn't).

This function's scope has grown by exactly this pattern twice now — times
only → venue added → every field checked independently — each time triggered
by the user asking some form of "does this actually cover everything." Take
that pattern seriously if a similar question comes up again: the honest
answer has been "no" both times.

**`venue` prefill source depends on why the row exists:** if the calendar has
a venue and it's not ambiguous, use it — it already reflects any override
applied there. If the calendar has **none, or an unresolved multi-venue
string**, fall back to `row["venue"]` (the matched show's setlist-derived
venue) instead of using the useless value — the whole point of a venue gap
firing is that the calendar doesn't know the venue (or knows it ambiguously),
so prefilling from the one source that does is what actually closes the gap.
The other five fields have no equivalent fallback (setlists.csv doesn't carry
times), so they're just prefilled-if-known, blank otherwise.

**Ambiguous venues (`VENUE_AMBIGUOUS`, duplicated from `export_calendar.py`
for the same independence reason as `OVERRIDE_TEMPLATE_FIELDS`) are treated
as a venue gap, same as blank.** This closed a real hole: the 10 ambiguous
venues resolved earlier this session were **entirely manual** — grep for the
warning, read the setlist post, hand-write the override — nothing in the code
did that. `export_calendar.py`'s check only warns, it never resolves; the old
`needs_venue = not cal_row.get("venue", "").strip()` only caught a *blank*
venue, and an ambiguous string isn't blank, so it never triggered the
fallback either. The user asked directly whether those 10 were "completed by
you instead of any of our code" — yes, they were, and that's what this fixes.
Verified by deleting a resolved row and confirming
`add_override_templates()` regenerates it byte-identical from
`setlists.csv` alone, no manual step required.

Leaving a prefilled `venue` as-is has no behavioral consequence when it came
from the calendar (`apply_overrides()` treats blank as "keep the parsed
value," and the parsed value already *is* what got prefilled) — but **when it
came from the setlist-venue fallback, leaving it as-is is what actually
applies it**; the calendar's blank venue only gets fixed if this override
survives. Don't treat "prefilled = no-op" as true for venue-gap rows the way
it is for rows whose venue simply mirrors what the calendar already had.

**Getting the *lookup key* wrong is a
different story** — an earlier one-off backfill script for pre-existing rows
keyed by `summary` alone (not `(date, summary)`), which silently returns the
wrong venue for any recurring event title reused across dates with different
venues (`TOKYO BEATREC`, `ASTROPUFF`, `#ﾆｷﾌﾟﾚ『シキサイ。』` and others repeat).
Worse, a redo of that backfill matched by *exact* `summary` equality against a
hand-typed `match` that was a deliberate *substring*, missed, and overwrote a
real hand-entered venue with blank. Both mistakes happened outside
`add_override_templates()` itself (which is correct — see below) in
throwaway migration scripts; if you ever need to backfill or repair existing
rows again, match on `(date, match)` using **substring** containment
(`match in summary`), the same rule `apply_overrides()` uses, and do it
against a scratch copy first.

**Rewritten every run, sorted incomplete-rows-first — but never edits an
existing row's fields, keyed on `(date, match)` already present in the
file.** Originally this was pure append (write mode `"a"`), which is what
caused the user's next report: after several rounds of prefill widening
(venue, then times), many rows ended up fully resolved without the user
having typed anything — but append-only meant they stayed scattered
chronologically among the rows still needing input, indistinguishable at a
glance from ones needing attention. The fix sorts by `not needs_anything(row)`
first, `date` second — every row still missing something floats to the top,
resolved rows sink to the bottom. Rewriting the whole file (not appending) is
what makes reordering possible; it's still safe because no row's *content* is
ever touched, only which position it's written at — content changes still
only come from a genuinely new row being added or an explicit fix elsewhere.
A show that already satisfies every field (times and venue, from the original
parse or an earlier override) is skipped for *new*-row generation exactly as
before; the "0 new rows" case is now reported as `N/M rows still need
something` instead, which is the more useful number.

**A real bug from exactly this class of mistake, caught and fixed:** when the
10 newly-detected ambiguous-venue events (see above) were resolved, a one-off
script appended a *new* row for each instead of checking whether one already
existed — 2025-11-02 already had an `add_override_templates()` row from
before the ambiguity regex was widened (`venue` still the raw unresolved
joined string), so the fix added a second, correct row next to the first
rather than replacing it. Two rows with the same `(date, match)` both got
applied by `apply_overrides()` (later one in the CSV wins, so behavior was
accidentally correct), but the file was wrong until the duplicate was found
and removed. Any script that touches `event_overrides.csv` outside
`add_override_templates()` itself must check `(date, match)` against existing
rows before appending, not just assume it's new.

**Standing rule, learned the hard way twice: every time this function's
prefill logic gains a new field, existing rows are permanently stuck without
it.** Append-only means old rows are never revisited, so improving what gets
prefilled for *new* rows does nothing for rows created before the change.
Happened for `venue` (rows existed with it blank before the calendar-blank
fallback was added) and again for `doors`/`showtime`/`meet_*` (this section) —
both needed a manual one-time backfill afterward, and the venue one initially
missed 21 more wrong/stale rows because the first backfill attempt checked
against `drawry_schedule.csv`'s own venue column instead of `setlists.csv` —
and `drawry_schedule.csv` had *already absorbed* a wrong override from a
previous mistake, so it just confirmed its own error back to itself. **Always
verify a backfill against `setlists.csv` (independent of any override chain),
never against `drawry_schedule.csv` (contaminated by whatever's currently in
`event_overrides.csv`).** After adding a new prefill field here, grep for
existing rows that would qualify and check whether they need the same
one-time fix.

`OVERRIDE_TEMPLATE_FIELDS` duplicates `export_calendar.py`'s override column
order rather than importing it — the two scripts are deliberately independent
(see the constraints section above). Keep them in sync by hand if
`OVERRIDE_FIELDS` there ever changes.

Scope was originally "shows with a pasted setlist" only — a show with no
setlist isn't in `set_length_stats.csv`'s population, so a row for it didn't
unblock anything *there*. Widened on request to every `is_show()` calendar
event regardless of setlist status: the user wanted to fix up pending/
no-setlist shows' venue and times too, not just ones that already have a
paste. The only behavioral difference between the two: a setlisted show
falls back to its setlist-derived venue when the calendar's is blank/
ambiguous (`venue_by_uid`, built from `rows`/setlists.csv); a setlist-less
show has no such fallback and that field is just left blank for the user to
type in. The loop itself now walks `calendar` directly (filtered by
`is_show()`) rather than deriving which UIDs exist from `rows` first — a
setlist-less show never appears in `rows` at all, so that was the actual
blocker before.

**Known, accepted risk from this widening:** a pending show's calendar entry
is still being actively edited by the band right up until the show happens —
literally observed the same day this was widened, when a pending event's
description gained its live/meet times between two fetches. `export_
calendar.py`'s `apply_overrides()` only treats a *blank* override cell as
"keep whatever the calendar currently says"; any cell this function prefilled
non-blank (venue, doors, showtime — whatever the calendar already knew at
generation time) is frozen from then on and will keep silently overriding a
later calendar correction to that same field, with no warning. This risk
technically existed before too, but only mattered for past/setlisted shows,
whose calendar data is essentially frozen once the show has happened;
widening scope to pending shows makes it real rather than theoretical.
Raised with the user and deliberately left as-is (accepted the risk over
losing the at-a-glance prefilled preview) — if a pending show's info looks
wrong on the site despite the calendar itself being correct, check here
first before re-debugging the parser.

**A show's *title* changing is handled differently from its venue/times
changing, on the user's explicit instruction:** `match` gets updated in
place — unlike every other field, which is frozen once prefilled (see
above) — because an unrenewed `match` doesn't just go stale, it breaks
matching entirely (`apply_overrides()` reports "matched no event — stale?"
and skips the row, silently dropping the venue/times it was carrying too).

First implemented as a heuristic (pairing an "orphaned" row — its `match` no
longer found in any of that date's current show titles — with an
"unmatched" show on that date, only when there was exactly one of each,
since `event_overrides.csv` had no uid to match on directly). The user then
pointed out a uid column was fine to add for exactly this bookkeeping, so
it's now an exact lookup instead: a trailing `uid` column (`OVERRIDE_
TEMPLATE_FIELDS`) that `export_calendar.py` never reads and the two scripts
therefore don't need to keep in sync on. A row's uid never changes across a
rename, so once known, matching is exact — no more guessing which orphan
pairs with which unmatched show. A row written before this column existed
gets one backfilled the first time it's seen, the same way `apply_
overrides()` itself matches an override: a unique (date, match-is-a-
substring-of-summary) pair; ambiguous or no match just leaves it uid-less,
same as before the column existed.

**Deliberately keyed by (uid, date), not uid alone** — this was the other
half of the user's guidance. A two-day event is one calendar row/uid but can
need two override rows, one per day: `apply_overrides()` itself still only
matches an override to a calendar row by that row's own start date (a real,
separate, deliberately-not-fixed-here gap — see the shows.csv section
above), so a day-2 override has to be hand-added today, dated for day 2,
sharing the same uid as day 1's row. Keying the live-show lookup on uid
alone would treat that legitimate one-uid/two-rows case as a conflict
instead of two independent, both-valid entries; keying on (uid, date), built
from `event_days()` rather than just the calendar row's own `start`, keeps
them properly independent.

Venue and every time field on a renamed row are left exactly as they
were — a title change says nothing about whether those also changed, and
this doesn't try to guess at that too. Reported unconditionally (not gated
by `--quiet`) as `override renamed {date}: {old!r} -> {new!r}`.

## Coverage reporting

`--missing` answers "which shows lack a setlist". Two things make it useful
rather than noise:

- **Non-shows are filtered** (`is_show()`): `×`/`△` availability placeholders,
  特典会, 配信, オフ会, solo-member events, product releases. ~35 of 177 past
  events. Extend `NON_SHOW_MARKERS` as new kinds appear — but prefer a false
  positive (a non-show left in the list) over hiding a real gap, since the list
  exists for the user to eyeball.
- `NON_SHOW_SUFFIXES` is matched with `endswith`, not `in`, specifically to
  separate `…「First Lines」リリース` (a product release, user-confirmed not an
  event) from `【リリースイベント】タワーレコード新宿店` (an in-store appearance
  that plausibly had a setlist).

`--missing` used to split output at the earliest pasted setlist (events older
than that were "not pasted yet" rather than gaps). Removed once the paste
archive reached the band's actual debut (2025-09-13) — nothing can be older
than that, so the split had nothing left to do. If the paste archive ever stops
covering back to the debut again, that's the signal to reintroduce it, not a
sign something broke.

## Verifying changes

There's no test suite. After touching either parser:

```sh
python3 pipeline/export_calendar.py            # expect "up to date" on a no-op run
python3 pipeline/sync_setlists.py              # 141 shows, 1021 songs (raw post count varies with paste-file layout)
python3 pipeline/sync_setlists.py --missing    # coverage + typo flags
```

Counts grow as pastes are added — check that nothing *regresses* (posts
skipped, shows unmatched, songs lost), not that they match exactly.

**Always run the dropped-line audit after touching `parse_post`.** Counts alone
will not catch a song line the regexes stopped matching:

```python
import sys; sys.path.insert(0, 'pipeline')
import sync_setlists as s
for b in s.split_posts(open('data/input/setlist_posts/2026-08-17.txt', encoding='utf-8').read()):
    post = s.parse_post(b, 'x')
    hdr = [i for i, l in enumerate(b) if s.DATE_LINE.match(l)][0]
    started = False
    for l in b[hdr + 1:]:
        if s.SONG_LINE.match(l) or s.ENCORE_LINE.match(l):
            started = True
        elif started and l.strip():
            print(f"DROPPED [{post['month']}/{post['day']}]: {l!r}")
```

Expected output: nothing.
