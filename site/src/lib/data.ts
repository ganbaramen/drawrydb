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
}

export interface Venue {
  id: string;
  name: string;
  shows: number;
  first_played: string;
  last_played: string;
  event_ids: string[];
}

interface SiteData {
  generated_at: string;
  events: Event[];
  songs: Song[];
  venues: Venue[];
}

const data = raw as SiteData;

export const generatedAt: string = data.generated_at;

// Already sorted by id (== chronological) by the exporter.
export const events: Event[] = data.events;
export const songs: Song[] = data.songs;
export const venues: Venue[] = data.venues;

export function getEvent(id: string): Event | undefined {
  return events.find((event) => event.id === id);
}

export function getSong(id: string): Song | undefined {
  return songs.find((song) => song.id === id);
}

export function getVenue(id: string): Venue | undefined {
  return venues.find((venue) => venue.id === id);
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
