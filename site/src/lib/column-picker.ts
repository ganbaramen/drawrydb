// Wires a <ColumnPicker> up to its table: each checkbox hides or shows every
// cell carrying the matching data-column, and the chosen set is remembered
// per reader in localStorage.
//
// Cells are hidden with the `hidden` attribute rather than removed, so the
// column index every <td> sits at never changes — lib/sortable-table.ts sorts
// by `cells[index]`, and pulling cells out of the row would silently
// misalign it.
export function initColumnPicker(picker: HTMLElement, table: HTMLTableElement): void {
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

  function apply(chosen: Set<string>): void {
    toggles.forEach((toggle) => {
      const key = toggle.dataset.columnToggle!;
      const on = chosen.has(key);
      toggle.checked = on;
      table.querySelectorAll<HTMLElement>(`[data-column="${key}"]`).forEach((cell) => {
        cell.hidden = !on;
      });
    });
    // Showing or hiding a column changes the table's scrollWidth without a
    // window resize, and lib/table-scroll.ts only recomputes its edge shadows
    // on scroll or resize — without this nudge they'd claim the table still
    // overflows after the columns that overflowed it were switched off.
    window.dispatchEvent(new Event('resize'));
  }

  toggles.forEach((toggle) => {
    toggle.addEventListener('change', () => {
      const chosen = new Set(
        toggles.filter((t) => t.checked).map((t) => t.dataset.columnToggle!),
      );
      save(chosen);
      apply(chosen);
    });
  });

  apply(read());
}
