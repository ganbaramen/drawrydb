// Subsequence fuzzy match: every character of `query`, in order (not
// necessarily contiguous), must appear somewhere in `text` — the same
// loose matching a command-palette search uses. Works fine on CJK text
// too, since each character (not each Latin letter) is already the
// meaningful unit to match. Case-insensitive for Latin text; an empty
// query matches everything.
export function fuzzyMatch(query: string, text: string): boolean {
  if (!query) return true;
  const q = query.toLowerCase();
  const t = text.toLowerCase();
  let ti = 0;
  for (const ch of q) {
    const found = t.indexOf(ch, ti);
    if (found === -1) return false;
    ti = found + 1;
  }
  return true;
}
