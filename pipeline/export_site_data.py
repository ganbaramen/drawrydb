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
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
    return events


def build_songs(events: list[dict]) -> list[dict]:
    stats = read_csv("song_stats.csv")
    setlists = read_csv("setlists.csv")

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
                "id": row["song"],
                "name": row["song"],
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
            }
        )
    return songs


def build_venues(events: list[dict]) -> list[dict]:
    stats = read_csv("venue_stats.csv")
    shows = read_csv("shows.csv")

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
                "id": row["venue"],
                "name": row["venue"],
                "shows": int(row["shows"]),
                "first_played": row["first_played"],
                "last_played": row["last_played"],
                "event_ids": event_ids_by_venue.get(row["venue"], []),
            }
        )
    return venues


def main() -> None:
    events = build_events()
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "events": events,
        "songs": build_songs(events),
        "venues": build_venues(events),
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
