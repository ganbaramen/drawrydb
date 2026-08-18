// Song/venue names become raw (often Japanese) path segments — see
// songs/[id].astro. Astro percent-escapes characters that would otherwise
// break path structure (observed: "#", which starts a URL fragment) when
// writing the output *file*, but does so as a literal "%23" substring in
// the filename, not an actual "#" byte. A link's href only gets one
// percent-decode pass by the static host, so producing that literal
// "%23" requires encoding the "%" itself too — "#" -> "%2523" ("%25"
// decodes to "%", then the literal "23" survives untouched). Verified
// against `astro preview` (same static-serving semantics as GitHub
// Pages): "%23" alone 404s, "%2523" resolves. Confirm again if Astro's
// own escaping of "#" (or any newly-affected character) ever changes.
export function urlSafe(id: string): string {
  return id.replace(/#/g, '%2523');
}

import type { Lang } from './i18n';

const WEEKDAYS_JA = ['日', '月', '火', '水', '木', '金', '土'];

export function formatDate(lang: Lang, iso: string): string {
  const [y, m, d] = iso.split('-').map(Number);
  const date = new Date(Date.UTC(y, m - 1, d));
  if (lang === 'ja') {
    return `${y}年${m}月${d}日(${WEEKDAYS_JA[date.getUTCDay()]})`;
  }
  // Intl's en-US order is month/day/year (or weekday-first with `weekday`
  // set); explicit year-month-day, matching the ja branch's own order, was
  // asked for over either of those.
  const month = new Intl.DateTimeFormat('en-US', { month: 'short', timeZone: 'UTC' }).format(date);
  const weekday = new Intl.DateTimeFormat('en-US', { weekday: 'short', timeZone: 'UTC' }).format(date);
  return `${y} ${month} ${d} (${weekday})`;
}

// Minutes between two "HH:MM" times, mirroring
// pipeline/sync_setlists.py's show_duration() (same midnight-wraparound
// handling — a show's live_end is occasionally past midnight).
export function liveDurationMinutes(start: string, end: string): number {
  const [startH, startM] = start.split(':').map(Number);
  const [endH, endM] = end.split(':').map(Number);
  const minutes = endH * 60 + endM - (startH * 60 + startM);
  return minutes < 0 ? minutes + 24 * 60 : minutes;
}

// key is "YYYY-MM", e.g. from an event date's first 7 characters.
export function formatMonth(lang: Lang, key: string): string {
  const [y, m] = key.split('-').map(Number);
  const date = new Date(Date.UTC(y, m - 1, 1));
  if (lang === 'ja') {
    return `${y}年${m}月`;
  }
  const month = new Intl.DateTimeFormat('en-US', { month: 'short', timeZone: 'UTC' }).format(date);
  return `${y} ${month}`;
}
