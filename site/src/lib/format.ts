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

// export_site_data.py ships bucket length as a bare minute count (not
// shows.csv's English "20 min" label) specifically so this can render it in
// either language.
export function formatSetLength(lang: Lang, minutes: number): string {
  return lang === 'ja' ? `${minutes}分` : `${minutes} min`;
}

// song_details.csv's track numbers are entered as plain digits ("1", "11")
// — padded to 2 digits at display time so the site doesn't require typing
// a leading zero by hand.
export function formatTrackNumber(number: string): string {
  return number.padStart(2, '0');
}

interface NamedWithTranslation {
  name: string;
  translation: string | null;
}

// The name shown as the *primary* text everywhere a song appears (lists,
// setlist entries, ...) — the original name, except in English with a
// translation set, where the translation takes over as primary. song.name
// itself is never mutated; this is purely a display-time choice, computed
// fresh per call so it always reflects the current page's lang.
export function songDisplayName(lang: Lang, song: NamedWithTranslation): string {
  return lang === 'en' && song.translation ? song.translation : song.name;
}

// The *other* name, shown as a subtitle only on the song's own page — null
// (render nothing) when there's no translation at all, matching "if there
// is no translation listed, only show the original."
export function songSubtitle(lang: Lang, song: NamedWithTranslation): string | null {
  if (!song.translation) return null;
  return lang === 'en' ? song.name : song.translation;
}

export interface TextChunk {
  text: string;
  // Present only on chunks that should render as a link.
  url?: string;
}

const URL_RE = /https?:\/\/\S+/g;

// Splits free-form text (e.g. a song's credits note) around any bare URLs
// it contains, for a template to map over — <a> for a chunk with `url`,
// plain text otherwise. Returns chunks rather than an HTML string so the
// caller never has to set innerHTML on user-provided text.
export function autoLink(text: string): TextChunk[] {
  const chunks: TextChunk[] = [];
  let lastIndex = 0;
  for (const match of text.matchAll(URL_RE)) {
    const start = match.index ?? 0;
    if (start > lastIndex) chunks.push({ text: text.slice(lastIndex, start) });
    chunks.push({ text: match[0], url: match[0] });
    lastIndex = start + match[0].length;
  }
  if (lastIndex < text.length) chunks.push({ text: text.slice(lastIndex) });
  return chunks;
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
