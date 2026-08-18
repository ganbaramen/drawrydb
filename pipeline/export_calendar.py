#!/usr/bin/env python3
"""Export a public Google Calendar to CSV, and keep the CSV up to date.

Fetches the calendar's public iCal feed, parses it with the standard library
only (no pip installs), and writes a sorted CSV. Re-running updates the file
in place and reports what changed, so it is safe to drive from cron/launchd.

Usage:
    ./export_calendar.py                      # write ./drawry_schedule.csv
    ./export_calendar.py -o events.csv        # different output path
    ./export_calendar.py --tz UTC             # render times in another zone
    ./export_calendar.py --watch 3600         # refresh every hour in-process
    ./export_calendar.py --quiet              # only print on change / error
"""

from __future__ import annotations

import argparse
import csv
import html
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# Drawry.公開スケジュール
CALENDAR_ID = (
    "c4b3816079e3e0a75f93717cdb6fbc529a286779006f5082e9d6c1850a6c5bb8"
    "@group.calendar.google.com"
)
ICS_URL = (
    "https://calendar.google.com/calendar/ical/"
    f"{urllib.parse.quote(CALENDAR_ID, safe='')}/public/basic.ics"
)
DEFAULT_TZ = "Asia/Tokyo"

# Paths resolve against the repo root, not the working directory, so the
# script works the same from anywhere (cron included — no `cd` needed).
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_DIR = os.path.join(ROOT, "data", "input")
GENERATED_DIR = os.path.join(ROOT, "data", "generated")

DEFAULT_OUTPUT = os.path.join(GENERATED_DIR, "drawry_schedule.csv")
DEFAULT_OVERRIDES = os.path.join(INPUT_DIR, "event_overrides.csv")


def rel(path: str) -> str:
    """Show paths relative to the repo root — absolute ones make the run
    output unreadable now that files live in data/input and data/generated."""
    try:
        return os.path.relpath(path, ROOT)
    except ValueError:
        return path


# Fields you fill in by hand, for events whose description doesn't state them
# (or states them in a shape the parser doesn't read). Applied after parsing on
# every run, so they survive regeneration.
OVERRIDE_FIELDS = (
    "venue",
    "doors",
    "showtime",
    "live_start",
    "live_end",
    "meet_start",
    "meet_end",
)
# A lone "-" clears a value the parser got wrong, as opposed to blank, which
# means "leave whatever was parsed".
OVERRIDE_CLEAR = "-"

# "12月20日(土)@ 青山RizM" -> venue. Reuses the same "first @venue line" idea as
# sync_setlists.py's DATE_LINE, but looser: the calendar's date line has more
# shapes ("4月18日(土),19日(日)@ ...", plain "9/8(月)20:00より…" with no venue at
# all for non-shows).
VENUE_LINE = re.compile(r"[@＠]\s*(.+)")
# A venue string joining multiple names is ambiguous — real examples:
# "duo MUSIC EXCHANGE&SHIBUYA RING" (a shared bill, band played only one),
# "下北沢シャングリラ / MOSAiC / ERA / Flowers LOFT" (a rotating multi-venue
# circuit event), and "大塚Hearts+、Hearts Next、MEETS、..." (multiple stages
# within one building complex) — none of these strings names one specific
# venue. Surface it rather than guessing; the setlist post (once pasted) or a
# manual override in event_overrides.csv resolves it.
#
# "・" is deliberately excluded even though it also separates lists
# ("大阪・心斎橋エリアライブハウス8会場"): it's overloaded in this data as a
# plain word-connector inside area descriptors ("THE LIVE HOUSE soma(大阪・
# 心斎橋)") and room-size suffixes ("TFTホール 1000・500・300"), where treating
# it as ambiguous would be a false positive on a single, real venue name.
VENUE_AMBIGUOUS = re.compile(r".+[&/、].+")

# Doors/showtime live in the description prose, not in DTSTART (every event on
# this calendar is all-day). Two spellings occur:
#   "開場 18:30 / 開演 19:00"      — labelled separately
#   "開場 / 開演 11:00 / 11:30"    — labels first, then both times
TIME_SEPARATE = {
    "doors": re.compile(r"開場\s*[：:]?\s*(\d{1,2})\s*[:：]\s*(\d{2})"),
    "showtime": re.compile(r"開演\s*[：:]?\s*(\d{1,2})\s*[:：]\s*(\d{2})"),
}
TIME_COMBINED = re.compile(
    r"開場\s*/\s*開演\s*[：:]?\s*"
    r"(\d{1,2})\s*[:：]\s*(\d{2})\s*/\s*(\d{1,2})\s*[:：]\s*(\d{2})"
)
# Most events are multi-group bills, so 開場/開演 is the *event's* schedule, not
# this band's. Their own slot is written as "ライブ 19:30~20:00" / "特典会
# 21:00~22:00" — that is the time that actually distinguishes two events on one
# day. Requiring a digit after the label keeps "特典会：バレンタインコスプレ"
# and "ライブ会場：..." out.
SLOT_LABELS = {"live": "ライブ", "meet": "特典会"}
# [^\S\n] rather than \s: the gap must not cross a newline, or a timetable's
# "20:50 特典会\n22:00 特典会終了" reads the *end* time as the start.
SLOT_PATTERN = (
    r"[^\S\n]*[：:]?[^\S\n]*(\d{1,2})[^\S\n]*[:：][^\S\n]*(\d{2})"
    r"(?:[^\S\n]*[~〜～\-–—][^\S\n]*(\d{1,2})[^\S\n]*[:：][^\S\n]*(\d{2}))?"
)
# The other layout puts the time first, one line per act:
#   20:10 Drawry.
#   20:50 特典会
#   22:00 特典会終了
BAND_NAME = "Drawry."
TIMETABLE_LINE = re.compile(r"^\s*(\d{1,2})\s*[:：]\s*(\d{2})\s+(\S.*)$")

COLUMNS = [
    "uid",
    "start",
    "end",
    "all_day",
    "venue",
    "doors",
    "showtime",
    "live_start",
    "live_end",
    "meet_start",
    "meet_end",
    "summary",
    "location",
    "description",
    "status",
    "recurrence",
    "last_modified",
]


# --- iCal parsing ------------------------------------------------------------


def unfold(text: str) -> list[str]:
    """Join RFC 5545 folded lines (continuations start with space or tab)."""
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def parse_line(line: str) -> tuple[str, dict[str, str], str] | None:
    """Split `NAME;PARAM=v:value` into (name, params, value)."""
    # The colon that ends the property section is the first one not inside
    # a quoted parameter value.
    in_quotes = False
    for i, ch in enumerate(line):
        if ch == '"':
            in_quotes = not in_quotes
        elif ch == ":" and not in_quotes:
            head, value = line[:i], line[i + 1 :]
            break
    else:
        return None

    parts = head.split(";")
    name = parts[0].upper()
    params = {}
    for param in parts[1:]:
        if "=" in param:
            key, val = param.split("=", 1)
            params[key.upper()] = val.strip('"')
    return name, params, value


def unescape_text(value: str) -> str:
    out = []
    i = 0
    while i < len(value):
        ch = value[i]
        if ch == "\\" and i + 1 < len(value):
            nxt = value[i + 1]
            out.append({"n": "\n", "N": "\n"}.get(nxt, nxt))
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def clean_description(value: str) -> str:
    """Google puts HTML in DESCRIPTION; flatten it to readable text."""
    text = unescape_text(value)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</?(p|div)[^>]*>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def parse_times(description: str) -> tuple[str, str]:
    """Pull (doors, showtime) as HH:MM out of the description prose."""
    combined = TIME_COMBINED.search(description)
    if combined:
        hours = combined.groups()
        return (
            f"{int(hours[0]):02d}:{hours[1]}",
            f"{int(hours[2]):02d}:{hours[3]}",
        )
    found = {}
    for name, pattern in TIME_SEPARATE.items():
        match = pattern.search(description)
        found[name] = f"{int(match.group(1)):02d}:{match.group(2)}" if match else ""
    return found["doors"], found["showtime"]


def parse_slots(description: str) -> dict[str, str]:
    """Pull this band's own ライブ / 特典会 slot times out of the description."""
    slots = {}
    for field, label in SLOT_LABELS.items():
        match = re.search(re.escape(label) + SLOT_PATTERN, description)
        if match:
            slots[f"{field}_start"] = f"{int(match.group(1)):02d}:{match.group(2)}"
            slots[f"{field}_end"] = (
                f"{int(match.group(3)):02d}:{match.group(4)}" if match.group(3) else ""
            )
        else:
            slots[f"{field}_start"] = slots[f"{field}_end"] = ""

    # Time-first timetable. Only fills what the label-first form missed, and
    # leaves live_end blank — the source gives the next act's start, which is
    # not the same as when this set ended.
    for line in description.split("\n"):
        match = TIMETABLE_LINE.match(line)
        if not match:
            continue
        when = f"{int(match.group(1)):02d}:{match.group(2)}"
        what = match.group(3).strip()
        if BAND_NAME.lower() in what.lower() and not slots["live_start"]:
            slots["live_start"] = when
        elif what.startswith("特典会"):
            key = "meet_end" if "終了" in what else "meet_start"
            if not slots[key]:
                slots[key] = when
    return slots


def parse_venue(description: str) -> str:
    """Pull the venue out of the description's "@venue" line, if present."""
    for line in description.split("\n")[:3]:
        match = VENUE_LINE.search(line)
        if match:
            return match.group(1).strip()
    return ""


def parse_dt(value: str, params: dict[str, str]) -> tuple[datetime | date, bool]:
    """Return (value, is_all_day) for a DTSTART/DTEND property."""
    if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", value):
        return datetime.strptime(value, "%Y%m%d").date(), True
    if value.endswith("Z"):
        dt = datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        return dt, False
    dt = datetime.strptime(value, "%Y%m%dT%H%M%S")
    tzid = params.get("TZID")
    if tzid:
        try:
            dt = dt.replace(tzinfo=ZoneInfo(tzid))
        except Exception:
            pass  # floating time; caller localizes it
    return dt, False


def parse_events(ics: str) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    current: dict[str, object] | None = None

    for line in unfold(ics):
        if line == "BEGIN:VEVENT":
            current = {}
            continue
        if line == "END:VEVENT":
            if current is not None:
                events.append(current)
            current = None
            continue
        if current is None:
            continue

        parsed = parse_line(line)
        if not parsed:
            continue
        name, params, value = parsed

        if name == "DTSTART":
            current["start"], current["all_day"] = parse_dt(value, params)
        elif name == "DTEND":
            current["end"], _ = parse_dt(value, params)
        elif name in ("SUMMARY", "LOCATION"):
            current[name.lower()] = unescape_text(value).strip()
        elif name == "DESCRIPTION":
            current["description"] = clean_description(value)
        elif name in ("UID", "STATUS"):
            current[name.lower()] = value.strip()
        elif name == "RRULE":
            current["recurrence"] = value.strip()
        elif name == "LAST-MODIFIED":
            current["last_modified"] = value.strip()

    return events


# --- rendering ---------------------------------------------------------------


def to_row(event: dict[str, object], tz: ZoneInfo) -> dict[str, str]:
    start = event.get("start")
    end = event.get("end")
    all_day = bool(event.get("all_day"))

    def render(value: object, is_end: bool) -> str:
        if value is None:
            return ""
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=tz)
            return value.astimezone(tz).strftime("%Y-%m-%d %H:%M")
        # All-day DTEND is exclusive in iCal; show the last day it covers.
        if is_end:
            value = value - timedelta(days=1)
        return value.strftime("%Y-%m-%d")

    description = str(event.get("description", ""))
    doors, showtime = parse_times(description)

    return {
        "uid": str(event.get("uid", "")),
        "start": render(start, False),
        "end": render(end, True),
        "all_day": "yes" if all_day else "no",
        "venue": parse_venue(description),
        "doors": doors,
        "showtime": showtime,
        **parse_slots(description),
        "summary": str(event.get("summary", "")),
        "location": str(event.get("location", "")),
        "description": str(event.get("description", "")),
        "status": str(event.get("status", "")),
        "recurrence": str(event.get("recurrence", "")),
        "last_modified": str(event.get("last_modified", "")),
    }


def sort_key(row: dict[str, str]) -> tuple[str, str, str]:
    # Two events on one day are ordered by when the band actually plays. Their
    # own slot beats the event's showtime, since most bills are multi-group and
    # two events can share a start time while their slots differ. Entries with
    # no time sort last that day rather than jumping to the front.
    when = row["live_start"] or row["showtime"] or row["doors"] or "~"
    return (row["start"], when, row["summary"])


# --- CSV I/O -----------------------------------------------------------------


def load_overrides(path: str) -> list[dict[str, str]]:
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return [row for row in csv.DictReader(fh) if (row.get("date") or "").strip()]


def apply_overrides(
    rows: list[dict[str, str]], overrides: list[dict[str, str]]
) -> tuple[list[str], list[str]]:
    """Overlay hand-entered times onto the parsed rows.

    Returns (applied, problems). Problems always deserve printing; applied lines
    are routine and get hidden under --quiet so cron stays silent.
    """
    applied: list[str] = []
    report = []
    for override in overrides:
        when = override["date"].strip()
        match = (override.get("match") or "").strip()
        candidates = [row for row in rows if row["start"][:10] == when]
        if match:
            candidates = [row for row in candidates if match in row["summary"]]

        if not candidates:
            report.append(f"override {when} {match!r} matched no event — stale?")
            continue
        if len(candidates) > 1:
            titles = ", ".join(repr(row["summary"][:28]) for row in candidates)
            report.append(
                f"override {when} matches {len(candidates)} events ({titles}) "
                f"— add a `match` column value to pick one"
            )
            continue

        row = candidates[0]
        changed = []
        for field in OVERRIDE_FIELDS:
            value = (override.get(field) or "").strip()
            if not value:
                continue
            new = "" if value == OVERRIDE_CLEAR else value
            if row[field] != new:
                changed.append(f"{field}={new or 'cleared'}")
            row[field] = new
        if changed:
            applied.append(
                f"override {when} {row['summary'][:30]}: {', '.join(changed)}"
            )
    return applied, report


def read_existing(path: str) -> list[dict[str, str]]:
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return [{col: row.get(col, "") for col in COLUMNS} for row in csv.DictReader(fh)]


def write_csv(path: str, rows: list[dict[str, str]]) -> None:
    """Write atomically so a reader never sees a half-written file."""
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".calendar-", suffix=".csv")
    try:
        # utf-8-sig keeps Excel from mangling the Japanese text.
        with os.fdopen(fd, "w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(fh, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def diff(old: list[dict[str, str]], new: list[dict[str, str]]) -> tuple[int, int, int]:
    old_by_uid = {row["uid"]: row for row in old}
    new_by_uid = {row["uid"]: row for row in new}
    added = len(new_by_uid.keys() - old_by_uid.keys())
    removed = len(old_by_uid.keys() - new_by_uid.keys())
    changed = sum(
        1
        for uid in new_by_uid.keys() & old_by_uid.keys()
        if new_by_uid[uid] != old_by_uid[uid]
    )
    return added, removed, changed


# --- driver ------------------------------------------------------------------


def fetch(url: str, retries: int = 3) -> str:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": "calendar-csv-export/1.0"}
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
            if attempt < retries - 1:
                time.sleep(2**attempt)
    raise SystemExit(f"error: could not fetch calendar feed: {last}")


def run_once(args: argparse.Namespace) -> None:
    tz = ZoneInfo(args.tz)
    ics = fetch(args.url)
    if "BEGIN:VCALENDAR" not in ics:
        raise SystemExit("error: response was not an iCal feed (is the calendar public?)")

    rows = [to_row(event, tz) for event in parse_events(ics)]
    # Overrides land before sorting, because the sort keys off these times.
    applied, problems = apply_overrides(rows, load_overrides(args.overrides))
    for row in rows:
        if VENUE_AMBIGUOUS.match(row["venue"]):
            problems.append(
                f"ambiguous venue on {row['start']}: {row['venue']!r} — "
                f"add a `venue` override in {args.overrides}"
            )
    rows.sort(key=sort_key)

    old = read_existing(args.output)
    added, removed, changed = diff(old, rows)

    if old and (added, removed, changed) == (0, 0, 0):
        if not args.quiet:
            print(f"{rel(args.output)}: up to date ({len(rows)} events)")
            for note in applied:
                print(f"  {note}")
        for note in problems:
            print(f"  {note}")
        return

    write_csv(args.output, rows)
    stamp = datetime.now(tz).strftime("%Y-%m-%d %H:%M")
    if old:
        print(
            f"{stamp} {rel(args.output)}: {len(rows)} events "
            f"(+{added} added, -{removed} removed, ~{changed} changed)"
        )
    else:
        print(f"{stamp} {rel(args.output)}: wrote {len(rows)} events")
    for note in applied if not args.quiet else []:
        print(f"  {note}")
    for note in problems:
        print(f"  {note}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-o", "--output", default=DEFAULT_OUTPUT, help="CSV path")
    parser.add_argument("--url", default=ICS_URL, help="iCal feed URL")
    parser.add_argument(
        "--overrides", default=DEFAULT_OVERRIDES, help="hand-entered times CSV"
    )
    parser.add_argument("--tz", default=DEFAULT_TZ, help="timezone for rendered times")
    parser.add_argument(
        "--watch",
        type=int,
        metavar="SECONDS",
        help="stay running and refresh on this interval",
    )
    parser.add_argument("--quiet", action="store_true", help="print only on change")
    args = parser.parse_args()

    if args.watch:
        while True:
            try:
                run_once(args)
            except SystemExit as exc:
                print(exc, file=sys.stderr)
            time.sleep(args.watch)
    else:
        run_once(args)


if __name__ == "__main__":
    main()
