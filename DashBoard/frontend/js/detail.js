/* ============================================================
   CHARDI.AI — DETAIL PAGE
   Reads ?id= from URL, fetches tender, populates page.
   ============================================================ */

const Detail = (() => {
  const { fetchTenderById, formatINRFull, formatDate,
          deadlineClass, deadlineDaysLabel, portalBadgeClass,
          buyerTypeLabel, relativeTime } = window.API;

  function escHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function getPortalName(portal) {
    const map = {
      gem: 'GeM', cppp: 'CPPP', ireps: 'IREPS',
      mahatenders: 'MahaTenders', karnataka: 'Karnataka eProcure',
      tamilnadu: 'TN Tenders', gujarat: 'nProcure Gujarat',
      rajasthan: 'SPPP Rajasthan', westbengal: 'WB Tenders',
      telangana: 'Telangana Tenders', kerala: 'Kerala eTenders',
      andhrapradesh: 'AP eProcurement', uttarpradesh: 'UP eTender',
      madhyapradesh: 'MP Tenders', haryana: 'Haryana eTenders',
      punjab: 'Punjab eTenders'
    };
    return map[portal] || portal.toUpperCase();
  }

  function showSkeleton() {
    document.getElementById('detail-content').style.display = 'none';
    document.getElementById('detail-skeleton').style.display = 'block';
    document.getElementById('detail-error').style.display   = 'none';
  }

  function showError(isNotFound) {
    document.getElementById('detail-content').style.display  = 'none';
    document.getElementById('detail-skeleton').style.display = 'none';
    const errorEl = document.getElementById('detail-error');
    errorEl.style.display = 'block';
    errorEl.innerHTML = `
      <div class="error-state" style="padding: var(--spacing-3xl) var(--spacing-xl);">
        <div class="error-state__icon">${isNotFound ? '🔍' : '⚠'}</div>
        <div class="error-state__title">${isNotFound ? 'Tender Not Found' : 'Failed to Load'}</div>
        <div class="error-state__message">
          ${isNotFound
            ? 'This tender ID does not exist or may have been removed.'
            : 'Could not load tender details. Please check your connection.'}
        </div>
        <a href="index.html" class="btn btn--ghost" style="margin-top: var(--spacing-md);">
          ← Back to Dashboard
        </a>
      </div>`;
  }

  function populate(tender) {
    document.getElementById('detail-skeleton').style.display = 'none';
    document.getElementById('detail-error').style.display   = 'none';
    const content = document.getElementById('detail-content');
    content.style.display = 'block';

    // Title + status badge
    document.getElementById('detail-title').textContent = tender.title;
    const badge = document.getElementById('detail-status-badge');
    badge.className = `badge badge--${tender.status}`;
    badge.textContent = tender.status;

    // Browser tab title
    document.title = `${tender.title.slice(0, 60)} — Chardi.ai`;

    // Deadline
    const dClass = deadlineClass(tender.deadline_at);
    const dLabel = deadlineDaysLabel(tender.deadline_at);
    const deadlineHtml = `
      <span class="${dClass}">${formatDate(tender.deadline_at)}</span>
      ${dLabel ? `<span class="deadline-badge deadline-badge--${dClass.replace('deadline--','')}" style="margin-left:6px;">${dLabel}</span>` : ''}`;

    // Value
    const valueHtml = tender.value
      ? `<span class="value-mono">${formatINRFull(tender.value)}</span>`
      : `<span class="value-not-disclosed">Not Disclosed</span>`;

    // Metadata grid
    const metaGrid = document.getElementById('detail-meta-grid');
    const portalName = getPortalName(tender.source_portal);
    const stateLabel = tender.state || 'Central (Pan-India)';
    metaGrid.innerHTML = `
      <div class="meta-item">
        <div class="meta-item__label">Tender Ref No</div>
        <div class="meta-item__value" style="font-family: var(--font-mono); font-size: var(--text-xs);">${escHtml(tender.tender_ref_no)}</div>
      </div>
      <div class="meta-item">
        <div class="meta-item__label">Source Portal</div>
        <div class="meta-item__value">
          <span class="portal-badge ${portalBadgeClass(tender.source_portal)}">${portalName}</span>
        </div>
      </div>
      <div class="meta-item">
        <div class="meta-item__label">Buyer Name</div>
        <div class="meta-item__value">${escHtml(tender.buyer_name)}</div>
      </div>
      <div class="meta-item">
        <div class="meta-item__label">Buyer Type</div>
        <div class="meta-item__value">${buyerTypeLabel(tender.buyer_type)}</div>
      </div>
      <div class="meta-item">
        <div class="meta-item__label">State / Jurisdiction</div>
        <div class="meta-item__value" style="font-family: var(--font-mono);">${escHtml(stateLabel)}</div>
      </div>
      <div class="meta-item">
        <div class="meta-item__label">Category</div>
        <div class="meta-item__value">${escHtml(tender.category)}</div>
      </div>
      <div class="meta-item">
        <div class="meta-item__label">Published</div>
        <div class="meta-item__value" style="font-family: var(--font-mono);">${formatDate(tender.published_at)}</div>
      </div>
      <div class="meta-item">
        <div class="meta-item__label">Deadline</div>
        <div class="meta-item__value">${deadlineHtml}</div>
      </div>
      <div class="meta-item">
        <div class="meta-item__label">Estimated Value</div>
        <div class="meta-item__value">${valueHtml}</div>
      </div>
      <div class="meta-item">
        <div class="meta-item__label">Currency</div>
        <div class="meta-item__value" style="font-family: var(--font-mono);">${tender.currency}</div>
      </div>`;

    // Description
    const descEl = document.getElementById('detail-description');
    const expandBtn = document.getElementById('detail-expand-btn');
    if (tender.description) {
      descEl.textContent = tender.description;
      if (tender.description.length > 500) {
        descEl.classList.add('collapsed');
        expandBtn.style.display = 'block';
        expandBtn.addEventListener('click', () => {
          const collapsed = descEl.classList.toggle('collapsed');
          expandBtn.textContent = collapsed ? 'Show more ↓' : 'Show less ↑';
        });
      }
    } else {
      descEl.textContent = 'No description available.';
      descEl.style.color = 'var(--color-text-muted)';
    }

    // Documents
    const docsEl = document.getElementById('detail-documents');
    if (tender.document_urls && tender.document_urls.length > 0) {
      docsEl.innerHTML = tender.document_urls.map((url, i) => {
        const filename = url.split('/').pop() || `Document ${i + 1}`;
        return `
          <a href="${escHtml(url)}" target="_blank" rel="noopener noreferrer" class="doc-link">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
            </svg>
            ${escHtml(filename)}
          </a>`;
      }).join('');
      document.getElementById('detail-docs-section').style.display = 'block';
    } else {
      document.getElementById('detail-docs-section').style.display = 'none';
    }

    // Source link
    const sourceLink = document.getElementById('detail-source-link');
    if (tender.source_url) {
      sourceLink.href = tender.source_url;
      sourceLink.textContent = `View on ${portalName} →`;
      sourceLink.style.display = 'inline-flex';
    }

    // Scraped at
    const scrapedEl = document.getElementById('detail-scraped');
    if (scrapedEl) {
      scrapedEl.textContent = `Data last updated ${relativeTime(tender.scraped_at)}`;
    }
  }

  async function init() {
    const params = new URLSearchParams(window.location.search);
    const id = params.get('id');

    if (!id) {
      showError(true);
      return;
    }

    showSkeleton();

    try {
      const tender = await fetchTenderById(id);
      populate(tender);
    } catch (err) {
      showError(err.message === 'TENDER_NOT_FOUND');
    }
  }

  return { init };
})();

document.addEventListener('DOMContentLoaded', () => Detail.init());