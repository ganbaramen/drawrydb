// Loaded at build time from the pipeline's export step
// (pipeline/export_site_data.py) — not fetched at runtime. Regenerate with
// `python3 pipeline/export_site_data.py` from the repo root before `astro
// dev` or `astro build`; see pipeline/README.md.
import raw from '../../../data/generated/site_data.json';

export interface SetlistEntry {
  position: number;
  song: string;
  note: string;
  is_se: boolean;
  is_interlude: boolean;
  is_encore: boolean;
}

export interface TicketLink {
  label: string | null;
  url: string;
}

export interface Event {
  id: string;
  date: string;
  title: string;
  venue: string | null;
  doors: string | null;
  showtime: string | null;
  live_start: string | null;
  live_end: string | null;
  has_setlist: boolean;
  setlist: SetlistEntry[];
  ticket_links: TicketLink[];
}

export interface Performance {
  event_id: string;
  date: string;
  venue: string;
  position: number;
  is_encore: boolean;
  note: string;
}

export interface SongCredits {
  // A track number the band assigns — unrelated to setlist running order
  // (SetlistEntry.position). Empty string if not set.
  number: string;
  lyrics: string;
  composition: string;
  arrangement: string;
  choreography: string;
  // Free-form — e.g. a link to the lyrics post. May contain a bare URL;
  // rendered with autoLink() in lib/format.ts, not pre-parsed here.
  note: string;
}

export interface Song {
  id: string;
  name: string;
  plays: number;
  shows: number;
  shows_since_debut: number;
  play_rate: number;
  first_performed: string;
  last_performed: string;
  debut_confirmed: boolean;
  encores: number;
  is_se: boolean;
  is_interlude: boolean;
  performances: Performance[];
  // Hand-maintained (data/input/song_credits.csv); null for a song with no
  // row yet.
  credits: SongCredits | null;
}

export interface Venue {
  id: string;
  name: string;
  shows: number;
  first_played: string;
  last_played: string;
  event_ids: string[];
}

export interface LengthBucket {
  minutes: number;
  shows: number;
  avg_songs: number;
  shows_with_se: number;
  event_ids: string[];
}

export interface SongLengthRate {
  count: number;
  // Shows in this bucket on/after the song's own first_performed — not the
  // bucket's total show count, since a song can't have been played before
  // it existed (same reasoning as song_stats.csv's own play_rate).
  eligible: number;
}

export interface SongLengthCounts {
  id: string;
  name: string;
  // Keyed by LengthBucket.minutes, stringified ("20", "25", ...).
  rates: Record<string, SongLengthRate>;
}

export interface SetLengthStats {
  buckets: LengthBucket[];
  songs: SongLengthCounts[];
  uncovered_shows: number;
}

interface SiteData {
  events: Event[];
  songs: Song[];
  venues: Venue[];
  set_length_stats: SetLengthStats;
}

const data = raw as SiteData;

// Already sorted by id (== chronological) by the exporter.
export const events: Event[] = data.events;
export const songs: Song[] = data.songs;
export const venues: Venue[] = data.venues;
export const setLengthStats: SetLengthStats = data.set_length_stats;

export function getEvent(id: string): Event | undefined {
  return events.find((event) => event.id === id);
}

// By *name*, not id — every other place in the data (Event.venue,
// SetlistEntry.song, Performance.venue, ...) carries the raw display name,
// never the id, since only song/venue pages themselves need the id (to
// link to). id is a separate, optionally hand-slugged field (see
// pipeline/export_site_data.py's load_slugs()) precisely so it's free to
// diverge from the name — looking these up by id here would silently break
// the moment a slug did.
export function getSong(name: string): Song | undefined {
  return songs.find((song) => song.name === name);
}

export function getVenue(name: string): Venue | undefined {
  return venues.find((venue) => venue.name === name);
}

// Build-time "today" (JST, matching the calendar's own timezone) — this is a
// static site, so "upcoming" is relative to when it was last built/deployed,
// not the visitor's clock. The deploy workflow rebuilds often enough
// (triggered by every push, including the scheduled calendar refresh) that
// this stays close to accurate.
const today = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Tokyo' }).format(new Date());

export function upcomingEvents(limit?: number): Event[] {
  const upcoming = events.filter((e) => e.date >= today);
  return typeof limit === 'number' ? upcoming.slice(0, limit) : upcoming;
}

export function recentSetlists(limit = 5): Event[] {
  return events
    .filter((e) => e.has_setlist)
    .slice()
    .reverse()
    .slice(0, limit);
}
