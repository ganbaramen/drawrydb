// Wires a <ColumnPicker> up to its table.
//
// Showing and hiding is *not* done here: ColumnPicker.astro emits one pair of
// CSS rules per column, keyed off each checkbox's :checked state, so the menu
// works with no script at all. This file only does the two things CSS cannot:
// remember the chosen set per reader, and tell the scroll shadows that the
// table changed width.
//
// Nothing ever removes a cell from a row. lib/sortable-table.ts sorts by
// `cells[index]`, so a column that came out of the markup would silently
// misalign every column after it; `display: none` keeps the index intact.
export function initColumnPicker(picker: HTMLElement): void {
  const defaults = new Set((picker.dataset.defaults || '').split(',').filter(Boolean));
  const storageKey = picker.dataset.storageKey;
  const toggles = Array.from(
    picker.querySelectorAll<HTMLInputElement>('input[data-column-toggle]'),
  );

  function read(): Set<string> {
    // A private window, cleared site data, or a browser set to block storage
    // all land here; the server-rendered defaults are the right answer in
    // every one of those cases.
    try {
      const saved = storageKey && localStorage.getItem(storageKey);
      if (saved) return new Set(JSON.parse(saved) as string[]);
    } catch {
      /* fall through to defaults */
    }
    return defaults;
  }

  function save(chosen: Set<string>): void {
    try {
      if (storageKey) localStorage.setItem(storageKey, JSON.stringify([...chosen]));
    } catch {
      /* a reader who can't persist still gets the toggle for this visit */
    }
  }

  // Showing or hiding a column changes the table's scrollWidth without a
  // window resize, and lib/table-scroll.ts only recomputes its edge shadows
  // on scroll or resize — without this nudge they'd claim the table still
  // overflows after the columns that overflowed it were switched off.
  function nudgeScrollShadows(): void {
    window.dispatchEvent(new Event('resize'));
  }

  toggles.forEach((toggle) => {
    toggle.addEventListener('change', () => {
      save(new Set(toggles.filter((t) => t.checked).map((t) => t.dataset.columnToggle!)));
      nudgeScrollShadows();
    });
  });

  // Restoring the remembered set is the one thing that has to move the
  // controls; from there the CSS follows them.
  const chosen = read();
  toggles.forEach((toggle) => {
    toggle.checked = chosen.has(toggle.dataset.columnToggle!);
  });
  nudgeScrollShadows();
}
