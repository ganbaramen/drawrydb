#!/usr/bin/env python3
"""Build data/generated/site_data.json for the DrawryDB site.

Reads the CSVs the other two pipeline scripts already produce, does the joins
in Python, and writes one JSON file shaped for rendering rather than analysis.
Not itself checked into git — it's a build step, run fresh by CI (see
.github/workflows/deploy.yml) and locally before `astro dev`:

    python3 pipeline/export_site_data.py

Unlike export_calendar.py and sync_setlists.py, this script is allowed to
import sync_setlists directly (see is_show() below) — the "independent
scripts" rule elsewhere in this pipeline is about those two not depending on
*each other*, so cron can run either alone. This script already depends on
both of their outputs, so it isn't part of that constraint.
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_DIR = os.path.join(ROOT, "data", "input")
GENERATED_DIR = os.path.join(ROOT, "data", "generated")
OUTPUT_JSON = os.path.join(GENERATED_DIR, "site_data.json")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_setlists import is_show  # noqa: E402  (see module docstring)

# Strips presentational prefixes off a calendar summary for display —
# "【イベント】『LEADING Circuit HELLOWEEN』" -> "LEADING Circuit HELLOWEEN".
# Only used as a fallback: a real show prefers `post_event_name` (already
# clean, since it comes straight from the setlist post body), so this only
# actually runs for pending events, which have no post to draw from yet.
TITLE_BRACKETS = re.compile(r"^[(（][^()（）]*[)）]|^【[^【】]*】")
QUOTE_PAIRS = {"「": "」", "『": "』"}


def unwrap_quotes(text: str) -> str:
    """Strip one layer of outer 「」/『』 quotes, e.g. '『LEADING…』' ->
    'LEADING…'. Only strips when the outer pair actually wraps the whole
    string — checked by depth, not by forbidding quotes in between, so a
    title with a nested pair ('『NANCY…「NANCY TANOCY PARTY」』') still loses
    its outer quotes and keeps the inner ones intact."""
    if not text:
        return text
    # U+FE0F (VARIATION SELECTOR-16) forces emoji-style rendering of an
    # otherwise dual-presentation character — invisible itself, so its
    # presence is easy to miss when copy-pasting and easy to drop
    # inconsistently. Found on a real multi-day event: 2026-04-18's post
    # had "エクストロメ‼️" (with VS16, renders as a red emoji) and
    # 2026-04-19's had "エクストロメ‼" (without, renders as plain bold
    # text) for what is the same tour/title — stripped everywhere so the
    # same title always renders the same way regardless of which post
    # happened to include it.
    text = text.replace("️", "")
    close = QUOTE_PAIRS.get(text[0])
    if not close or text[-1] != close:
        return text
    depth = 0
    for ch in text[1:-1]:
        if ch in QUOTE_PAIRS:
            depth += 1
        elif ch in QUOTE_PAIRS.values():
            if depth == 0:
                return text
            depth -= 1
    return text[1:-1] if depth == 0 else text


def clean_title(summary: str) -> str:
    """Fallback title for pending events, which have no post to draw from."""
    text = summary.strip()
    while True:
        stripped = TITLE_BRACKETS.sub("", text).strip()
        if stripped == text:
            break
        text = stripped
    return unwrap_quotes(text)


# Anchors on the "■チケット販売サイト"-style header that precedes a ticket
# URL in the calendar description prose (142/200 events use that exact
# label; チケット抽選サイト/チケットサイト/チケット詳細・販売サイト/販売サイト
# are the other real variants found by auditing every description — see
# CLAUDE.md's approach elsewhere in this pipeline of testing against real
# data rather than guessing). Requiring チケット or 販売 in the header, and
# then excluding the ones that also mention 配信 (livestream) or チェキ
# (cheki photos), keeps out the other kinds of "■...サイト" headers that
# also appear (streaming links, cheki sales) without needing a header
# allowlist that would miss a new phrasing.
TICKET_HEADER = re.compile(r"^■.*(?:チケット|販売).*$")
TICKET_HEADER_EXCLUDE = ("配信", "チェキ", "マワループ", "質問")
# A header-like line that isn't a ticket link at all (a festival's "公式HP"
# often follows right after its ticket link, with no further ■ header to
# signal the ticket section ended) — closes the section same as a
# non-matching ■ header would.
NON_TICKET_LABELS = {"公式HP"}
TICKET_URL = re.compile(r"https?://\S+")
# One event's ticket URL is missing its scheme entirely
# ("ticketvillage.jp/events/13764") — a real typo in the source post, not a
# parsing edge case to special-case away; this catches bare domains
# generally instead.
BARE_DOMAIN = re.compile(r"^[\w.-]+\.[a-zA-Z]{2,}(?:/\S*)?$")


def parse_ticket_links(description: str) -> list[dict]:
    """Pull (label, url) ticket-sale links out of the description prose.

    label is the platform/tier name on its own line just above the URL when
    present (e.g. "イープラス" / "VIPチケット" for events with more than one
    ticket link), else None for the common case of one bare URL under the
    header.
    """
    links: list[dict] = []
    in_section = False
    pending_label: str | None = None
    for line in description.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("■"):
            in_section = bool(TICKET_HEADER.match(stripped)) and not any(
                word in stripped for word in TICKET_HEADER_EXCLUDE
            )
            pending_label = None
            continue
        if stripped in NON_TICKET_LABELS:
            in_section = False
            pending_label = None
            continue
        if not in_section:
            continue
        match = TICKET_URL.search(stripped)
        if match:
            url = re.split(r"[\s※]", match.group(0))[0]
            links.append({"label": pending_label, "url": url})
            pending_label = None
        elif BARE_DOMAIN.match(stripped):
            links.append({"label": pending_label, "url": f"https://{stripped}"})
            pending_label = None
        else:
            pending_label = stripped
    return links


def read_csv(name: str) -> list[dict[str, str]]:
    path = os.path.join(GENERATED_DIR, name)
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def load_slugs(name: str) -> dict[str, str]:
    """name -> hand-typed URL slug (data/input/venue_slugs.csv, `name,slug`
    — songs' own slug lives in song_details.csv alongside their credits, see
    load_song_details()). Per DRAWRYDB.md's slug section: a missing file, or
    a name with no row yet, isn't an error — that name's id just falls back
    to itself (raw Japanese, percent-encoded by the browser same as it
    already is), so the site works before this table is filled in. Filling
    one in is purely additive — it doesn't touch anything else the id is
    used for (venue matching stays keyed by name throughout the rest of
    this pipeline)."""
    path = os.path.join(INPUT_DIR, name)
    if not os.path.exists(path):
        return {}
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return {
            row["name"].strip(): row["slug"].strip()
            for row in csv.DictReader(fh)
            if row.get("name") and row.get("slug")
        }


CREDIT_FIELDS = ["number", "lyrics", "composition", "arrangement", "choreography", "note"]


def load_song_details() -> dict[str, dict[str, str]]:
    """name -> {slug, translation, number, lyrics, composition,
    arrangement, choreography, note} from data/input/song_details.csv. One
    file, not several — a song's slug, English translation, and credits
    (作詞/作曲/編曲/振付, a track number, a free-form note e.g. a
    lyrics-post link) are all exactly one hand-curated row per song, so
    splitting them across separate files just meant editing several places
    for what's conceptually one "everything about this song that isn't
    derived" row. Same missing-file/missing-row tolerance as before: a song
    with no row here just gets no slug (id falls back to its raw name), no
    translation subtitle, and no credits section."""
    path = os.path.join(INPUT_DIR, "song_details.csv")
    if not os.path.exists(path):
        return {}
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return {
            row["name"].strip(): {
                "slug": row.get("slug", "").strip(),
                "translation": row.get("translation", "").strip(),
                **{field: row.get(field, "").strip() for field in CREDIT_FIELDS},
            }
            for row in csv.DictReader(fh)
            if row.get("name")
        }


def load_event_notes() -> list[dict[str, str]]:
    """data/input/event_notes.csv (date,match,note) — the hand-entry escape
    hatch for a freeform note on an event's page, same `date` + optional
    `match` (substring of the event's calendar summary, for double-header
    days) keying as event_overrides.csv. `note` can be multi-line — a
    plain quoted CSV field already supports embedded newlines, no special
    handling needed to read or write one."""
    path = os.path.join(INPUT_DIR, "event_notes.csv")
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return [row for row in csv.DictReader(fh) if (row.get("date") or "").strip()]


def apply_event_notes(events: list[dict], notes: list[dict[str, str]]) -> None:
    """Attach a `note` field (None when there isn't one) to every event in
    place, matching on (date, match-substring-of-calendar_summary) like
    export_calendar.py's apply_overrides(). Ambiguous/stale rows are
    reported rather than silently skipped, same reasoning as that
    function's own report."""
    by_date: dict[str, list[dict]] = {}
    for event in events:
        by_date.setdefault(event["date"], []).append(event)
        event["note"] = None

    for row in notes:
        when = row["date"].strip()
        match = (row.get("match") or "").strip()
        candidates = by_date.get(when, [])
        if match:
            candidates = [e for e in candidates if match in e["title"]]

        if not candidates:
            print(f"  event note {when} {match!r} matched no event — stale?")
            continue
        if len(candidates) > 1:
            titles = ", ".join(repr(e["title"][:28]) for e in candidates)
            print(
                f"  event note {when} matches {len(candidates)} events "
                f"({titles}) — add a `match` column value to pick one"
            )
            continue

        candidates[0]["note"] = row["note"]


def sort_key(row: dict[str, str]) -> str:
    """Same fallback chain the pipeline uses elsewhere for same-day
    ordering: the band's own slot, then the event's showtime, then doors."""
    return row.get("live_start") or row.get("showtime") or row.get("doors") or "~"


def build_events() -> list[dict]:
    calendar = read_csv("drawry_schedule.csv")
    shows = read_csv("shows.csv")
    setlists = read_csv("setlists.csv")

    songs_by_uid_date: dict[tuple[str, str], list[dict]] = {}
    for row in setlists:
        key = (row["event_uid"], row["event_date"])
        songs_by_uid_date.setdefault(key, []).append(row)

    linked_uids = {row["event_uid"] for row in shows if row["event_uid"]}
    # shows.csv has no description column (see CLAUDE.md's shows.csv section
    # — it only carries what building the show list itself needed), so a
    # show's ticket links come from the calendar row via event_uid instead.
    description_by_uid = {row["uid"]: row["description"] for row in calendar}

    # One entry per real show, plus one per calendar event that should have a
    # setlist but doesn't have one linked yet (past gap or future show).
    by_date: dict[str, list[dict]] = {}
    for row in shows:
        by_date.setdefault(row["event_date"], []).append(
            {
                "date": row["event_date"],
                "title": unwrap_quotes(row["post_event_name"])
                or clean_title(row["calendar_summary"]),
                "venue": row["venue"],
                "doors": row["doors"] or None,
                "showtime": row["showtime"] or None,
                "live_start": row["live_start"] or None,
                "live_end": row["live_end"] or None,
                "has_setlist": True,
                "setlist": [
                    {
                        "position": int(song["position"]),
                        "song": song["song"],
                        "note": song["note"],
                        "is_se": song["is_se"] == "yes",
                        "is_interlude": song["is_interlude"] == "yes",
                        "is_encore": song["is_encore"] == "yes",
                    }
                    for song in sorted(
                        songs_by_uid_date.get((row["event_uid"], row["event_date"]), []),
                        key=lambda s: int(s["position"]),
                    )
                ],
                "ticket_links": parse_ticket_links(description_by_uid.get(row["event_uid"], "")),
                "sort_key": sort_key(row),
            }
        )

    for row in calendar:
        if row["uid"] in linked_uids or not is_show(row["summary"]):
            continue
        date = row["start"][:10]
        by_date.setdefault(date, []).append(
            {
                "date": date,
                "title": clean_title(row["summary"]),
                "venue": row["venue"] or None,
                "doors": row["doors"] or None,
                "showtime": row["showtime"] or None,
                "live_start": row["live_start"] or None,
                "live_end": row["live_end"] or None,
                "has_setlist": False,
                "setlist": [],
                "ticket_links": parse_ticket_links(row["description"]),
                "sort_key": sort_key(row),
            }
        )

    events = []
    for date in sorted(by_date):
        day_events = sorted(by_date[date], key=lambda e: (e["sort_key"], e["title"]))
        for n, event in enumerate(day_events, start=1):
            event["id"] = f"{date}-{n}"
            del event["sort_key"]
            events.append(event)

    events.sort(key=lambda e: e["id"])
    apply_event_notes(events, load_event_notes())
    return events


def song_credits(details: dict[str, str] | None) -> dict[str, str] | None:
    """None unless at least one actual credit field is filled in — most
    song_details.csv rows have a slug and nothing else right now, and a
    credits section with every field blank isn't worth rendering."""
    if not details or not any(details.get(field) for field in CREDIT_FIELDS):
        return None
    return {field: details.get(field, "") for field in CREDIT_FIELDS}


def build_songs(events: list[dict]) -> list[dict]:
    stats = read_csv("song_stats.csv")
    setlists = read_csv("setlists.csv")
    details = load_song_details()

    event_id_by_date_venue = {
        (e["date"], e["venue"]): e["id"] for e in events if e["has_setlist"]
    }

    performances_by_song: dict[str, list[dict]] = {}
    for row in setlists:
        performances_by_song.setdefault(row["song"], []).append(
            {
                "event_id": event_id_by_date_venue[(row["event_date"], row["venue"])],
                "date": row["event_date"],
                "venue": row["venue"],
                "position": int(row["position"]),
                "is_encore": row["is_encore"] == "yes",
                "note": row["note"],
            }
        )

    songs = []
    for row in stats:
        performances = sorted(
            performances_by_song.get(row["song"], []), key=lambda p: p["date"]
        )
        songs.append(
            {
                "id": details.get(row["song"], {}).get("slug") or row["song"],
                "name": row["song"],
                "translation": details.get(row["song"], {}).get("translation") or None,
                "plays": int(row["plays"]),
                "shows": int(row["shows"]),
                "shows_since_debut": int(row["shows_since_debut"]),
                "play_rate": float(row["play_rate"]),
                "first_performed": row["first_performed"],
                "last_performed": row["last_performed"],
                "debut_confirmed": row["debut_confirmed"] == "yes",
                "encores": int(row["encores"]),
                "is_se": row["is_se"] == "yes",
                "is_interlude": row["is_interlude"] == "yes",
                "performances": performances,
                "credits": song_credits(details.get(row["song"])),
            }
        )
    return songs


ROLE_FIELDS = ["lyrics", "composition", "arrangement", "choreography"]


def load_creator_details() -> dict[str, dict[str, str]]:
    """name -> {slug, x} from data/input/creator_details.csv. Same
    one-file-per-thing reasoning as load_song_details(): a creator's slug
    and X/Twitter handle are both exactly one hand-curated fact per person,
    so one row covers both instead of splitting them across files. `x` is
    a bare handle (no "@", no URL) — build_creators() below turns it into
    a full profile URL; same missing-file/missing-row/blank-value
    tolerance as load_song_details() (no row, or a blank `x` cell, just
    means no link renders)."""
    path = os.path.join(INPUT_DIR, "creator_details.csv")
    if not os.path.exists(path):
        return {}
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return {
            row["name"].strip(): {
                "slug": row.get("slug", "").strip(),
                "x": row.get("x", "").strip(),
            }
            for row in csv.DictReader(fh)
            if row.get("name")
        }


def split_creators(value: str) -> list[str]:
    """"nenene, & Yoshimura" -> ["nenene,", "Yoshimura"] — " & " (with the
    surrounding spaces) is the only separator real data uses for a
    co-credited role; a bare comma inside a name ("nenene,") is part of
    the name itself, not a list separator, so this doesn't split on it."""
    return [name.strip() for name in value.split(" & ") if name.strip()]


def build_creators(songs: list[dict]) -> list[dict]:
    """One entry per person credited on lyrics/composition/arrangement/
    choreography (data/input/song_details.csv), each listing every song
    they worked on and which role(s) — the credits table on a song's own
    page, inverted (person -> songs instead of song -> people). "A & B" in
    a credit field means two people share that credit; split via
    split_creators() into separate entries, same person merged across every
    song and field they appear in.
    """
    details = load_creator_details()
    song_by_id = {song["id"]: song for song in songs if song.get("credits")}

    # name -> song_id -> roles (in ROLE_FIELDS order, since that's the
    # order fields are visited below for each song).
    by_name: dict[str, dict[str, list[str]]] = {}
    for song in song_by_id.values():
        credits = song["credits"]
        for field in ROLE_FIELDS:
            value = credits.get(field, "")
            if not value:
                continue
            for name in split_creators(value):
                roles = by_name.setdefault(name, {}).setdefault(song["id"], [])
                if field not in roles:
                    roles.append(field)

    creators = []
    for name, song_roles in by_name.items():
        song_entries = [
            {
                "song_id": song_id,
                "song_name": song_by_id[song_id]["name"],
                "translation": song_by_id[song_id]["translation"],
                "roles": roles,
            }
            for song_id, roles in song_roles.items()
        ]
        song_entries.sort(
            key=lambda e: (
                song_by_id[e["song_id"]]["first_performed"],
                song_by_id[e["song_id"]]["name"],
            )
        )
        creators.append(
            {
                "id": details.get(name, {}).get("slug") or name,
                "name": name,
                "x": details.get(name, {}).get("x") or None,
                "songs": song_entries,
            }
        )
    # Most-credited first — the closest equivalent here to venues.csv's own
    # shows-desc default; name is a full tiebreak (creator names are unique
    # keys into by_name, so this alone already makes the sort deterministic).
    creators.sort(key=lambda c: (-len(c["songs"]), c["name"]))
    return creators


def build_venues(events: list[dict]) -> list[dict]:
    stats = read_csv("venue_stats.csv")
    shows = read_csv("shows.csv")
    slugs = load_slugs("venue_slugs.csv")

    event_id_by_date_venue = {
        (e["date"], e["venue"]): e["id"] for e in events if e["has_setlist"]
    }

    event_ids_by_venue: dict[str, list[str]] = {}
    for row in sorted(shows, key=lambda r: r["event_date"]):
        event_ids_by_venue.setdefault(row["venue"], []).append(
            event_id_by_date_venue[(row["event_date"], row["venue"])]
        )

    venues = []
    for row in stats:
        venues.append(
            {
                "id": slugs.get(row["venue"], row["venue"]),
                "name": row["venue"],
                "shows": int(row["shows"]),
                "first_played": row["first_played"],
                "last_played": row["last_played"],
                "event_ids": event_ids_by_venue.get(row["venue"], []),
            }
        )
    return venues


def build_set_length_stats(events: list[dict]) -> dict:
    """Group shows by set length (shows.csv's length_bucket, already derived
    from the calendar's live_start/live_end — see CLAUDE.md's set_length_stats
    section) and report, per bucket, how many shows there are, how many real
    songs a set that length tends to have, how many included an SE, which
    events had that length, and how often each song turns up — the last one
    across every bucket, so the site can show a single table comparing play
    distribution by length instead of sync_setlists.py's own report's
    top-5-per-bucket cap.

    Coverage is partial by the same token as shows.csv itself: only shows
    whose calendar entry states both live_start and live_end get a bucket.
    """
    shows = read_csv("shows.csv")
    setlists = read_csv("setlists.csv")
    # A song can't have been played before it existed — the fair denominator
    # per bucket is shows on/after *that song's* debut, not every show of
    # that length, the same reasoning song_stats.csv's own play_rate uses
    # (see CLAUDE.md's shows_since_debut/play_rate section).
    first_performed = {row["song"]: row["first_performed"] for row in read_csv("song_stats.csv")}
    details = load_song_details()
    event_id_by_date_venue = {
        (e["date"], e["venue"]): e["id"] for e in events if e["has_setlist"]
    }

    bucket_by_show = {
        (row["event_date"], row["venue"]): row["length_bucket"]
        for row in shows
        if row["length_bucket"]
    }

    songs_by_show: dict[tuple[str, str], list[dict]] = {}
    for row in setlists:
        songs_by_show.setdefault((row["event_date"], row["venue"]), []).append(row)

    bucket_info: dict[str, dict] = {}
    song_counts: dict[str, dict[str, int]] = {}
    bucket_dates: dict[str, list[str]] = {}
    for key, bucket in sorted(bucket_by_show.items()):
        date, _venue = key
        songs = songs_by_show.get(key, [])
        info = bucket_info.setdefault(
            bucket, {"shows": 0, "real_songs": 0, "with_se": 0, "event_ids": []}
        )
        info["shows"] += 1
        # SE and Interlude are categories, not song choices — excluded from
        # the song count for the same reason sync_setlists.py's avg_songs is.
        info["real_songs"] += sum(
            1 for s in songs if s["is_se"] != "yes" and s["is_interlude"] != "yes"
        )
        info["with_se"] += 1 if any(s["is_se"] == "yes" for s in songs) else 0
        info["event_ids"].append(event_id_by_date_venue[key])
        bucket_dates.setdefault(bucket, []).append(date)
        counts = song_counts.setdefault(bucket, {})
        for s in songs:
            counts[s["song"]] = counts.get(s["song"], 0) + 1

    # bucket_info/song_counts/bucket_dates are keyed by shows.csv's English
    # length_bucket label ("20 min") — internal grouping only. The site
    # needs to render this in either language, so the *exported* key is the
    # locale-neutral minute count instead; the label itself isn't shipped at
    # all, letting the site format "20分"/"20 min" from the number.
    bucket_keys = sorted(bucket_info, key=lambda b: int(b.split()[0]))
    minutes_by_key = {b: int(b.split()[0]) for b in bucket_keys}

    buckets = [
        {
            "minutes": minutes_by_key[b],
            "shows": bucket_info[b]["shows"],
            "avg_songs": round(bucket_info[b]["real_songs"] / bucket_info[b]["shows"], 1),
            "shows_with_se": bucket_info[b]["with_se"],
            "event_ids": bucket_info[b]["event_ids"],
        }
        for b in bucket_keys
    ]

    # Debut order, then track number as a tiebreaker — matching
    # songs/index.astro's own default ordering (see its comment for why:
    # a song with no number, e.g. SE/Interlude, sorts after one that has
    # it, same "blanks last" convention as the sortable columns). Name is
    # a final tiebreak so the order is fully determined even when two
    # songs share both a debut date and a (missing) number — necessary
    # because the input is a set: without a total order, ties would be
    # broken by set-iteration order, which depends on Python's per-process
    # string hash randomization and silently reshuffles on every run (this
    # is what caused "Automated data refresh" commits that only reordered
    # a couple of songs with no actual data change).
    def song_sort_key(name: str) -> tuple[str, int, str]:
        number = details.get(name, {}).get("number")
        return (first_performed.get(name, ""), int(number) if number else 10**9, name)

    all_song_names = sorted(
        {name for counts in song_counts.values() for name in counts},
        key=song_sort_key,
    )
    songs = []
    for name in all_song_names:
        debut = first_performed.get(name, "")
        rates = {}
        for b in bucket_keys:
            eligible = sum(1 for d in bucket_dates[b] if d >= debut)
            rates[str(minutes_by_key[b])] = {
                "count": song_counts[b].get(name, 0),
                "eligible": eligible,
            }
        songs.append(
            {
                "id": details.get(name, {}).get("slug") or name,
                "name": name,
                "translation": details.get(name, {}).get("translation") or None,
                "rates": rates,
            }
        )

    uncovered = len(shows) - sum(b["shows"] for b in buckets)
    return {"buckets": buckets, "songs": songs, "uncovered_shows": uncovered}


def main() -> None:
    events = build_events()
    songs = build_songs(events)
    data = {
        "events": events,
        "songs": songs,
        "venues": build_venues(events),
        "creators": build_creators(songs),
        "set_length_stats": build_set_length_stats(events),
    }
    with open(OUTPUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    with_setlist = sum(1 for e in data["events"] if e["has_setlist"])
    pending = len(data["events"]) - with_setlist
    print(
        f"wrote {os.path.relpath(OUTPUT_JSON, ROOT)}: {len(data['events'])} events "
        f"({with_setlist} with a setlist, {pending} pending)"
    )


if __name__ == "__main__":
    main()
