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

// One ticket on-sale (発売) phase — events can list several (先行 then
// 一般). Parsed from the calendar description by parse_ticket_sales() in
// export_site_data.py; "YYYY-MM-DD HH:MM" in JST, or null when that phase
// has no such boundary (e.g. a "〜4/30 23:59まで" end-only window).
export interface TicketSale {
  label: string | null;
  start: string | null;
  end: string | null;
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
  // 特典会 (meet & greet) — same per-calendar-event granularity gap as the
  // other time fields (see CLAUDE.md's shows.csv section).
  meet_start: string | null;
  meet_end: string | null;
  has_setlist: boolean;
  setlist: SetlistEntry[];
  ticket_links: TicketLink[];
  ticket_sales: TicketSale[];
  note: string | null;
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
  // English translation of the title (data/input/song_details.csv); null
  // if none is set. Shown as a subtitle under the title on the song's own
  // page — song.name itself is never replaced by it (names stay in their
  // original language everywhere else on the site).
  translation: string | null;
  plays: number;
  shows: number;
  shows_since_debut: number;
  play_rate: number;
  first_performed: string;
  last_performed: string;
  // Consecutive-show counts, per show *date* (a double-header day is one
  // unit) and counting only shows on/after the song's own debut — see
  // build_songs() in pipeline/export_site_data.py. current_streak runs back
  // from the most recent show and is 0 if the latest show didn't include
  // the song.
  current_streak: number;
  longest_streak: number;
  debut_confirmed: boolean;
  encores: number;
  is_se: boolean;
  is_interlude: boolean;
  performances: Performance[];
  // Hand-maintained (data/input/song_details.csv); null for a song with no
  // row yet.
  credits: SongCredits | null;
}

export interface CreatorCredit {
  song_id: string;
  song_name: string;
  translation: string | null;
  // Subset of "lyrics" | "composition" | "arrangement" | "choreography",
  // in that fixed order — everything this person did on this one song.
  roles: string[];
}

export interface Creator {
  id: string;
  name: string;
  // Bare X/Twitter handle (no "@", no URL) from data/input/
  // creator_details.csv; null when not known.
  x: string | null;
  songs: CreatorCredit[];
}

export interface Venue {
  id: string;
  name: string;
  shows: number;
  first_played: string;
  last_played: string;
  event_ids: string[];
  // Hand-maintained (data/input/venue_details.csv); null for a venue with
  // no row yet. capacity is free-form text, not a number — some venues are
  // stated as a range or with a note (e.g. "約300名"), which a number
  // couldn't hold.
  address: string | null;
  capacity: string | null;
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
  translation: string | null;
  is_se: boolean;
  is_interlude: boolean;
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
  creators: Creator[];
  set_length_stats: SetLengthStats;
}

const data = raw as SiteData;

// Already sorted by id (== chronological) by the exporter.
export const events: Event[] = data.events;
export const songs: Song[] = data.songs;
export const venues: Venue[] = data.venues;
export const creators: Creator[] = data.creators;
export const setLengthStats: SetLengthStats = data.set_length_stats;

// Index once at module scope rather than scanning per call. These
// accessors are called from inside template loops (venues/[id].astro maps
// getEvent over a venue's shows; events/[id].astro calls getSong per
// setlist row), so a linear find made page rendering quadratic in the data
// size. It's imperceptible at today's ~200 events, which is exactly why it
// would go unnoticed until it wasn't.
const eventById = new Map(events.map((event) => [event.id, event]));
const songByName = new Map(songs.map((song) => [song.name, song]));
const venueByName = new Map(venues.map((venue) => [venue.name, venue]));
const creatorByName = new Map(creators.map((creator) => [creator.name, creator]));

export function getEvent(id: string): Event | undefined {
  return eventById.get(id);
}

// By *name*, not id — every other place in the data (Event.venue,
// SetlistEntry.song, Performance.venue, ...) carries the raw display name,
// never the id, since only song/venue pages themselves need the id (to
// link to). id is a separate, optionally hand-slugged field (see
// pipeline/export_site_data.py's load_details()) precisely so it's free to
// diverge from the name — looking these up by id here would silently break
// the moment a slug did.
export function getSong(name: string): Song | undefined {
  return songByName.get(name);
}

export function getVenue(name: string): Venue | undefined {
  return venueByName.get(name);
}

// By name, same reasoning as getSong/getVenue — a credit field (e.g.
// "nenene, & Yoshimura") stores creators' raw display names, split on
// " & " at render time, never an id.
export function getCreator(name: string): Creator | undefined {
  return creatorByName.get(name);
}

// Build-time "today" (JST, matching the calendar's own timezone) — this is a
// static site, so "upcoming" is relative to when it was last built/deployed,
// not the visitor's clock. The deploy workflow rebuilds often enough
// (triggered by every push, including the scheduled calendar refresh) that
// this stays close to accurate.
export const today = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Tokyo' }).format(new Date());

export function upcomingEvents(limit?: number): Event[] {
  // A posted setlist means the show already happened — setlists are only
  // entered from posts after the fact, so that's the decisive "is over"
  // signal, immune to any skew between build time and JST event dates (a
  // same-JST-day show used to linger here until midnight JST). The date
  // check stays as the first cut; has_setlist does the real filtering.
  const upcoming = events.filter((e) => !e.has_setlist && e.date >= today);
  return typeof limit === 'number' ? upcoming.slice(0, limit) : upcoming;
}

export function recentSetlists(limit = 5): Event[] {
  return events
    .filter((e) => e.has_setlist)
    .slice()
    .reverse()
    .slice(0, limit);
}
