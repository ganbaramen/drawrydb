const WEEKDAYS_JA = ['日', '月', '火', '水', '木', '金', '土'];

export function formatDateJa(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number);
  const date = new Date(Date.UTC(y, m - 1, d));
  return `${y}年${m}月${d}日(${WEEKDAYS_JA[date.getUTCDay()]})`;
}
