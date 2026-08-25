// Wraps every table container (the overflow-x-auto div Fulldev's <Table>
// renders around its <table>, tagged data-slot="table-container") in a
// .table-scroll-wrap with two edge-fade .scroll-shadow divs, and keeps
// their visibility in sync with actual scroll position. Kept as runtime
// DOM setup rather than static markup in each page so every table page
// gets it from the one call in Layout.astro, instead of every page
// needing its own copy.
export function initTableScrollShadows(): void {
  document.querySelectorAll<HTMLElement>('[data-slot="table-container"]').forEach((scrollEl) => {
    const wrap = document.createElement('div');
    wrap.className = 'table-scroll-wrap';
    scrollEl.parentElement!.insertBefore(wrap, scrollEl);
    wrap.appendChild(scrollEl);

    const left = document.createElement('div');
    left.className = 'scroll-shadow scroll-shadow--left';
    const right = document.createElement('div');
    right.className = 'scroll-shadow scroll-shadow--right';
    wrap.append(left, right);

    function update() {
      // >1px slack: a scrollWidth/clientWidth rounding difference of
      // under a pixel is common and isn't an actual scroll distance —
      // without slack, a table that exactly fits can still show a
      // shadow that never goes away no matter how far you scroll.
      const canScrollLeft = scrollEl.scrollLeft > 1;
      const canScrollRight = scrollEl.scrollLeft + scrollEl.clientWidth < scrollEl.scrollWidth - 1;
      wrap.toggleAttribute('data-can-scroll-left', canScrollLeft);
      wrap.toggleAttribute('data-can-scroll-right', canScrollRight);
    }

    scrollEl.addEventListener('scroll', update, { passive: true });
    window.addEventListener('resize', update);
    update();
  });
}
