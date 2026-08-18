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


def main() -> None:
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "events": build_events(),
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
