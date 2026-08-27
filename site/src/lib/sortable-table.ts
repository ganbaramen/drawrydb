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

    // A real <button> inside the cell, rather than role="button" on the
    // <th> itself: that role overrode the cell's implicit columnheader
    // role, so the header stopped being announced as the column's header
    // *and* the aria-sort set on the same element became meaningless —
    // aria-sort is only defined on a column header. The <th> keeps its own
    // role and carries aria-sort; the button carries the interaction.
    const label = document.createElement('button');
    label.type = 'button';
    label.className = 'sortable';
    while (th.firstChild) label.appendChild(th.firstChild);
    // The indicator lives in its own aria-hidden span rather than in a
    // ::after on the button. Chrome folds CSS generated content into the
    // accessible name, so the arrow was being announced as part of the
    // header — "披露回数 ↑" rather than "披露回数". aria-hidden excludes the
    // span and its generated content from the name; the sort state is
    // carried by the <th>'s aria-sort, which is where it belongs.
    const arrow = document.createElement('span');
    arrow.className = 'sort-arrow';
    arrow.setAttribute('aria-hidden', 'true');
    label.appendChild(arrow);
    th.appendChild(label);
    th.setAttribute('aria-sort', 'none');

    const sort = () => {
      ascending = activeIndex === index ? !ascending : true;
      activeIndex = index;

      headers.forEach((h) => {
        if (h.dataset.sortType) h.setAttribute('aria-sort', 'none');
      });
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

        // Dates compare as plain strings (ISO sorts correctly that way),
        // but blanks need the same treatment the numeric branch gives
        // them. Without this an empty date sorts *first* ascending and
        // last descending — the exact asymmetry B-04 was fixed to remove,
        // and the site's rule is blanks last in both directions. No date
        // column is blank today; this is the branch that keeps it true if
        // one ever is.
        const aBlank = va === '';
        const bBlank = vb === '';
        if (aBlank || bBlank) {
          if (aBlank && bBlank) return 0;
          return aBlank ? 1 : -1;
        }

        const cmp = va < vb ? -1 : va > vb ? 1 : 0;
        return ascending ? cmp : -cmp;
      });
      rows.forEach((row) => tbody.appendChild(row));
    };

    // A <button> already answers Enter and Space with a click, so the
    // keydown handler the <th> needed is gone with it.
    label.addEventListener('click', sort);
  });
}
