#!/usr/bin/env python3
"""Parse setlist posts pasted from X (#Drawryセトリ) into a per-song CSV.

Workflow: select posts on the X search page, copy, and paste them into a new
file under setlist_posts/ (any filename, .txt). Formatting loss is fine — the
parser keys off the 【セットリスト】 header and the date line inside each post.
Then run this script. It is append-only and idempotent: re-pasting posts you
already captured is harmless, they dedupe.

Each song becomes one row in setlists.csv, linked to the calendar event by uid
so setlists and schedule stay joinable.

Usage:
    ./sync_setlists.py                # parse setlist_posts/ -> setlists.csv + song_stats.csv
    ./sync_setlists.py --missing      # also list past events with no setlist
"""

from __future__ import annotations

import argparse
import csv
import difflib
import glob
import os
import re
import sys
from collections import Counter
from datetime import date, datetime, timedelta

# Calendar entries that are not performances, so their lack of a setlist is
# expected rather than a gap. `×` / `△` / `○` are availability placeholders.
NON_SHOW_EXACT = {"×", "✕", "x", "△", "○", "◯", "?", "？"}
NON_SHOW_MARKERS = (
    "特典会",
    "オフ会",
    "配信",
    "生誕祭",
    "リリイベ",
    "お渡し会",
    "撮影会",
    "握手会",
    "ソロイベント",
    "出演イベント",
    "弾き語り",
    "発売",
    "オープン",
    "ライブ予定なし",
)
# Checked as a suffix, not a substring: a title *ending* in リリース is a product
# release ("会場限定1st EP「First Lines」リリース"), whereas 【リリースイベント】 is
# an in-store appearance that may well have a setlist.
NON_SHOW_SUFFIXES = ("リリース",)

# Paths resolve against the repo root, not the working directory, so the
# script works the same from anywhere (cron included — no `cd` needed).
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_DIR = os.path.join(ROOT, "data", "input")
GENERATED_DIR = os.path.join(ROOT, "data", "generated")

POSTS_DIR = os.path.join(INPUT_DIR, "setlist_posts")
CORRECTIONS_CSV = os.path.join(INPUT_DIR, "song_corrections.csv")
VENUE_CORRECTIONS_CSV = os.path.join(INPUT_DIR, "venue_corrections.csv")
EVENT_OVERRIDES_CSV = os.path.join(INPUT_DIR, "event_overrides.csv")

CALENDAR_CSV = os.path.join(GENERATED_DIR, "drawry_schedule.csv")
OUTPUT_CSV = os.path.join(GENERATED_DIR, "setlists.csv")
STATS_CSV = os.path.join(GENERATED_DIR, "song_stats.csv")
VENUE_STATS_CSV = os.path.join(GENERATED_DIR, "venue_stats.csv")
VENUE_REVIEW_CSV = os.path.join(GENERATED_DIR, "venue_review.csv")
SET_LENGTH_STATS_CSV = os.path.join(GENERATED_DIR, "set_length_stats.csv")
SHOWS_CSV = os.path.join(GENERATED_DIR, "shows.csv")


def rel(path: str) -> str:
    """Show paths relative to the repo root — absolute ones make the run
    output unreadable now that files live in data/input and data/generated."""
    try:
        return os.path.relpath(path, ROOT)
    except ValueError:
        return path


COLUMNS = [
    "event_date",
    "live_start",
    "showtime",
    "event_uid",
    "position",
    "song",
    "corrected_from",
    "is_se",
    "is_interlude",
    "is_encore",
    "note",
    "venue",
    "post_event_name",
    "calendar_summary",
    "source_file",
]

SETLIST_HEADER = "【セットリスト】"
# "8月16日(日)@ LIVLIV(静岡ARTIE)" -> month, day, venue
DATE_LINE = re.compile(r"^(\d{1,2})月(\d{1,2})日\s*(?:[（(][^）)]*[）)])?\s*(?:[@＠]\s*(.*))?$")
# "01. SE(Draw a Story)" / "1.曲名" / "M1. 曲名"
SONG_LINE = re.compile(r"^[MmＭ]?\s*(\d{1,2})\s*[.。、．)）:：]\s*(.+)$")
# "En. Moving Lights!" / "Encore: 曲名" / "アンコール1. 曲名" — encores are not
# numbered in sequence, so they need their own anchor or they vanish silently.
ENCORE_LINE = re.compile(
    r"^(?:En|Enc|Encore|EN|アンコール|アンコ)\s*\d{0,2}\s*[.。、．)）:：]\s*(.+)$",
    re.IGNORECASE,
)
# "SE(スタンドバイミー)" -> the SE's source track
SE_TRACK = re.compile(r"^SE\s*[(（]\s*(.+?)\s*[)）]\s*$", re.IGNORECASE)
# Trailing performance annotation, e.g. "(初披露)" or "(拡張イントロ)". Keyword-
# gated on purpose: a bare trailing paren is often part of the title itself
# (every "SE(曲名)" is), so only these performance words split off.
SONG_NOTE = re.compile(
    r"^(.*?)\s*[(（]\s*([^)）]*"
    r"(?:初披露|新曲|カバー|披露|イントロ|アウトロ|アレンジ|アカペラ|バージョン|ver\.?)"
    r"[^)）]*)\s*[)）]\s*$",
    re.IGNORECASE,
)
# "SE(Moving Lights!) ※New" — an annotation appended with ※ rather than parens.
# Anything after ※ is commentary, never part of the title.
SONG_ASIDE = re.compile(r"^(.*?)\s*[※*]\s*(.+?)\s*$")
# Bare section-header lines a few posts use to set off a pre-set segment (a
# talk segment with a song played before the numbered main set). They stop
# event-name accumulation and, for トークパート, label any song line that
# follows until the next section header — that's how "トークパート" attaches
# to the acoustic song beneath it instead of being read as part of the event
# name (see 2026-04-04@下北沢MOSAiC).
SECTION_LABELS = {"トークパート": "トークパート", "本編": None}
# "SEなし" is a remark, not part of the event name; the absence of SE rows
# already records it.
NOISE_LINES = {
    "Show more",
    "Show less",
    "Translate post",
    "·",
    "",
    "SEなし",
    "SE無し",
    "SEなし。",
}


def normalize(text: str) -> str:
    """Half-width the digits so full-width post text still matches."""
    return text.translate(str.maketrans("０１２３４５６７８９", "0123456789"))


def split_posts(text: str) -> list[list[str]]:
    """Return each post's body: the lines after 【セットリスト】, up to its tags."""
    lines = [line.strip() for line in normalize(text).replace("\r\n", "\n").split("\n")]
    lines = [line for line in lines if line not in NOISE_LINES]

    starts = [i for i, line in enumerate(lines) if SETLIST_HEADER in line]
    posts = []
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        body = []
        started = False
        for line in lines[start + 1 : end]:
            # The trailing hashtag line closes the post; the author block of the
            # next post follows it and must not be read as setlist content.
            # Only treat hashtags as the terminator once songs have started —
            # some event names are themselves hashtags ("#ﾆｷﾌﾟﾚ『シキサイ。』").
            if started and line.startswith("#") and all(
                token.startswith("#") for token in line.split()
            ):
                break
            if line.startswith("#") and "セトリ" in line:
                break
            started = started or bool(SONG_LINE.match(line) or ENCORE_LINE.match(line))
            body.append(line)
        if body:
            posts.append(body)
    return posts


def parse_song(raw: str) -> tuple[str, bool, str]:
    """Return (song, is_se, note) for one numbered line's text."""
    notes = []
    aside = SONG_ASIDE.match(raw)
    if aside:
        raw, aside_note = aside.group(1).strip(), aside.group(2).strip()
        notes.append(aside_note)

    match = SONG_NOTE.match(raw)
    if match:
        raw, paren_note = match.group(1).strip(), match.group(2).strip()
        notes.insert(0, paren_note)
    note = "; ".join(notes)

    # An SE is its own track, distinct from the song it draws on, so keep the
    # name verbatim — "SE(Draw a Story)" never collapses into "Draw a Story".
    if SE_TRACK.match(raw) or raw.upper() == "SE":
        return raw.strip(), True, note
    return raw.strip(), False, note


def parse_post(body: list[str], source: str) -> dict | None:
    """Turn one post body into {month, day, venue, event_name, songs}."""
    header = None
    header_index = 0
    for i, line in enumerate(body):
        match = DATE_LINE.match(line)
        if match:
            header, header_index = match, i
            break
    if header is None:
        return None

    month, day = int(header.group(1)), int(header.group(2))
    venue = (header.group(3) or "").strip()

    songs: list[tuple[int, str, bool, str, bool]] = []
    name_parts: list[str] = []
    section_note: str | None = None
    for line in body[header_index + 1 :]:
        if line in SECTION_LABELS:
            section_note = SECTION_LABELS[line]
            continue
        match = SONG_LINE.match(line)
        encore = ENCORE_LINE.match(line) if not match else None
        if match or encore:
            raw = match.group(2) if match else encore.group(1)
            song, is_se, note = parse_song(raw)
            if song:
                if section_note:
                    note = "; ".join(n for n in (section_note, note) if n)
                # Encores restart or omit numbering, so keep counting from the
                # main set to preserve true running order.
                position = int(match.group(1)) if match else len(songs) + 1
                songs.append((position, song, is_se, note, bool(encore)))
        elif section_note:
            # An unnumbered song inside a labelled section (e.g. a talk-part
            # performance) — treat it as a song rather than swallowing it
            # into the event name.
            song, is_se, note = parse_song(line)
            if song:
                note = "; ".join(n for n in (section_note, note) if n)
                songs.append((len(songs) + 1, song, is_se, note, False))
        elif not songs:
            # Lines between the date line and the first song are the event name.
            name_parts.append(line)
    if not songs:
        return None

    # The posted numbers are labels and are sometimes wrong (real posts have
    # "01, 02, 02, 03"). Running order is what `position` means, so derive it
    # from order of appearance and report numbering that disagrees.
    posted = [number for number, *_ in songs]
    songs = [(i + 1, *rest) for i, (_, *rest) in enumerate(songs)]

    return {
        "month": month,
        "day": day,
        "venue": venue,
        "event_name": " ".join(name_parts).strip(),
        "songs": songs,
        "posted_numbering": posted if posted != list(range(1, len(songs) + 1)) else None,
        "source": source,
    }


def is_interlude(song: str) -> bool:
    """Interludes are a category, not one track.

    The posts write every one as a bare "Interlude", so separate interludes are
    indistinguishable by name. That is why the same name carries a 初披露 tag on
    more than one date — those are different pieces, not a mistake.
    """
    return song.lower().startswith("interlude")


def load_corrections(path: str) -> dict[str, str]:
    """Read the wrong -> correct song name map, if the file exists."""
    if not os.path.exists(path):
        return {}
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return {
            row["wrong"].strip(): row["correct"].strip()
            for row in csv.DictReader(fh)
            if row.get("wrong") and row.get("correct")
        }


def load_calendar(path: str) -> list[dict[str, str]]:
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return [row for row in csv.DictReader(fh) if row.get("start")]


def event_days(row: dict[str, str]) -> list[date]:
    """Every date a calendar event covers (its `end` is inclusive in our CSV)."""
    try:
        start = date.fromisoformat(row["start"][:10])
        end = date.fromisoformat((row.get("end") or "")[:10]) if row.get("end") else start
    except ValueError:
        return []
    if end < start:
        end = start
    span = min((end - start).days, 31)
    return [start + timedelta(days=n) for n in range(span + 1)]


def match_score(post: dict, row: dict[str, str]) -> float:
    """How well a post matches one calendar event, for same-day tie-breaks.

    The calendar's description repeats the venue, which is the strongest signal;
    the event name is a weaker one because the two sources abbreviate it
    differently.
    """
    haystack = f"{row.get('summary', '')} {row.get('description', '')}".lower()
    score = 0.0
    venue = post["venue"].lower().strip()
    if venue:
        if venue in haystack:
            score += 2.0
        else:
            score += difflib.SequenceMatcher(None, venue, haystack).ratio()
    if post["event_name"]:
        score += difflib.SequenceMatcher(
            None, post["event_name"], row.get("summary", "")
        ).ratio()
    return score


def resolve_date(
    post: dict, calendar: list[dict[str, str]], today: date
) -> tuple[str, str, str, dict[str, str]]:
    """Posts carry no year. Use the calendar as the oracle, else nearest past.

    Returns (iso_date, event_uid, calendar_summary, {live_start, showtime}).
    """
    month, day = post["month"], post["day"]
    # Match anywhere inside an event's span, not just its start day: a two-day
    # festival is one calendar entry but gets a setlist post per day.
    matches = [
        (day_of, row)
        for row in calendar
        for day_of in event_days(row)
        if day_of.month == month and day_of.day == day
    ]
    if matches:
        # Prefer the most recent occurrence that has already happened.
        past = [pair for pair in matches if pair[0] <= today]
        day_of = max(pair[0] for pair in (past or matches))
        # A date alone is not always unique — the band plays two events on the
        # same day fairly often. Pick by venue and event name in that case.
        same_day = [row for when, row in matches if when == day_of]
        best = (
            max(same_day, key=lambda row: match_score(post, row))
            if len(same_day) > 1
            else same_day[0]
        )
        return (
            day_of.isoformat(),
            best.get("uid", ""),
            best.get("summary", ""),
            {
                "live_start": best.get("live_start", ""),
                "showtime": best.get("showtime", "") or best.get("doors", ""),
            },
        )

    for year in (today.year, today.year - 1, today.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue
        if candidate <= today:
            return candidate.isoformat(), "", "", {"live_start": "", "showtime": ""}
    empty = {"live_start": "", "showtime": ""}
    return date(today.year - 1, month, day).isoformat(), "", "", empty


def build_rows(
    posts_dir: str,
    calendar: list[dict[str, str]],
    today: date,
    corrections: dict[str, str],
    venue_corrections: dict[str, str],
):
    rows: list[dict[str, str]] = []
    applied: Counter[str] = Counter()
    venues_applied: Counter[str] = Counter()
    seen: dict[tuple, tuple[str, ...]] = {}
    parsed = skipped = duplicates = 0
    conflicts: list[str] = []
    numbering: list[str] = []

    for path in sorted(glob.glob(os.path.join(posts_dir, "*.txt"))):
        source = os.path.basename(path)
        with open(path, encoding="utf-8") as fh:
            bodies = split_posts(fh.read())
        for body in bodies:
            post = parse_post(body, source)
            if post is None:
                skipped += 1
                continue
            parsed += 1

            iso, uid, summary, times = resolve_date(post, calendar, today)
            songs = tuple(song for _, song, _, _, _ in post["songs"])
            key = (iso, post["venue"])
            if key in seen:
                duplicates += 1
                if seen[key] != songs:
                    conflicts.append(f"{iso} @ {post['venue']} — two pastes disagree")
                continue
            seen[key] = songs
            # Corrected for display/stats only — matching above already ran on
            # the raw text, which is more likely to appear verbatim in the
            # calendar description than a canonicalized name would be.
            venue = venue_corrections.get(post["venue"], post["venue"])
            if venue != post["venue"]:
                venues_applied[post["venue"]] += 1
            if post["posted_numbering"]:
                numbering.append(
                    f"{iso} @ {post['venue']} — post numbers them "
                    f"{','.join(str(n) for n in post['posted_numbering'])}"
                )

            for position, song, is_se, note, is_encore in post["songs"]:
                # Correct known typos, but keep what was posted in its own
                # column so the CSV never loses the original.
                original = song
                song = corrections.get(song, song)
                if song != original:
                    applied[original] += 1
                rows.append(
                    {
                        "event_date": iso,
                        "live_start": times["live_start"],
                        "showtime": times["showtime"],
                        "event_uid": uid,
                        "position": str(position),
                        "song": song,
                        "corrected_from": original if song != original else "",
                        "is_se": "yes" if is_se else "no",
                        "is_interlude": "yes" if is_interlude(song) else "no",
                        "is_encore": "yes" if is_encore else "no",
                        "note": note,
                        "venue": venue,
                        "post_event_name": post["event_name"],
                        "calendar_summary": summary,
                        "source_file": source,
                    }
                )

    # Sort by when the band actually played so two shows on one day stay as two
    # blocks instead of interleaving by position. Their own slot beats the
    # event's showtime, which two events on a day can share. Untimed last.
    rows.sort(
        key=lambda row: (
            row["event_date"],
            row["live_start"] or row["showtime"] or "~",
            row["venue"],
            int(row["position"]),
        )
    )
    return rows, {
        "parsed": parsed,
        "skipped": skipped,
        "duplicates": duplicates,
        "conflicts": conflicts,
        "numbering": numbering,
        "applied": applied,
        "venues_applied": venues_applied,
    }


def build_stats(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[str]]:
    """One row per track: play counts and the dates it was first/last performed."""
    plays: Counter[str] = Counter()
    encores: Counter[str] = Counter()
    shows: dict[str, set[tuple[str, str]]] = {}
    first: dict[str, str] = {}
    last: dict[str, str] = {}
    marked: dict[str, str] = {}
    flags: dict[str, tuple[str, str]] = {}
    all_shows: set[tuple[str, str]] = set()

    for row in rows:
        song, when = row["song"], row["event_date"]
        show = (when, row["venue"])
        all_shows.add(show)
        plays[song] += 1
        shows.setdefault(song, set()).add(show)
        first[song] = min(when, first.get(song, when))
        last[song] = max(when, last.get(song, when))
        flags[song] = (row["is_se"], row["is_interlude"])
        if row["is_encore"] == "yes":
            encores[song] += 1
        if "初披露" in row["note"]:
            marked[song] = min(when, marked.get(song, when))

    stats = []
    notes = []
    for song, count in plays.most_common():
        # A debut is "confirmed" when the band tagged that same performance
        # 初披露; otherwise first_performed is only a lower bound, limited by
        # how far back the pastes go.
        confirmed = marked.get(song) == first[song]
        # Of all the shows that happened on or after this song's debut, what
        # share actually included it? Fairer than a raw play count for
        # comparing an old staple against a track introduced last month.
        eligible = sum(1 for when, _ in all_shows if when >= first[song])
        stats.append(
            {
                "song": song,
                "plays": str(count),
                "shows": str(len(shows[song])),
                "shows_since_debut": str(eligible),
                "play_rate": f"{len(shows[song]) / eligible:.2f}" if eligible else "",
                "first_performed": first[song],
                "last_performed": last[song],
                "debut_confirmed": "yes" if confirmed else "no",
                "encores": str(encores[song]),
                "is_se": flags[song][0],
                "is_interlude": flags[song][1],
            }
        )
        # SE and Interlude are categories rather than single tracks, so a later
        # 初披露 under the same name is a different piece, not a contradiction.
        if (
            song in marked
            and not confirmed
            and not is_interlude(song)
            and not song.startswith("SE")
        ):
            notes.append(
                f"{song!r} is tagged 初披露 on {marked[song]} but was already "
                f"played on {first[song]} — the marker looks wrong"
            )
    return stats, notes


def build_shows(
    rows: list[dict[str, str]], calendar: list[dict[str, str]]
) -> list[dict[str, str]]:
    """One row per actual performance — the canonical answer to "which show
    was at which venue" that nothing else in this file has to re-derive.

    `drawry_schedule.csv` is one row per *calendar event*, not per show (a
    2-day event is one row covering both days); `setlists.csv` is one row per
    *song*. A show only exists implicitly, as a group of setlist rows sharing
    (event_date, venue) — every stats function that needs "how many shows"
    re-groups it that way itself. This materializes that grouping once.

    `venue` here is setlists.csv's (post-derived, corrected) venue — the most
    reliable source, per the venue-ambiguity investigation: every ambiguous
    calendar venue found so far was resolved by the setlist post naming one
    specific place, even when the calendar description named several.
    """
    calendar_by_uid = {row["uid"]: row for row in calendar}
    by_show: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in rows:
        by_show.setdefault((row["event_date"], row["venue"]), []).append(row)

    shows = []
    for (when, venue), songs in sorted(by_show.items()):
        first = songs[0]
        cal_row = calendar_by_uid.get(first["event_uid"], {})
        minutes = show_duration(cal_row)
        shows.append(
            {
                "event_date": when,
                "venue": venue,
                "event_uid": first["event_uid"],
                "calendar_summary": first["calendar_summary"],
                "post_event_name": first["post_event_name"],
                "songs": str(len(songs)),
                "se": str(sum(1 for s in songs if s["is_se"] == "yes")),
                "interludes": str(sum(1 for s in songs if s["is_interlude"] == "yes")),
                "encores": str(sum(1 for s in songs if s["is_encore"] == "yes")),
                "doors": cal_row.get("doors", ""),
                "showtime": cal_row.get("showtime", ""),
                "live_start": cal_row.get("live_start", ""),
                "live_end": cal_row.get("live_end", ""),
                "length_bucket": length_bucket(minutes) if minutes is not None else "",
                "source_file": ", ".join(
                    sorted({s["source_file"] for s in songs})
                ),
            }
        )
    return shows


def report_shows(rows: list[dict[str, str]], calendar: list[dict[str, str]], path: str) -> None:
    shows = build_shows(rows, calendar)
    fields = list(shows[0].keys()) if shows else ["event_date", "venue"]
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(shows)
    unlinked = sum(1 for row in shows if not row["event_uid"])
    print(
        f"wrote {rel(path)}: {len(shows)} shows"
        + (f" ({unlinked} not linked to a calendar event)" if unlinked else "")
    )


def build_venue_stats(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """One row per venue: how often the band has played there.

    Sourced from setlists.csv's own `venue` (as written in the post), not the
    calendar's — the post always names one specific venue, so it carries none
    of the calendar description's "duo MUSIC EXCHANGE&SHIBUYA RING" ambiguity.
    """
    # setlists.csv already dedupes to one row-group per (event_date, venue), so
    # within a venue the date alone identifies the show.
    shows: dict[str, set[str]] = {}
    first: dict[str, str] = {}
    last: dict[str, str] = {}
    for row in rows:
        venue, when = row["venue"], row["event_date"]
        if not venue:
            continue
        shows.setdefault(venue, set()).add(when)
        first[venue] = min(when, first.get(venue, when))
        last[venue] = max(when, last.get(venue, when))

    stats = [
        {
            "venue": venue,
            "shows": str(len(dates)),
            "first_played": first[venue],
            "last_played": last[venue],
        }
        for venue, dates in shows.items()
    ]
    stats.sort(key=lambda row: (-int(row["shows"]), row["venue"]))
    return stats


def report_venue_stats(rows: list[dict[str, str]], path: str) -> None:
    stats = build_venue_stats(rows)
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=list(stats[0]) if stats else ["venue"]
        )
        writer.writeheader()
        writer.writerows(stats)
    print(f"wrote {rel(path)}: {len(stats)} venues")


def show_duration(row: dict[str, str]) -> int | None:
    """Minutes between live_start and live_end, if the calendar has both."""
    start, end = row.get("live_start", ""), row.get("live_end", "")
    if not start or not end:
        return None
    fmt = "%H:%M"
    minutes = (datetime.strptime(end, fmt) - datetime.strptime(start, fmt)).total_seconds() / 60
    return int(minutes + (24 * 60 if minutes < 0 else 0))


def length_bucket(minutes: int) -> str:
    return f"{round(minutes / 5) * 5} min"


# Mirrors export_calendar.py's event_overrides.csv header. Not imported from
# there — the two scripts are deliberately independent (see CLAUDE.md).
OVERRIDE_TEMPLATE_FIELDS = [
    "date",
    "match",
    "venue",
    "doors",
    "showtime",
    "live_start",
    "live_end",
    "meet_start",
    "meet_end",
]
# Mirrors export_calendar.py's VENUE_AMBIGUOUS — same reason, not imported.
# That script only detects and warns about an ambiguous venue; it doesn't
# resolve one. This is what actually closes the gap: an ambiguous venue is
# treated the same as a blank one, falling back to the setlist post's venue.
VENUE_AMBIGUOUS = re.compile(r".+[&/、].+")
# Mirrors export_site_data.py's TITLE_BRACKETS/unwrap_quotes — same
# independence reason (that script imports this module, not the other way
# around, so this can't just import theirs). Strips the same presentational
# noise ("【イベント】", wrapping 「」/『』) from a freshly auto-generated
# `match` value, so event_overrides.csv reads like the title actually shown
# on the site instead of the raw calendar summary. apply_overrides() only
# ever needs `match in summary` (a substring test — see export_calendar.py),
# and stripping a prefix/wrapper never removes anything from the *middle* of
# the string, so a stripped value is still guaranteed to be found inside the
# untouched raw summary it came from.
MATCH_TITLE_BRACKETS = re.compile(r"^[(（][^()（）]*[)）]|^【[^【】]*】")
MATCH_QUOTE_PAIRS = {"「": "」", "『": "』"}


def clean_match_title(summary: str) -> str:
    text = summary.strip()
    while True:
        stripped = MATCH_TITLE_BRACKETS.sub("", text).strip()
        if stripped == text:
            break
        text = stripped
    if not text:
        return text
    close = MATCH_QUOTE_PAIRS.get(text[0])
    if not close or text[-1] != close:
        return text
    depth = 0
    for ch in text[1:-1]:
        if ch in MATCH_QUOTE_PAIRS:
            depth += 1
        elif ch in MATCH_QUOTE_PAIRS.values():
            if depth == 0:
                return text
            depth -= 1
    return text[1:-1] if depth == 0 else text


def add_override_templates(
    rows: list[dict[str, str]], calendar: list[dict[str, str]], path: str
) -> None:
    """Append event_overrides.csv rows for shows missing a usable calendar
    venue (blank *or* an unresolved multi-venue string) or any of the six time
    fields (doors/showtime/live_start/live_end/meet_start/meet_end) — so
    `event_overrides.csv` is the complete list of "things worth filling in,"
    and filling one in is a matter of typing into an existing cell rather than
    first figuring out which dates need one at all.

    A row is generated if the calendar is missing *any single* field, not just
    if it's missing every time field — a show can have doors/showtime known
    but be missing only meet_start/meet_end, and that's still worth a row.
    Every field the calendar *does* already know is prefilled, including
    live_start/live_end when those specifically aren't the reason the row
    exists (e.g. a venue-only gap on a show whose times are fully known).

    Only touches shows that have a pasted setlist — a calendar event with no
    setlist yet isn't part of set_length_stats.csv either, so there's nothing
    to unblock by giving it a row.

    The file is rewritten (not appended to) every run, sorted so rows still
    needing something come first — but no *existing row's fields* are ever
    edited or removed, only reordered. Anything already filled in, by hand or
    by an earlier run, survives byte-for-byte; the rewrite only changes row
    order and adds genuinely new rows.
    """
    calendar_by_uid = {row["uid"]: row for row in calendar}
    existing_rows: list[dict[str, str]] = []
    existing: set[tuple[str, str]] = set()
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                existing_rows.append(row)
                existing.add(((row.get("date") or "").strip(), (row.get("match") or "").strip()))

    time_fields = ("doors", "showtime", "live_start", "live_end", "meet_start", "meet_end")
    seen_uids: set[str] = set()
    new_rows = []
    missing_counts = {field: 0 for field in ("venue", *time_fields)}
    for row in sorted(rows, key=lambda r: (r["event_date"], r["venue"])):
        uid = row["event_uid"]
        if not uid or uid in seen_uids:
            continue
        seen_uids.add(uid)
        cal_row = calendar_by_uid.get(uid)
        if not cal_row:
            continue

        missing_fields = [f for f in time_fields if not cal_row.get(f, "").strip()]
        cal_venue = cal_row.get("venue", "").strip()
        # Ambiguous is treated the same as blank: a non-blank but unresolved
        # multi-venue string ("A/B/C") is just as unusable as no venue at all.
        needs_venue = not cal_venue or bool(VENUE_AMBIGUOUS.match(cal_venue))
        if not missing_fields and not needs_venue:
            continue

        when = cal_row["start"][:10]
        match = clean_match_title(cal_row.get("summary", ""))
        if (when, match) in existing:
            continue
        existing.add((when, match))
        missing_counts["venue"] += needs_venue
        for field in missing_fields:
            missing_counts[field] += 1
        new_rows.append(
            {
                "date": when,
                "match": match,
                # If the calendar has no venue at all, prefill from the
                # setlist post instead — it's the more reliable source anyway
                # (see the venue-ambiguity notes) and often already knows the
                # answer the calendar never parsed. Every time field is
                # prefilled from the calendar whenever it has one, whether or
                # not that specific field is why this row exists — a no-op if
                # left as-is (re-asserting the same value shows no change),
                # and one less thing to retype for fields the calendar
                # already answered.
                "venue": row["venue"] if needs_venue else cal_venue,
                **{field: cal_row.get(field, "") for field in time_fields},
            }
        )

    # Rewritten (not appended) every run, in a fixed order: rows still
    # missing something come first (sorted by date), so opening the file
    # shows what needs attention without scrolling past rows that don't.
    # Everything already resolved — hand-typed or filled in by an earlier
    # override script — sorts after, still present (it has to be: several of
    # these encode a permanent fix, like an ambiguous calendar venue, that
    # would silently regress without it) but out of the way.
    def needs_anything(row: dict[str, str]) -> bool:
        return not row.get("venue", "").strip() or any(
            not row.get(field, "").strip() for field in time_fields
        )

    all_rows = existing_rows + new_rows
    all_rows.sort(key=lambda r: (not needs_anything(r), r["date"], r["match"]))

    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=OVERRIDE_TEMPLATE_FIELDS)
        writer.writeheader()
        writer.writerows(all_rows)

    incomplete = sum(1 for r in all_rows if needs_anything(r))
    if new_rows:
        breakdown = ", ".join(
            f"{field}={count}" for field, count in missing_counts.items() if count
        )
        print(f"added {len(new_rows)} rows to {rel(path)} ({breakdown})")
    print(
        f"{rel(path)}: {incomplete}/{len(all_rows)} rows still need something — "
        f"fill in what you know on those"
    )


def build_set_length_stats(
    rows: list[dict[str, str]], calendar: list[dict[str, str]]
) -> tuple[list[dict[str, str]], list[str]]:
    """Group shows by set length (from the calendar's live_start/live_end) and
    report, per bucket, how many songs a set that length tends to have and
    which songs turn up most often.

    Coverage is partial — only shows whose calendar entry states both times.
    """
    calendar_by_uid = {row["uid"]: row for row in calendar}
    by_show: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in rows:
        by_show.setdefault((row["event_date"], row["venue"]), []).append(row)

    buckets: dict[str, dict] = {}
    unmatched = 0
    for (when, venue), songs in by_show.items():
        uid = songs[0]["event_uid"]
        minutes = show_duration(calendar_by_uid.get(uid, {}))
        if minutes is None:
            unmatched += 1
            continue
        bucket = length_bucket(minutes)
        info = buckets.setdefault(
            bucket, {"shows": 0, "songs": 0, "se": 0, "song_counts": Counter()}
        )
        info["shows"] += 1
        # SE and Interlude are categories, not songs — they'd inflate a set's
        # apparent song count without being a song choice.
        info["songs"] += sum(
            1
            for song in songs
            if song["is_se"] == "no" and song["is_interlude"] == "no"
        )
        info["se"] += sum(1 for song in songs if song["is_se"] == "yes")
        for song in songs:
            info["song_counts"][song["song"]] += 1

    stats = []
    for bucket in sorted(buckets, key=lambda b: int(b.split()[0])):
        info = buckets[bucket]
        top = ", ".join(
            f"{song} ({count}/{info['shows']})"
            for song, count in info["song_counts"].most_common(5)
        )
        stats.append(
            {
                "length": bucket,
                "shows": str(info["shows"]),
                "avg_songs": f"{info['songs'] / info['shows']:.1f}",
                "avg_se": f"{info['se'] / info['shows']:.1f}",
                "most_common_songs": top,
            }
        )
    notes = [f"{unmatched} shows have no calendar live_start/live_end, excluded"]
    return stats, notes


def report_set_length_stats(
    rows: list[dict[str, str]], calendar: list[dict[str, str]], path: str
) -> None:
    stats, notes = build_set_length_stats(rows, calendar)
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=list(stats[0]) if stats else ["length"]
        )
        writer.writeheader()
        writer.writerows(stats)
    covered = sum(int(row["shows"]) for row in stats)
    print(f"wrote {rel(path)}: {len(stats)} length buckets over {covered} shows")
    for note in notes:
        print(f"  note: {note}")


def report_stats(rows: list[dict[str, str]], show_count: int, path: str) -> None:
    """Write the per-track stats CSV and print a short summary."""
    stats, notes = build_stats(rows)
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(stats[0]) if stats else ["song"])
        writer.writeheader()
        writer.writerows(stats)

    confirmed = sum(1 for row in stats if row["debut_confirmed"] == "yes")
    print(
        f"wrote {rel(path)}: {len(stats)} tracks over {show_count} shows "
        f"({confirmed} debuts confirmed by a 初披露 tag)"
    )
    for note in notes:
        print(f"  note: {note}")


def is_show(summary: str) -> bool:
    """Would this calendar entry be expected to have a setlist?"""
    text = summary.strip()
    if not text or text in NON_SHOW_EXACT:
        return False
    if text.endswith(NON_SHOW_SUFFIXES):
        return False
    return not any(marker in text for marker in NON_SHOW_MARKERS)


def report_missing(calendar, rows, today: date, show_all: bool) -> None:
    """List past calendar events that have no setlist recorded."""
    covered = {row["event_uid"] for row in rows if row["event_uid"]}
    past = [row for row in calendar if row["start"][:10] <= today.isoformat()]
    missing = [row for row in past if row.get("uid") not in covered]
    have = len(past) - len(missing)
    if not show_all:
        shows = [row for row in missing if is_show(row.get("summary", ""))]
        skipped = len(missing) - len(shows)
        missing = shows
    else:
        skipped = 0

    print(
        f"\nsetlist coverage: {have}/{len(past)} past events have a setlist"
        + (f" ({skipped} non-show entries ignored)" if skipped else "")
    )
    if not missing:
        print("  nothing missing")
        return

    print(f"  {len(missing)} without a setlist:")
    for row in missing:
        print(f"    {row['start'][:10]}  {row.get('summary', '')[:60]}")
    if not show_all:
        print("  (--missing-all also includes 特典会/配信/× placeholder entries)")


def report_typos(rows: list[dict[str, str]]) -> None:
    """Flag near-identical song names — usually a typo in the source post."""
    counts = Counter(row["song"] for row in rows)
    # An SE shares its name with the song it draws on, which is a real
    # distinction, not a typo — only compare like with like.
    se_names = {row["song"] for row in rows if row["is_se"] == "yes"}
    names = sorted(counts, key=lambda name: -counts[name])
    flagged: set[str] = set()
    for i, name in enumerate(names):
        for other in names[i + 1 :]:
            if other in flagged or counts[other] > 2:
                continue
            if (name in se_names) != (other in se_names):
                continue
            if difflib.SequenceMatcher(None, name, other).ratio() >= 0.85:
                flagged.add(other)
                print(
                    f"  possible typo: {other!r} ({counts[other]}x) "
                    f"vs {name!r} ({counts[name]}x)"
                )


VENUE_TOKEN = re.compile(r"[A-Za-z0-9]+")
# Neighborhood/city names, romaji and kanji. These are common enough across
# unrelated venues that leaving them in makes the ratio/substring/token
# heuristics below false-positive freely: "SHIBUYA" alone chained nine
# distinct venues into one cluster, and "アメリカ村" pulled a third, unrelated
# venue into what should've been a 2-member group. Stripped before comparing
# — not a claim of completeness, extend as new areas show up in false
# positives.
VENUE_AREA_WORDS = {
    "渋谷", "SHIBUYA", "下北沢", "SHIMOKITAZAWA", "大塚", "OTSUKA", "恵比寿", "EBISU",
    "銀座", "GINZA", "新宿", "SHINJUKU", "アメリカ村", "神田", "KANDA", "池袋",
    "IKEBUKURO", "表参道", "OMOTESANDO", "高円寺", "KOENJI", "青山", "AOYAMA",
    "心斎橋", "SHINSAIBASHI", "白金高輪", "四谷", "YOTSUYA", "京都", "KYOTO", "新代田",
    "お台場", "ODAIBA", "秋葉原", "AKIHABARA", "六本木", "ROPPONGI", "原宿",
    "HARAJUKU", "中野", "NAKANO", "吉祥寺", "KICHIJOJI", "横浜", "YOKOHAMA", "大阪",
    "OSAKA", "名古屋", "NAGOYA",
}
_AREA_PATTERN = re.compile(
    "|".join(re.escape(w) for w in sorted(VENUE_AREA_WORDS, key=len, reverse=True)),
    re.IGNORECASE,
)
# Live-house brand words that recur across many unrelated physical venues
# ("LOFT" is a nationwide chain — 新宿LOFT and 下北沢Flowers Loft are different
# buildings, not a spelling variant of each other). A short generic word like
# this can still pass the length-4 substring gate below, so it needs its own
# check: if the *entire* shorter name reduces to one of these, that alone
# isn't evidence, however it wasn't disqualified by any other test.
VENUE_GENERIC_WORDS = {"LOFT", "HALL", "STUDIO", "CLUB", "LIVE", "THEATER", "THEATRE"}


def strip_area(name: str) -> str:
    stripped = _AREA_PATTERN.sub("", name).strip()
    # Don't hand back an empty string just because the name is *only* an area
    # word plus punctuation — comparing "" to anything is meaningless.
    return stripped if len(stripped) >= 2 else name


def venue_related(a: str, b: str) -> bool:
    """True if two venue names look like they could be the same place.

    Three independent signals, since no one of them covers every real case:
    - fuzzy ratio: catches spacing/case/half-width variants and typos
      ("大塚Heats+" vs "大塚Hearts+", "渋谷Spotify O-Crest" vs "Spotify O-Crest")
    - substring: catches a short name inside a longer, more specific one
      ("DESEO mini" is not fuzzy-similar to "DESEO mini with VILLAGE
      VANGUARD" — length difference tanks the ratio — but is a clean
      containment)
    - shared distinctive token: catches "SHIBUYA DESEO" alongside the above,
      which is neither a substring nor fuzzy-similar to either. Tokens under
      5 chars are excluded so generic words ("mini", "live", "hall") can't
      chain unrelated venues together.

    All three run on the area-stripped name — otherwise a shared
    neighborhood, not a shared venue, is enough to match.
    """
    a2, b2 = strip_area(a), strip_area(b)
    # 0.75 (not the 0.6 an early version used): the true positives only ratio
    # catches (not substring) bottom out at 0.75 ("下北沢Flowers Loft" vs
    # "Flowers LOFT"); the false positives it let through as low as 0.6
    # topped out at 0.67 ("大塚Hearts+" vs "Veats SHIBUYA", "下北沢ADRIFT" vs
    # "渋谷GRIT") — coincidental shared letters between short unrelated names.
    if difflib.SequenceMatcher(None, a2, b2).ratio() >= 0.75:
        return True
    # Minimum length 4 so a short generic facility-type suffix left over after
    # area-stripping doesn't match everything that ends in it — "渋谷音楽堂"
    # ("concert hall") stripped to "音楽堂" (3 chars) was a substring of an
    # unrelated venue's full name and wrongly clustered them. The shorter side
    # also can't be *only* a chain-brand word ("新宿LOFT" strips to "LOFT",
    # which is a real substring of "下北沢Flowers LOFT" — a coincidence of both
    # using the same chain name, not the same building).
    shorter = a2 if len(a2) <= len(b2) else b2
    if (
        len(a2) >= 4
        and len(b2) >= 4
        and shorter.upper() not in VENUE_GENERIC_WORDS
        and (a2 in b2 or b2 in a2)
    ):
        return True
    tokens_a = {
        t.upper()
        for t in VENUE_TOKEN.findall(a2)
        if len(t) >= 5 and t.upper() not in VENUE_GENERIC_WORDS
    }
    tokens_b = {
        t.upper()
        for t in VENUE_TOKEN.findall(b2)
        if len(t) >= 5 and t.upper() not in VENUE_GENERIC_WORDS
    }
    return bool(tokens_a & tokens_b)


def cluster_venues(venue_counts: dict[str, int]) -> dict[str, int]:
    """Union-find over `venue_related`. Returns venue -> cluster id, only for
    venues that share a cluster with at least one other venue."""
    names = list(venue_counts)
    parent = {name: name for name in names}

    def find(name: str) -> str:
        while parent[name] != name:
            parent[name] = parent[parent[name]]
            name = parent[name]
        return name

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            if venue_related(a, b):
                union(a, b)

    groups: dict[str, list[str]] = {}
    for name in names:
        groups.setdefault(find(name), []).append(name)

    cluster_id = 0
    assignment: dict[str, int] = {}
    for members in groups.values():
        if len(members) < 2:
            continue
        cluster_id += 1
        for name in members:
            assignment[name] = cluster_id
    return assignment


def report_venue_review(rows: list[dict[str, str]], path: str) -> None:
    """Write a worksheet of venues that might be the same place, grouped for
    review. Purely informational — merging only happens via venue_corrections
    .csv, which this never writes to. Safe to regenerate any time; it has no
    memory of past decisions, so a venue merged last week just won't reappear
    once its rows share one corrected name.
    """
    stats = build_venue_stats(rows)
    counts = {row["venue"]: int(row["shows"]) for row in stats}
    clusters = cluster_venues(counts)

    fields = [
        "cluster",
        "venue",
        "shows",
        "first_played",
        "last_played",
        "suggested_canonical",
    ]
    review_rows = []
    for row in stats:
        cluster = clusters.get(row["venue"])
        if cluster is None:
            continue
        members = [v for v, c in clusters.items() if c == cluster]
        # Most-played spelling as a starting suggestion — not applied
        # anywhere, just a guess to save typing when you agree with it.
        suggestion = max(members, key=lambda v: (counts[v], v))
        review_rows.append(
            {
                "cluster": str(cluster),
                "venue": row["venue"],
                "shows": row["shows"],
                "first_played": row["first_played"],
                "last_played": row["last_played"],
                "suggested_canonical": suggestion,
            }
        )
    review_rows.sort(key=lambda row: (int(row["cluster"]), -int(row["shows"])))

    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(review_rows)

    clusters_found = len({row["cluster"] for row in review_rows})
    if review_rows:
        print(
            f"wrote {rel(path)}: {clusters_found} possible-duplicate venue groups "
            f"({len(review_rows)} venues) — nothing is merged until you add "
            f"confirmed ones to {rel(VENUE_CORRECTIONS_CSV)}"
        )
    else:
        print(f"wrote {rel(path)}: no possible-duplicate venues found")


def write_csv(path: str, rows: list[dict[str, str]]) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--posts-dir", default=POSTS_DIR)
    parser.add_argument("--calendar", default=CALENDAR_CSV)
    parser.add_argument("-o", "--output", default=OUTPUT_CSV)
    parser.add_argument("--corrections", default=CORRECTIONS_CSV)
    parser.add_argument("--venue-corrections", default=VENUE_CORRECTIONS_CSV)
    parser.add_argument("--stats-output", default=STATS_CSV)
    parser.add_argument("--venue-stats-output", default=VENUE_STATS_CSV)
    parser.add_argument("--venue-review-output", default=VENUE_REVIEW_CSV)
    parser.add_argument("--set-length-output", default=SET_LENGTH_STATS_CSV)
    parser.add_argument("--shows-output", default=SHOWS_CSV)
    parser.add_argument(
        "--missing", action="store_true", help="list past events with no setlist"
    )
    parser.add_argument(
        "--missing-all",
        action="store_true",
        help="like --missing, including non-show entries",
    )
    parser.add_argument("--overrides", default=EVENT_OVERRIDES_CSV)
    args = parser.parse_args()

    if not os.path.isdir(args.posts_dir):
        raise SystemExit(f"error: no {args.posts_dir}/ directory — paste posts there first")

    calendar = load_calendar(args.calendar)
    if not calendar:
        print(f"warning: {args.calendar} not found; dates fall back to nearest past year", file=sys.stderr)

    corrections = load_corrections(args.corrections)
    venue_corrections = load_corrections(args.venue_corrections)
    rows, report = build_rows(
        args.posts_dir, calendar, date.today(), corrections, venue_corrections
    )
    shows = {(row["event_date"], row["venue"]) for row in rows}
    unmatched = sorted(
        {(row["event_date"], row["venue"]) for row in rows if not row["event_uid"]}
    )

    print(
        f"{report['parsed']} posts parsed → {len(shows)} shows, {len(rows)} songs"
        + (f" ({report['duplicates']} duplicate posts ignored)" if report["duplicates"] else "")
    )
    if report["skipped"]:
        print(f"  {report['skipped']} blocks skipped (no date line or no songs)")
    for conflict in report["conflicts"]:
        print(f"  conflict: {conflict}")
    for odd in report["numbering"]:
        print(f"  numbering typo in post: {odd}")
    for event_date, venue in unmatched:
        print(f"  no calendar event for {event_date} @ {venue or '?'}")
    for wrong, count in sorted(report["applied"].items()):
        print(f"  corrected {wrong!r} → {corrections[wrong]!r} ({count}x)")
    for wrong in sorted(set(corrections) - set(report["applied"])):
        print(f"  note: correction for {wrong!r} matched nothing — stale entry?")
    for wrong, count in sorted(report["venues_applied"].items()):
        print(f"  corrected venue {wrong!r} → {venue_corrections[wrong]!r} ({count}x)")
    for wrong in sorted(set(venue_corrections) - set(report["venues_applied"])):
        print(f"  note: venue correction for {wrong!r} matched nothing — stale entry?")
    report_typos(rows)

    if args.missing or args.missing_all:
        report_missing(calendar, rows, date.today(), args.missing_all)

    add_override_templates(rows, calendar, args.overrides)

    write_csv(args.output, rows)
    print(f"\nwrote {rel(args.output)}")
    report_stats(rows, len(shows), args.stats_output)
    report_venue_stats(rows, args.venue_stats_output)
    report_venue_review(rows, args.venue_review_output)
    report_set_length_stats(rows, calendar, args.set_length_output)
    report_shows(rows, calendar, args.shows_output)


if __name__ == "__main__":
    main()
