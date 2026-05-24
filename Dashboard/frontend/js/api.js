/* ============================================================
   CHARDI.AI — API LAYER
   Points to FastAPI backend at BASE_URL.
   Set USE_MOCK = true for local development without a backend.
   ============================================================ */

const BASE_URL = 'https://backend-production-6227c.up.railway.app'; // change to your Railway URL in prod
const USE_MOCK  = false;                  // flip to true for offline dev

/* ──────────────────────────────────────────────
   PORTALS COVERED
   ────────────────────────────────────────────── */

const PORTALS = [
  { id: 'cppp',                   label: 'CPPP',          badge: 'portal-badge--cppp'  },
  { id: 'mahatenders',            label: 'Maharashtra',   badge: 'portal-badge--state' },
  { id: 'kppp',                   label: 'Karnataka',     badge: 'portal-badge--state' },
  { id: 'tntenders',              label: 'Tamil Nadu',    badge: 'portal-badge--state' },
  { id: 'up_eprocurement',        label: 'Uttar Pradesh', badge: 'portal-badge--state' }, // Updated
  { id: 'telangana_eprocurement', label: 'Telangana',     badge: 'portal-badge--state' }, // Updated
  { id: 'wbtenders',              label: 'West Bengal',   badge: 'portal-badge--state' },
  { id: 'kerala_tenders',         label: 'Kerala',        badge: 'portal-badge--state' }, // Updated
  { id: 'ap_eprocurement',        label: 'Andhra Pradesh',badge: 'portal-badge--state' },
  { id: 'rajasthan_eprocurement', label: 'Rajasthan',     badge: 'portal-badge--state' }, // Updated
];

window.PORTALS = PORTALS;



/* ──────────────────────────────────────────────
   INTERNAL HELPERS
   ────────────────────────────────────────────── */

function buildQueryString(obj) {
  const params = new URLSearchParams();
  Object.entries(obj).forEach(([key, val]) => {
    if (val === null || val === undefined || val === '' || val === 'all') return;
    if (Array.isArray(val)) {
      val.forEach(v => v && params.append(key, v));
    } else {
      params.set(key, val);
    }
  });
  return params.toString();
}

function applyMockFilters(tenders, filters) {
  return tenders.filter(t => {
    if (filters.q) {
      const q = filters.q.toLowerCase();
      if (!(t.title + t.buyer_name + (t.description || '')).toLowerCase().includes(q)) return false;
    }
    if (filters.status && filters.status !== 'all' && t.status !== filters.status) return false;
    if (filters.state  && filters.state !== 'all') {
      if (filters.state === 'central' && t.state !== null) return false;
      if (filters.state !== 'central' && t.state !== filters.state) return false;
    }
    if (filters.buyer_type?.length && !filters.buyer_type.includes(t.buyer_type)) return false;
    if (filters.portal?.length && !filters.portal.includes(t.source_portal)) return false;
    if (filters.min_value && t.value < Number(filters.min_value)) return false;
    if (filters.max_value && t.value > Number(filters.max_value)) return false;
    return true;
  });
}

async function simulateDelay(ms) {
  return new Promise(r => setTimeout(r, ms));
}

/* ──────────────────────────────────────────────
   PUBLIC API FUNCTIONS
   ────────────────────────────────────────────── */

async function fetchTenders(filters = {}, page = 1, limit = 25) {
  if (USE_MOCK) {
    await simulateDelay(400);
    const filtered    = applyMockFilters(MOCK_TENDERS, filters);
    const total       = filtered.length;
    const total_pages = Math.max(1, Math.ceil(total / limit));
    const tenders     = filtered.slice((page - 1) * limit, page * limit);
    return { tenders, total, page, total_pages, limit };
  }

  const qs  = buildQueryString({ ...filters, page, limit });
  const res = await fetch(`${BASE_URL}/api/tenders?${qs}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function fetchTenderById(id) {
  if (USE_MOCK) {
    await simulateDelay(300);
    const tender = MOCK_TENDERS.find(t => t.id === id);
    if (!tender) throw new Error('TENDER_NOT_FOUND');
    return tender;
  }

  const res = await fetch(`${BASE_URL}/api/tenders/${id}`);
  if (res.status === 404) throw new Error('TENDER_NOT_FOUND');
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function fetchStats() {
  if (USE_MOCK) {
    await simulateDelay(250);
    return MOCK_STATS;
  }

  const res = await fetch(`${BASE_URL}/api/stats`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function fetchChartData(filters = {}) {
  if (USE_MOCK) {
    await simulateDelay(200);
    return [
      { state: 'MH', count: 2 },
      { state: 'KA', count: 1 },
      { state: 'TN', count: 1 },
      { state: 'AP', count: 1 },
    ];
  }

  const qs  = buildQueryString({
    portal:     filters.portal,
    status:     filters.status,
    buyer_type: filters.buyer_type,
  });
  const res = await fetch(`${BASE_URL}/api/chart/state?${qs}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function exportTenders(format, filters = {}) {
  if (USE_MOCK) {
    const { tenders } = await fetchTenders(filters, 1, 9999);
    let content, mime, ext;
    if (format === 'json') {
      content = JSON.stringify(tenders, null, 2);
      mime = 'application/json'; ext = 'json';
    } else {
      const headers = ['id','tender_ref_no','title','buyer_name','buyer_type',
        'state','source_portal','status','value','category','published_at',
        'deadline_at','source_url'];
      const rows = tenders.map(t =>
        headers.map(h => {
          const v = t[h];
          if (v == null) return '';
          const s = String(v);
          return s.includes(',') || s.includes('"') ? `"${s.replace(/"/g,'""')}"` : s;
        }).join(',')
      );
      content = [headers.join(','), ...rows].join('\n');
      mime = 'text/csv'; ext = 'csv';
    }
    const blob = new Blob([content], { type: mime });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = `chardi-tenders-${new Date().toISOString().slice(0,10)}.${ext}`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    return;
  }

  const qs = buildQueryString({ ...filters, format });
  window.location.href = `${BASE_URL}/api/tenders/export?${qs}`;
}

/* ──────────────────────────────────────────────
   FORMATTING UTILITIES
   ────────────────────────────────────────────── */

function formatINR(value) {
  if (value == null) return null;
  const n = Number(value);
  if (n >= 1e9)  return `₹${(n / 1e9).toFixed(2)}Cr`;
  if (n >= 1e7)  return `₹${(n / 1e7).toFixed(2)}Cr`;
  if (n >= 1e5)  return `₹${(n / 1e5).toFixed(2)}L`;
  if (n >= 1e3)  return `₹${(n / 1e3).toFixed(1)}K`;
  return `₹${n.toLocaleString('en-IN')}`;
}

function formatINRFull(value) {
  if (value == null) return 'Not Disclosed';
  return '₹' + Number(value).toLocaleString('en-IN');
}

function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric'
  });
}

function deadlineClass(iso) {
  if (!iso) return 'deadline--normal';
  const days = (new Date(iso) - Date.now()) / 86400000;
  if (days < 7)  return 'deadline--urgent';
  if (days < 30) return 'deadline--soon';
  return 'deadline--normal';
}

function deadlineDaysLabel(iso) {
  if (!iso) return '';
  const days = Math.ceil((new Date(iso) - Date.now()) / 86400000);
  if (days < 0)  return 'Expired';
  if (days === 0) return 'Today!';
  if (days === 1) return '1 day left';
  if (days < 30) return `${days}d left`;
  return '';
}

function portalBadgeClass(portal) {
  const map = {
    cppp: 'portal-badge--cppp',
    gem:  'portal-badge--gem',
  };
  return map[portal] || 'portal-badge--state';
}

function portalLabel(portal) {
  const p = (window.PORTALS || []).find(x => x.id === portal);
  return p ? p.label : portal.toUpperCase();
}

function relativeTime(iso) {
  if (!iso) return 'Unknown';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1)  return 'just now';
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function buyerTypeLabel(type) {
  const map = {
    central_ministry: 'Central Ministry',
    psu:              'PSU',
    state_govt:       'State Govt',
    defence:          'Defence',
    autonomous_body:  'Autonomous Body',
    local_body:       'Local Body',
  };
  return map[type] || (type || '—');
}

// Expose globally
window.API = {
  fetchTenders,
  fetchTenderById,
  fetchStats,
  fetchChartData,
  exportTenders,
  formatINR,
  formatINRFull,
  formatDate,
  deadlineClass,
  deadlineDaysLabel,
  portalBadgeClass,
  portalLabel,
  relativeTime,
  buyerTypeLabel,

};
