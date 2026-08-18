// UI chrome dictionary for Phase 3 (see DRAWRYDB.md's i18n section). Song,
// event, and venue names are never translated — they stay Japanese in both
// locales — so this only needs to cover nav/labels/messages, not content.

export const LOCALES = ['ja', 'en'] as const;
export type Lang = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Lang = 'ja';

type Dict = Record<string, string>;

const ja: Dict = {
  'nav.events': 'イベント',
  'nav.songs': '楽曲',
  'nav.venues': '会場',
  'theme.toggle': 'テーマを切り替える',
  'disclaimer.pre': '非公式のファンサイトです — Drawry. 本人・関係者・公式とは一切関係ありません。',
  'disclaimer.post': 'が個人的に作成・運営しています。',
  'footer.disclaimer':
    'これは非公式のファンプロジェクトであり、Drawry. または関係者とは一切関係ありません。連絡先:',
  'footer.credit': '（ramen）',
  'footer.source': 'GitHubでソースを見る',
  'home.next': '次のライブ',
  'home.recent': '最近のセットリスト',
  'home.viewAll': 'すべてのイベントを見る →',
  'events.title': 'イベント一覧',
  'events.count': '{n}件',
  'events.filter.has': 'セトリあり',
  'events.filter.none': 'セトリなし',
  'events.filter.all': 'すべて',
  'events.month.label': '月で絞り込み',
  'events.month.all': 'すべての月',
  'events.back': '← イベント一覧に戻る',
  'events.venue': '会場',
  'events.doors': '開場',
  'events.showtime': '開演',
  'events.live': 'ライブ',
  'events.timeRangeSep': '〜',
  'events.pending': 'このライブのセットリストはまだ公開されていません。投稿され次第、追加されます。',
  'badge.pending': 'セトリ未公開',
  'badge.encore': 'アンコール',
  'songs.title': '楽曲一覧',
  'songs.count': '{n}曲',
  'songs.back': '← 楽曲一覧に戻る',
  'songs.name': '曲名',
  'songs.plays': '演奏回数',
  'songs.playsCount': '{n}回',
  'songs.debut': '初披露',
  'songs.lastPerformed': '最終披露',
  'songs.playRate': '披露率',
  'songs.playRateDetail': '{pct}% ({shows}/{total}公演)',
  'songs.encores': 'アンコール',
  'songs.history': '演奏履歴',
  'venues.title': '会場一覧',
  'venues.count': '{n}会場',
  'venues.back': '← 会場一覧に戻る',
  'venues.name': '会場',
  'venues.shows': '公演回数',
  'venues.showsCount': '{n}回',
  'venues.firstPlayed': '初出演',
  'venues.lastPlayed': '最終出演',
  'venues.history': '公演一覧',
};

const en: Dict = {
  'nav.events': 'Events',
  'nav.songs': 'Songs',
  'nav.venues': 'Venues',
  'theme.toggle': 'Toggle theme',
  'disclaimer.pre':
    'This is an unofficial fan site — not affiliated with Drawry. or their management. Made and run independently by ',
  'disclaimer.post': '.',
  'footer.disclaimer':
    'This is an unofficial fan project, not affiliated with Drawry. or their management. Contact:',
  'footer.credit': ' (ramen)',
  'footer.source': 'Source on GitHub',
  'home.next': 'Next show',
  'home.recent': 'Recent setlists',
  'home.viewAll': 'View all events →',
  'events.title': 'Events',
  'events.count': '{n} events',
  'events.filter.has': 'Has setlist',
  'events.filter.none': 'No setlist',
  'events.filter.all': 'All',
  'events.month.label': 'Filter by month',
  'events.month.all': 'All months',
  'events.back': '← Back to events',
  'events.venue': 'Venue',
  'events.doors': 'Doors',
  'events.showtime': 'Showtime',
  'events.live': 'Live',
  'events.timeRangeSep': '–',
  'events.pending': "This show's setlist hasn't been posted yet. It'll be added once it is.",
  'badge.pending': 'No setlist yet',
  'badge.encore': 'Encore',
  'songs.title': 'Songs',
  'songs.count': '{n} songs',
  'songs.back': '← Back to songs',
  'songs.name': 'Song',
  'songs.plays': 'Plays',
  'songs.playsCount': '{n} plays',
  'songs.debut': 'First performed',
  'songs.lastPerformed': 'Last performed',
  'songs.playRate': 'Play rate',
  'songs.playRateDetail': '{pct}% ({shows}/{total} shows)',
  'songs.encores': 'Encores',
  'songs.history': 'Performance history',
  'venues.title': 'Venues',
  'venues.count': '{n} venues',
  'venues.back': '← Back to venues',
  'venues.name': 'Venue',
  'venues.shows': 'Shows',
  'venues.showsCount': '{n} shows',
  'venues.firstPlayed': 'First played',
  'venues.lastPlayed': 'Last played',
  'venues.history': 'Shows',
};

const dictionaries: Record<Lang, Dict> = { ja, en };

export function t(lang: Lang, key: string, vars?: Record<string, string | number>): string {
  let str = dictionaries[lang][key] ?? dictionaries[DEFAULT_LOCALE][key] ?? key;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      str = str.replaceAll(`{${k}}`, String(v));
    }
  }
  return str;
}
