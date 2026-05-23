/* ============================================================
   CHARDI.AI — TABLE MODULE
   Handles all tender table rendering and interactions.
   ============================================================ */

const Table = (() => {
  const { formatINR, formatDate, deadlineClass, deadlineDaysLabel,
          portalBadgeClass, buyerTypeLabel } = window.API;

  /* ── Render full table ── */
  function renderTable(tenders, totalCount) {
    const wrapper = document.getElementById('table-body-wrapper');
    if (!wrapper) return;

    // Update result count
    updateResultCount(totalCount);

    if (!tenders || tenders.length === 0) {
      renderEmpty();
      return;
    }

    wrapper.innerHTML = tenders.map(t => renderRow(t)).join('');
  }

  /* ── Render single row ── */
  function renderRow(t) {
    const dClass = deadlineClass(t.deadline_at);
    const dLabel = deadlineDaysLabel(t.deadline_at);
    const valueDisplay = t.value ? formatINR(t.value) : null;
    const portalClass  = portalBadgeClass(t.source_portal);
    const portalLabel  = t.source_portal.toUpperCase();
    const stateLabel   = t.state || 'Central';

    const urgencyBadge = dLabel
      ? `<div class="deadline-badge deadline-badge--${dClass.replace('deadline--', '')}">
           ${dLabel}
         </div>`
      : '';

    return `
      <tr data-tender-id="${t.id}">
        <td class="td-title">
          <div class="tooltip-wrapper">
            <div class="td-title__text">${escHtml(t.title)}</div>
            <div class="tooltip">${escHtml(t.title)}</div>
          </div>
        </td>
        <td class="td-buyer">
          <div class="td-buyer__name">${escHtml(t.buyer_name)}</div>
          <div class="td-buyer__type">${buyerTypeLabel(t.buyer_type)}</div>
        </td>
        <td class="td-state">${escHtml(stateLabel)}</td>
        <td class="td-category">${escHtml(t.category)}</td>
        <td class="td-value">
          ${valueDisplay
            ? `<span class="value-mono">${valueDisplay}</span>`
            : `<span class="value-not-disclosed">Not disclosed</span>`}
        </td>
        <td class="td-deadline">
          <div class="${dClass}">${formatDate(t.deadline_at)}</div>
          ${urgencyBadge}
        </td>
        <td>
          <span class="badge badge--${t.status}">${t.status}</span>
        </td>
        <td class="td-source">
          <span class="portal-badge ${portalClass}">${portalLabel}</span>
        </td>
      </tr>`;
  }

  /* ── Skeleton loading rows ── */
  function renderSkeletons(count = 10) {
    const wrapper = document.getElementById('table-body-wrapper');
    if (!wrapper) return;

    wrapper.innerHTML = Array.from({ length: count }, () => `
      <tr class="skeleton-row">
        <td>
          <span class="skel skel--title skeleton"></span>
          <span class="skel skel--title-sm skeleton"></span>
        </td>
        <td>
          <span class="skel skel--buyer skeleton"></span>
        </td>
        <td><span class="skel skel--short skeleton"></span></td>
        <td><span class="skel skel--medium skeleton"></span></td>
        <td><span class="skel skel--value skeleton"></span></td>
        <td><span class="skel skel--medium skeleton"></span></td>
        <td><span class="skel skel--badge skeleton"></span></td>
        <td><span class="skel skel--medium skeleton"></span></td>
      </tr>`).join('');

    updateResultCount(null);
  }

  /* ── Empty state ── */
  function renderEmpty() {
    const wrapper = document.getElementById('table-body-wrapper');
    if (!wrapper) return;

    wrapper.innerHTML = `
      <tr>
        <td colspan="8">
          <div class="empty-state">
            <div class="empty-state__icon">🔍</div>
            <div class="empty-state__title">No tenders found</div>
            <div class="empty-state__message">
              No tenders match your current filters. Try broadening your search or clearing filters.
            </div>
            <button class="btn btn--ghost" onclick="window.Filters.clearAll()">
              Clear all filters
            </button>
          </div>
        </td>
      </tr>`;

    updateResultCount(0);
  }

  /* ── Error state ── */
  function renderError(message = 'Something went wrong') {
    const wrapper = document.getElementById('table-body-wrapper');
    if (!wrapper) return;

    wrapper.innerHTML = `
      <tr>
        <td colspan="8">
          <div class="error-state">
            <div class="error-state__icon">⚠</div>
            <div class="error-state__title">Failed to load tenders</div>
            <div class="error-state__message">${escHtml(message)}</div>
            <button class="btn btn--ghost" id="retry-btn">
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
              </svg>
              Retry
            </button>
          </div>
        </td>
      </tr>`;

    const retryBtn = document.getElementById('retry-btn');
    if (retryBtn && window._dashboardRefresh) {
      retryBtn.addEventListener('click', window._dashboardRefresh);
    }
  }

  /* ── Sort column headers ── */
  function bindSortHeaders() {
    document.querySelectorAll('.th--sortable').forEach(th => {
      th.addEventListener('click', () => {
        const col = th.dataset.sort;
        window.Filters.setSort(col);
        updateSortUI(col, window.Filters.get().sort_dir);
      });
    });
  }

  function updateSortUI(activeCol, dir) {
    document.querySelectorAll('.th--sortable').forEach(th => {
      const arrow = th.querySelector('.sort-arrow');
      const isActive = th.dataset.sort === activeCol;
      th.classList.toggle('th--active', isActive);
      if (arrow) {
        arrow.classList.toggle('sort-arrow--asc',  isActive && dir === 'asc');
        arrow.classList.toggle('sort-arrow--desc', isActive && dir === 'desc');
      }
    });
  }

  /* ── Pagination ── */
  function renderPagination(page, totalPages, total) {
    const info = document.getElementById('pagination-info');
    const prevBtn  = document.getElementById('pagination-prev');
    const nextBtn  = document.getElementById('pagination-next');
    const jumpInput = document.getElementById('pagination-jump');
    const jumpMax   = document.getElementById('pagination-total');

    if (info)    info.textContent  = `Page ${page} of ${totalPages}`;
    if (jumpMax) jumpMax.textContent = totalPages;
    if (jumpInput) jumpInput.value = page;

    if (prevBtn) {
      prevBtn.disabled = page <= 1;
      prevBtn.onclick  = () => window.Filters.setPage(page - 1);
    }

    if (nextBtn) {
      nextBtn.disabled = page >= totalPages;
      nextBtn.onclick  = () => window.Filters.setPage(page + 1);
    }

    if (jumpInput) {
      jumpInput.onchange = () => {
        const p = parseInt(jumpInput.value, 10);
        if (p >= 1 && p <= totalPages) window.Filters.setPage(p);
        else jumpInput.value = page;
      };
    }
  }

  /* ── Result count ── */
  function updateResultCount(total) {
    const el = document.getElementById('result-count');
    if (!el) return;
    if (total === null) {
      el.innerHTML = '<span class="result-count">Loading...</span>';
    } else {
      el.innerHTML = `<span class="result-count">Showing <strong>${total.toLocaleString('en-IN')}</strong> tenders</span>`;
    }
  }

  /* ── Escape HTML ── */
  function escHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  /* ── Init ── */
  function init() {
    bindSortHeaders();
    const { sort_by, sort_dir } = window.Filters.get();
    if (sort_by) updateSortUI(sort_by, sort_dir);
  }

  return { init, renderTable, renderSkeletons, renderEmpty, renderError, renderPagination, updateSortUI };
})();

window.Table = Table;