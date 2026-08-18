#!/usr/bin/env bash
# Runs the full pipeline in order: refresh the calendar, rebuild
# setlists/stats from it, then rebuild the site's
# data/generated/site_data.json. Same three commands pipeline/README.md
# documents individually (and what .github/workflows/refresh-data.yml runs
# on a schedule) — this just runs them together for local use.
#
# Resolves paths from its own location, not the working directory, so it
# runs correctly from anywhere — same property the Python scripts
# themselves keep (see CLAUDE.md).
#
# Any arguments are forwarded to export_calendar.py only (e.g. --quiet) —
# sync_setlists.py's and export_site_data.py's own flags are for overriding
# file paths, not something a routine "refresh everything" run needs.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 "$ROOT/pipeline/export_calendar.py" "$@"
python3 "$ROOT/pipeline/sync_setlists.py"
python3 "$ROOT/pipeline/export_site_data.py"
