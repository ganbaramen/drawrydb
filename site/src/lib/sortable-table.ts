// Click-to-sort for a <table>'s numeric/date columns. Any <th> that carries
// data-sort-type ("number" or "date") becomes sortable; a header with
// neither (e.g. the name column, deliberately excluded — alphabetical sort
// wasn't asked for) is left alone. Each sortable column's <td> should carry
// a data-sort-value with the raw comparable value (song.play_rate as a
// 0-1 float, not the rounded "97%" text that's actually displayed).
export function initSortableTable(table: HTMLTableElement): void {
  const headers = Array.from(table.querySelectorAll<HTMLTableCellElement>('thead th'));
  const tbody = table.tBodies[0];
  if (!tbody) return;

  let activeIndex = -1;
  let ascending = true;

  headers.forEach((th, index) => {
    const type = th.dataset.sortType;
    if (!type) return;

    th.classList.add('sortable');
    th.setAttribute('role', 'button');
    th.setAttribute('tabindex', '0');
    th.setAttribute('aria-sort', 'none');

    const sort = () => {
      ascending = activeIndex === index ? !ascending : true;
      activeIndex = index;

      headers.forEach((h) => {
        delete h.dataset.sortDir;
        if (h.dataset.sortType) h.setAttribute('aria-sort', 'none');
      });
      th.dataset.sortDir = ascending ? 'asc' : 'desc';
      th.setAttribute('aria-sort', ascending ? 'ascending' : 'descending');

      const rows = Array.from(tbody.rows);
      rows.sort((a, b) => {
        const va = a.cells[index]?.dataset.sortValue ?? '';
        const vb = b.cells[index]?.dataset.sortValue ?? '';

        if (type === 'number') {
          const na = parseFloat(va);
          const nb = parseFloat(vb);
          const aBlank = Number.isNaN(na);
          const bBlank = Number.isNaN(nb);
          // A blank cell (e.g. a song with no track number) always sorts
          // to the bottom, regardless of direction — NaN - NaN style
          // comparisons here previously returned NaN, which corrupts the
          // *entire* sort (not just the blank rows), since NaN is neither
          // <0, >0, nor 0.
          if (aBlank || bBlank) {
            if (aBlank && bBlank) return 0;
            return aBlank ? 1 : -1;
          }
          return ascending ? na - nb : nb - na;
        }

        const cmp = va < vb ? -1 : va > vb ? 1 : 0;
        return ascending ? cmp : -cmp;
      });
      rows.forEach((row) => tbody.appendChild(row));
    };

    th.addEventListener('click', sort);
    th.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        sort();
      }
    });
  });
}
